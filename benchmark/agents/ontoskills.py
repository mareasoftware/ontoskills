"""OntoSkills MCP agent for the benchmark.

Uses the single ``ontoskill`` MCP tool to find and load skill knowledge
via the Anthropic tool-use API.

Supports an optional **prefetch** mode that retrieves relevant skill
knowledge before the first API call and injects it into the system prompt.
This eliminates multi-turn tool-call overhead and frees turns for
interaction (asking clarifying questions, checking prerequisites).
"""

from __future__ import annotations

import json
import logging
import time

from benchmark.mcp_client.client import MCPClient

from .base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition (mirrors ontomcp single ontoskill tool)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "ontoskill",
        "description": (
            "Find or load a skill by name or query. "
            "If q matches a known skill id, returns that skill's context. "
            "Otherwise, searches for relevant skills."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Skill id or natural language query",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                },
            },
            "required": ["q"],
        },
    },
]


class OntoSkillsAgent(BaseAgent):
    """Agent that uses the single ontoskill MCP tool to query the OntoSkills knowledge base.

    Parameters
    ----------
    model:
        Anthropic model ID.
    ontology_root:
        Path to compiled TTL packages.
    ontomcp_bin:
        Path to the ontomcp binary.
    api_key:
        Anthropic API key.
    prefetch:
        When True, skill knowledge is retrieved via MCP before the first
        API call and injected into the system prompt.  This eliminates
        multi-turn tool-call overhead and frees turns for interaction.
    """

    def __init__(
        self,
        model: str,
        ontology_root: str,
        ontomcp_bin: str | None = None,
        api_key: str | None = None,
        prefetch: bool = False,
    ) -> None:
        super().__init__(model=model, api_key=api_key)
        self.ontology_root = ontology_root
        self.prefetch = prefetch
        self._prefetched_knowledge: str = ""
        # Create the client but do NOT start it yet (started in run()).
        self._mcp_client = MCPClient(
            ontomcp_bin=ontomcp_bin,
            ontology_root=ontology_root,
        )

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        if self._prefetched_knowledge:
            return self._build_enriched_system_prompt()
        return (
            "You are an AI agent with access to OntoSkills — a structured "
            "skill knowledge base.\n"
            "Use the `ontoskill` tool to find or load skills:\n"
            "- ontoskill(q='skill-name') to load a known skill by name\n"
            "- ontoskill(q='natural language query') to search for skills\n\n"
            "After loading skill knowledge, follow the procedures and "
            "constraints strictly.\n"
        )

    def get_tools(self) -> list[dict] | None:
        if self._prefetched_knowledge:
            return None
        return _TOOL_DEFINITIONS

    # ------------------------------------------------------------------
    # Pre-fetch helpers
    # ------------------------------------------------------------------

    def _compact_tool_result(
        self, tool_name: str, tool_input: dict, raw: dict,
    ) -> str:
        """Compact an MCP tool result into token-efficient text."""
        return self._compact_tool_result_static(tool_name, tool_input, raw)

    @staticmethod
    def _compact_tool_result_static(
        tool_name: str, tool_input: dict, mcp_result: dict,
    ) -> str:
        """Compact MCP tool response to reduce token usage."""
        content = mcp_result.get("content", [])
        if content and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item["text"]
        return json.dumps(mcp_result, indent=2)

    def prefetch_skills(self, task_prompt: str) -> str:
        """Pre-fetch relevant skill knowledge via MCP.

        Calls ontoskill and returns compact text.
        """
        try:
            mcp_result = self._mcp_client.call_tool(
                "ontoskill", {"q": task_prompt},
            )
            content = mcp_result.get("content", [])
            if content and isinstance(content, list) and content[0].get("text"):
                return content[0]["text"]
        except Exception as exc:
            logger.warning("ontoskill failed: %s", exc)
        return ""

    def prefetch_skills_by_ids(self, skill_ids: list[str], query: str | None = None) -> str:
        """Pre-fetch skill knowledge by known skill IDs (skip search).

        Used when skill_ids are already known (e.g. per-package tasks).
        Calls the single ``ontoskill`` tool for each ID.
        """
        parts: list[str] = []
        for sid in skill_ids:
            try:
                mcp_res = self._mcp_client.call_tool(
                    "ontoskill", {"q": sid},
                )
                content = mcp_res.get("content", [])
                if content and isinstance(content, list) and content[0].get("text"):
                    parts.append(content[0]["text"])
                    continue
            except Exception as exc:
                logger.warning("ontoskill(%s) failed: %s", sid, exc)
        return "\n\n".join(parts)

    def _build_enriched_system_prompt(self) -> str:
        """Build system prompt with pre-fetched skill knowledge."""
        return (
            "You are an AI agent with expert skill knowledge pre-loaded below.\n"
            "You already have ALL the knowledge needed. Do NOT search for more.\n"
            "Generate the solution code immediately based on the pre-loaded knowledge.\n"
            "Follow the skill's procedures, constraints, and best practices strictly.\n"
            "\n"
            "--- Pre-loaded Skill Knowledge ---\n"
            f"{self._prefetched_knowledge}\n"
            "--- End of Pre-loaded Knowledge ---\n"
        )

    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        """Execute one turn: call the API, execute any tool calls via MCP.

        Returns ``(assistant_message_dict, usage_metrics_dict)``.

        When the response contains tool_use blocks, the corresponding
        tool_result messages are appended to *messages* so that the next
        call sees the full conversation.  The assistant message is also
        appended (before tool_results) to maintain correct ordering.

        Sets ``self._subprocess_dead`` to ``True`` if an MCP exception
        is caught and the underlying subprocess is no longer alive, so
        that ``run()`` can break out of its loop.
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
        t_tool_start = time.perf_counter()
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_calls += 1
            tool_name = block["name"]
            tool_input = block.get("input", {})
            try:
                mcp_result = self._mcp_client.call_tool(tool_name, tool_input)
                # Compact the MCP result to save tokens.
                result_text = self._compact_tool_result(
                    tool_name, tool_input, mcp_result,
                )
                is_error = False
            except Exception as exc:
                result_text = f"Error calling {tool_name}: {exc}"
                is_error = True
                # I2: Check if the MCP subprocess is still alive.  If it
                # has crashed, set a flag so run() can break out instead
                # of sending cascading errors on subsequent turns.
                if self._mcp_client._proc is not None:
                    proc = self._mcp_client._proc
                    if proc.poll() is not None:
                        self._subprocess_dead = True

            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result_text,
                "is_error": is_error,
            })

        if tool_result_blocks:
            t_tool_end = time.perf_counter()
            latency_ms += (t_tool_end - t_tool_start) * 1000

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
        3. When ``prefetch=True``, retrieve skill knowledge via MCP
           before the first API call and inject into system prompt.
        4. Manage the conversation loop directly.
        5. Validate that tool_result messages are present for every
           tool_use block (C1).
        6. Break out of the loop early if the MCP subprocess has
           crashed (I2).
        """
        self._subprocess_dead = False
        self._prefetched_knowledge = ""

        with self._mcp_client:
            self._mcp_client.initialize()

            # Pre-fetch skill knowledge when enabled.
            if self.prefetch:
                knowledge = self.prefetch_skills(task_prompt)
                if knowledge:
                    self._prefetched_knowledge = knowledge
                    logger.info(
                        "Pre-fetched %d chars of skill knowledge",
                        len(knowledge),
                    )

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

                if tool_use_blocks:
                    # C1: Validate that run_turn appended matching
                    # tool_result messages for every tool_use block.
                    tool_ids = {b["id"] for b in tool_use_blocks}
                    last_msg = messages[-1] if messages else {}
                    result_ids: set[str] = set()
                    if isinstance(last_msg.get("content"), list):
                        result_ids = {
                            b.get("tool_use_id", "")
                            for b in last_msg["content"]
                            if isinstance(b, dict)
                            and b.get("type") == "tool_result"
                        }
                    missing = tool_ids - result_ids
                    if missing:
                        raise RuntimeError(
                            f"run_turn() returned tool_use blocks but the last "
                            f"message in *messages* does not contain matching "
                            f"tool_result blocks.  Missing tool_result for "
                            f"ids: {missing}."
                        )

                    # I2: If the MCP subprocess has crashed, break out
                    # instead of sending cascading errors on subsequent
                    # turns.
                    if self._subprocess_dead:
                        break
                else:
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
            )
