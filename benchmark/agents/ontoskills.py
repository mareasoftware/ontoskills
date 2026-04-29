"""OntoSkills MCP agent for the benchmark.

Uses the 5 MCP tools (search, get_skill_context, evaluate_execution_plan,
query_epistemic_rules, prefetch_knowledge) via the Anthropic tool-use API to answer questions
about skills.

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
            "required": ["query"],
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
                "query": {
                    "type": "string",
                    "description": "Optional natural language query to filter knowledge nodes.",
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
    """Agent that uses 4 MCP tools to query the OntoSkills knowledge base.

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

    # ------------------------------------------------------------------
    # Pre-fetch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_mcp_result(raw: dict) -> dict | None:
        """Extract the data payload from a raw MCP response."""
        data = raw.get("structuredContent")
        if data:
            return data if isinstance(data, dict) else {"result": data}
        content = raw.get("content", [])
        if content and isinstance(content, list) and content[0].get("text"):
            try:
                return json.loads(content[0]["text"])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _compact_tool_result(
        self, tool_name: str, tool_input: dict, raw: dict,
    ) -> str:
        """Compact an MCP tool result into token-efficient text."""
        return self._compact_tool_result_static(tool_name, tool_input, raw)

    @staticmethod
    def _compact_tool_result_static(
        tool_name: str, tool_input: dict, raw: dict,
    ) -> str:
        """Static wrapper for use outside the agent (e.g. perpackage wrapper)."""
        data = OntoSkillsAgent._parse_mcp_result(raw)
        if data is None:
            return json.dumps(raw, ensure_ascii=False)

        if tool_name == "search":
            return OntoSkillsAgent._compact_search(data)
        if tool_name == "get_skill_context":
            content = raw.get("content", [])
            if content and isinstance(content, list) and content[0].get("text"):
                return content[0]["text"]
            return json.dumps(raw, ensure_ascii=False)
        if tool_name == "query_epistemic_rules":
            return OntoSkillsAgent._compact_epistemic_rules(data)
        if tool_name == "evaluate_execution_plan":
            return OntoSkillsAgent._compact_plan(data)
        return json.dumps(raw, ensure_ascii=False)

    @staticmethod
    def _compact_search(data: dict) -> str:
        """Compact search results into concise text."""
        lines: list[str] = []
        mode = data.get("mode", "")
        lines.append(f"Search mode: {mode}")

        # BM25 results
        results = data.get("results", [])
        if results:
            for r in results[:5]:
                sid = r.get("skill_id", "")
                intents = "; ".join(r.get("intents", [])[:2])
                tier = r.get("trust_tier", "")
                lines.append(f"- {sid} [{tier}]: {intents}")

        # Semantic matches
        matches = data.get("matches", [])
        if matches:
            for m in matches[:3]:
                intent = m.get("intent", "")
                score = m.get("score", 0)
                skills = ", ".join(m.get("skills", [])[:3])
                lines.append(f"- {intent} (score={score:.2f}): {skills}")

        # Structured results
        skills = data.get("skills", [])
        if skills:
            for s in skills[:5]:
                sid = s.get("id", "")
                nature = s.get("nature", "")
                lines.append(f"- {sid} ({nature})")

        return "\n".join(lines) if len(lines) > 1 else json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _compact_epistemic_rules(data: dict) -> str:
        """Compact epistemic rules into concise text."""
        # Handle multiple response shapes: result (array), nodes, knowledge_nodes
        nodes = data.get("result", data.get("nodes", data.get("knowledge_nodes", [])))
        if isinstance(nodes, dict):
            nodes = nodes.get("nodes", nodes.get("knowledge_nodes", []))
        if not nodes:
            return "No knowledge nodes found."

        lines: list[str] = []
        for node in nodes:
            kind = node.get("kind", "").replace("_", " ").upper()
            content = node.get("directive_content", "")
            if not content:
                continue
            ctx = node.get("applies_to_context", "")
            severity = node.get("severity_level", "")
            parts = [kind]
            if ctx:
                parts.append(f"({ctx})")
            if severity and severity in ("CRITICAL", "HIGH"):
                parts.append(f"[{severity}]")
            lines.append("  ".join(parts) + ":")
            lines.append(f"  {content}")

        return "\n".join(lines) if lines else json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _compact_plan(data: dict) -> str:
        """Compact execution plan evaluation into concise text."""
        lines: list[str] = []
        applicable = data.get("applicable", False)
        lines.append(f"Applicable: {'Yes' if applicable else 'No'}")

        recommended = data.get("recommended_skill")
        if recommended:
            lines.append(f"Recommended: {recommended}")

        steps = data.get("plan_steps", [])
        if steps:
            lines.append("Plan:")
            for i, step in enumerate(steps, 1):
                lines.append(f"  {i}. {step.get('skill_id', '')}: {step.get('purpose', '')}")

        missing = data.get("missing_states", [])
        if missing:
            lines.append(f"Missing states: {', '.join(missing)}")

        warnings = data.get("dependency_warnings", [])
        if warnings:
            lines.append(f"Warnings: {'; '.join(warnings[:3])}")

        return "\n".join(lines)

    @staticmethod
    def _extract_skill_ids(search_result: dict) -> list[str]:
        """Extract skill_id values from an MCP search result."""
        data = search_result.get("structuredContent")
        if not data:
            content = search_result.get("content", [])
            if content and isinstance(content, list) and content[0].get("text"):
                try:
                    data = json.loads(content[0]["text"])
                except (json.JSONDecodeError, TypeError):
                    return []
        if not data:
            return []
        results = data.get("results", [])
        return [r["skill_id"] for r in results if "skill_id" in r]

    def prefetch_skills(self, task_prompt: str) -> str:
        """Pre-fetch relevant skill knowledge via MCP.

        Calls prefetch_knowledge and returns compact text.
        """
        try:
            mcp_result = self._mcp_client.call_tool(
                "prefetch_knowledge", {"query": task_prompt, "max_skills": 3},
            )
            content = mcp_result.get("content", [])
            if content and isinstance(content, list) and content[0].get("text"):
                return content[0]["text"]
        except Exception as exc:
            logger.warning("prefetch_knowledge failed: %s", exc)
        return ""

    def prefetch_skills_by_ids(self, skill_ids: list[str], query: str | None = None) -> str:
        """Pre-fetch skill knowledge by known skill IDs (skip search).

        Used when skill_ids are already known (e.g. per-package tasks).
        """
        parts: list[str] = []
        for sid in skill_ids:
            try:
                mcp_res = self._mcp_client.call_tool(
                    "get_skill_context", {"skill_id": sid, "query": query},
                )
                content = mcp_res.get("content", [])
                if content and isinstance(content, list) and content[0].get("text"):
                    parts.append(content[0]["text"])
            except Exception as exc:
                logger.warning("prefetch get_skill_context(%s) failed: %s", sid, exc)
        return "\n\n".join(parts)

    def _build_enriched_system_prompt(self) -> str:
        """Build system prompt with pre-fetched skill knowledge."""
        return (
            "You are an AI agent with expert skill knowledge pre-loaded below.\n"
            "Use this knowledge directly to complete the task.\n"
            "Follow the skill's procedures, constraints, and best practices strictly.\n"
            "If you need more details or other skills, use your available tools.\n"
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
