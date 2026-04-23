"""OntoSkills MCP agent for the benchmark.

Uses the 4 MCP tools (search, get_skill_context, evaluate_execution_plan,
query_epistemic_rules) via the Anthropic tool-use API to answer questions
about skills.
"""

from __future__ import annotations

import json
import time

from benchmark.mcp_client.client import MCPClient

from .base import AgentResult, BaseAgent

# ---------------------------------------------------------------------------
# Tool definitions (mirrors ontomcp src/main.rs:720-794)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "search",
        "description": (
            "Search skills by keyword query, alias, or structured filters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query",
                },
                "alias": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "intent": {"type": "string"},
                "requires_state": {"type": "string"},
                "yields_state": {"type": "string"},
                "skill_type": {
                    "type": "string",
                    "enum": ["executable", "declarative"],
                },
                "category": {"type": "string"},
                "is_user_invocable": {"type": "boolean"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        },
    },
    {
        "name": "get_skill_context",
        "description": (
            "Fetch the full execution context for a skill, including "
            "requirements, transitions, payload, dependencies, and "
            "knowledge nodes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": (
                        "Short id like 'xlsx' or qualified id like "
                        "'marea/office/xlsx'."
                    ),
                },
                "include_inherited_knowledge": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["skill_id"],
        },
    },
    {
        "name": "evaluate_execution_plan",
        "description": (
            "Evaluate whether an intent or skill can be executed from the "
            "current states and return the full plan plus warnings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "skill_id": {"type": "string"},
                "current_states": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
        },
    },
    {
        "name": "query_epistemic_rules",
        "description": (
            "Query normalized knowledge nodes with guided filters. "
            "Returns both epistemic nodes (rules, constraints) and "
            "operational nodes (procedures, code patterns, output "
            "formats, commands, prerequisites)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "kind": {"type": "string"},
                "dimension": {"type": "string"},
                "severity_level": {"type": "string"},
                "applies_to_context": {"type": "string"},
                "include_inherited": {
                    "type": "boolean",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        },
    },
]


class OntoSkillsAgent(BaseAgent):
    """Agent that uses 4 MCP tools to query the OntoSkills knowledge base."""

    def __init__(
        self,
        model: str,
        ontology_root: str,
        ontomcp_bin: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model=model, api_key=api_key)
        self.ontology_root = ontology_root
        # Create the client but do NOT start it yet (started in run()).
        self._mcp_client = MCPClient(
            ontomcp_bin=ontomcp_bin,
            ontology_root=ontology_root,
        )

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        return (
            "You are an AI agent with access to a knowledge base of skills "
            "via 4 tools:\n"
            "- search: Find skills by intent, keyword, or filters\n"
            "- get_skill_context: Get full execution context for a specific skill\n"
            "- evaluate_execution_plan: Check if an intent/skill can execute "
            "from given states\n"
            "- query_epistemic_rules: Query knowledge nodes (epistemic rules "
            "and operational procedures)\n"
            "\n"
            "Use these tools to answer questions about skills accurately. "
            "Call the appropriate tool(s) before answering. "
            "Be concise and factual."
        )

    def get_tools(self) -> list[dict] | None:
        return _TOOL_DEFINITIONS

    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        """Execute one turn: call the API, execute any tool calls via MCP.

        Returns ``(assistant_message_dict, usage_metrics_dict)``.

        When the response contains tool_use blocks, the corresponding
        tool_result messages are appended to *messages* so that the next
        call sees the full conversation.  The assistant message is also
        appended (before tool_results) to maintain correct ordering.
        """
        start = time.perf_counter()
        response = self._call_api(messages)
        latency_ms = (time.perf_counter() - start) * 1000

        # Build the assistant message from the response content blocks.
        content_blocks: list[dict] = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append({
                    "type": "text",
                    "text": block.text,
                })
            elif block.type == "tool_use":
                content_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        assistant_msg: dict = {
            "role": "assistant",
            "content": content_blocks,
        }

        # Execute any tool_use blocks via the MCP client and build
        # the corresponding tool_result blocks.
        tool_calls = 0
        tool_result_blocks: list[dict] = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_calls += 1
            tool_name = block["name"]
            tool_input = block.get("input", {})
            try:
                mcp_result = self._mcp_client.call_tool(tool_name, tool_input)
                # The MCP result has a "content" list; serialize it for the
                # tool_result payload.
                result_text = json.dumps(mcp_result, ensure_ascii=False)
            except Exception as exc:
                result_text = f"Error calling {tool_name}: {exc}"

            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result_text,
            })

        # When there are tool results, append both the assistant message
        # and the tool_result user message so that the conversation is
        # correctly ordered for the next API call.
        if tool_result_blocks:
            messages.append(assistant_msg)
            messages.append({
                "role": "user",
                "content": tool_result_blocks,
            })

        metrics: dict = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "tool_calls": tool_calls,
        }

        return assistant_msg, metrics

    # ------------------------------------------------------------------
    # Override run() to manage the MCP client lifecycle
    # ------------------------------------------------------------------

    def run(self, task_prompt: str, max_turns: int = 10) -> AgentResult:
        """Start the MCP client, run the agent loop, then shut down.

        Overrides the base ``run`` to:
        1. Wrap the loop in a ``with MCPClient`` context manager.
        2. Send the MCP ``initialize`` handshake before the first turn.
        3. Manage the conversation loop directly (the base class assumes
           the subclass does not append messages during ``run_turn``,
           but this agent must append tool_result messages to support
           multi-turn tool use).
        """
        with self._mcp_client:
            self._mcp_client.initialize()

            messages: list[dict] = [
                {"role": "user", "content": task_prompt},
            ]

            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0

            for _ in range(max_turns):
                assistant_msg, metrics = self.run_turn(messages)
                turns += 1

                total_input += metrics["input_tokens"]
                total_output += metrics["output_tokens"]
                total_latency_ms += metrics["latency_ms"]
                total_tool_calls += metrics["tool_calls"]

                # run_turn already appended the assistant message and
                # tool_result messages to *messages* when tool calls
                # occurred.  When there are no tool calls we must
                # append the assistant message ourselves.
                tool_use_blocks = [
                    b
                    for b in (assistant_msg.get("content") or [])
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]

                if not tool_use_blocks:
                    messages.append(assistant_msg)
                    break

            # Extract the final text answer from the last assistant message.
            answer = ""
            for block in reversed(messages):
                if isinstance(block, dict) and block.get("role") == "assistant":
                    content = block.get("content", "")
                    if isinstance(content, str):
                        answer = content
                    elif isinstance(content, list):
                        texts = [
                            b["text"]
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        answer = "\n".join(texts)
                    break

            return AgentResult(
                answer=answer,
                input_tokens=total_input,
                output_tokens=total_output,
                total_latency_ms=total_latency_ms,
                tool_calls=total_tool_calls,
                turns=turns,
                context_overflow=False,
            )
