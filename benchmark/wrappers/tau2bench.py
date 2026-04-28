"""Tau2-Bench benchmark wrapper.

Loads tau2-bench tasks, runs them through a BaseAgent subclass, and
scores results using string matching against expected outputs.

 tau2-bench (now tau^3-bench) evaluates agents via tool-call interactions
in simulated customer-service environments (airline, retail, banking, etc.).

This is a simplified first version that:
- Loads task instructions and available domain tools from the tau2 dataset
- Injects tools into the agent via monkey-patching
- Routes tool calls: MCP tool names -> MCP client, domain tools -> recorded
- Scores via string matching against expected outputs

If the ``tau2_bench`` package is not installed, ``Tau2BenchWrapper`` can
still be imported, but ``load_dataset`` will raise ``ImportError`` at runtime.
"""

from __future__ import annotations

import json
import logging
import time
from math import comb
from pathlib import Path
from typing import Any

from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import: tau2_bench may not be installed
# ---------------------------------------------------------------------------

try:
    from tau2_bench import (  # type: ignore[import-untyped]
        get_tasks,
        get_tools as get_tau2_tools,
    )

    _HAS_TAU2 = True
except ImportError:
    _HAS_TAU2 = False

# ---------------------------------------------------------------------------
# MCP tool names used by OntoSkillsAgent
# ---------------------------------------------------------------------------

_MCP_TOOL_NAMES = frozenset({
    "search",
    "get_skill_context",
    "evaluate_execution_plan",
    "query_epistemic_rules",
})


class Tau2BenchWrapper:
    """Tau2-Bench benchmark wrapper.

    Parameters
    ----------
    data_dir:
        Directory to cache downloaded tau2-bench data.
    """

    _VALID_DOMAINS = ("mock", "airline", "retail", "telecom")
    _POLICY_FILES = {
        "airline": "policy.md",
        "retail": "policy.md",
        "telecom": "main_policy.md",
    }

    def __init__(self, data_dir: str = "benchmark/data/tau2bench") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def load_dataset(
        self,
        domain: str = "airline",
        split: str = "test",
    ) -> list[dict]:
        """Load tau2-bench tasks from local JSON files.

        Each task dict contains:
        ``task_id``, ``instruction``, ``domain``, ``tools`` (list of tool
        schemas), ``expected_outputs`` (list of expected response strings).
        """
        if domain not in self._VALID_DOMAINS:
            raise ValueError(
                f"Invalid domain {domain!r}. "
                f"Choose from {self._VALID_DOMAINS}"
            )

        # Try local JSON files first (downloaded via hf download).
        tasks_file = self.data_dir / "domains" / domain / "tasks.json"
        if tasks_file.exists():
            return self._load_from_local_json(domain, tasks_file)

        # Fallback to tau2_bench package if installed.
        if not _HAS_TAU2:
            raise ImportError(
                "tau2_bench is not installed and no local data found at "
                f"{tasks_file}. Download with: hf download "
                "HuggingFaceH4/tau2-bench-data --repo-type dataset "
                "--local-dir benchmark/data/tau2bench"
            )

        tasks_raw = get_tasks(domain=domain, split=split)
        domain_tools = get_tau2_tools(domain=domain)

        tasks: list[dict] = []
        for i, task in enumerate(tasks_raw):
            task_id = task.get("task_id", f"{domain}_{split}_{i}")
            instruction = task.get("instruction", task.get("prompt", ""))
            expected = task.get("expected_outputs", task.get("expected", []))
            # expected may be a string or list of strings
            if isinstance(expected, str):
                expected = [expected]

            tasks.append({
                "task_id": str(task_id),
                "instruction": instruction,
                "domain": domain,
                "tools": domain_tools,
                "expected_outputs": expected,
                "metadata": {
                    k: v
                    for k, v in task.items()
                    if k not in ("instruction", "expected_outputs", "tools")
                },
            })

        logger.info(
            "Loaded %d tau2-bench tasks (domain=%s, split=%s)",
            len(tasks),
            domain,
            split,
        )
        return tasks

    def _load_from_local_json(
        self, domain: str, tasks_file: Path,
    ) -> list[dict]:
        """Load tasks from local JSON files downloaded via hf download."""
        with open(tasks_file, encoding="utf-8") as f:
            tasks_raw = json.load(f)

        # Build tool schemas from the domain's db.json API definitions.
        domain_tools: list[dict] = self._build_domain_tools(tasks_file)

        tasks: list[dict] = []
        for i, task in enumerate(tasks_raw):
            task_id = task.get("id", f"{domain}_{i}")

            # Build a string prompt from the user_scenario dict.
            instruction = self._serialize_instruction(task, domain)

            # Flatten evaluation_criteria into a list of expected strings.
            expected = self._flatten_expected_outputs(
                task.get("evaluation_criteria", {})
            )

            tasks.append({
                "task_id": str(task_id),
                "instruction": instruction,
                "domain": domain,
                "tools": domain_tools,
                "expected_outputs": expected,
                "metadata": {
                    k: v
                    for k, v in task.items()
                    if k not in ("description", "user_scenario")
                },
            })

        logger.info(
            "Loaded %d tau2-bench tasks from %s (domain=%s)",
            len(tasks), tasks_file, domain,
        )
        return tasks

    @staticmethod
    def _serialize_instruction(task: dict, domain: str) -> str:
        """Convert a tau2 task dict into a string prompt for the agent."""
        scenario = task.get("user_scenario")
        if not scenario:
            desc = task.get("description", "")
            if isinstance(desc, str):
                return desc
            return json.dumps(desc, ensure_ascii=False)

        if isinstance(scenario, str):
            return scenario

        # scenario is a dict with persona + instructions.
        parts: list[str] = []
        instr = scenario.get("instructions", {})
        if isinstance(instr, dict):
            task_instr = instr.get("task_instructions", "")
            if task_instr:
                parts.append(f"Instructions: {task_instr}")
            reason = instr.get("reason_for_call", "")
            if reason:
                parts.append(f"Reason for call: {reason}")
            known = instr.get("known_info", "")
            if known:
                parts.append(f"Known info: {known}")
            unknown = instr.get("unknown_info", "")
            if unknown:
                parts.append(f"Unknown info: {unknown}")

        persona = scenario.get("persona")
        if persona:
            parts.append(f"Persona: {json.dumps(persona, ensure_ascii=False)}")

        return "\n\n".join(parts) if parts else json.dumps(scenario, ensure_ascii=False)

    @staticmethod
    def _flatten_expected_outputs(criteria: Any) -> list[str]:
        """Flatten evaluation_criteria into a list of expected strings.

        Excludes ``reward_basis`` (meta-categories like "DB", "COMMUNICATE")
        and ``actions`` (handled separately via tool-call matching).
        """
        if not criteria:
            return []
        if isinstance(criteria, str):
            return [criteria]
        if isinstance(criteria, list):
            return [str(e) for e in criteria if e]

        # criteria is a dict with keys like actions, communicate_info, nl_assertions.
        parts: list[str] = []
        for key, value in criteria.items():
            if key in ("reward_basis",):
                continue  # meta-categories, not expected outputs
            if key == "actions":
                # Actions are expected tool calls — handled via tool-call matching.
                continue
            if isinstance(value, str) and value:
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item:
                        parts.append(item)
                    elif isinstance(item, dict):
                        name = item.get("name", "")
                        if name:
                            args = item.get("arguments", {})
                            parts.append(f"{name}({json.dumps(args, ensure_ascii=False)})")
        return parts

    @staticmethod
    def _flatten_expected_actions(criteria: Any) -> list[dict]:
        """Extract expected tool-call actions from evaluation_criteria.

        Returns a list of dicts with ``name`` and ``arguments`` keys.
        """
        if not criteria or not isinstance(criteria, dict):
            return []
        actions = criteria.get("actions", [])
        if not isinstance(actions, list):
            return []
        result: list[dict] = []
        for item in actions:
            if isinstance(item, dict) and item.get("name"):
                result.append({
                    "name": item["name"],
                    "arguments": item.get("arguments", {}),
                })
        return result

    @staticmethod
    def _build_domain_tools(tasks_file: Path) -> list[dict]:
        """Build tool schemas from task evaluation criteria.

        Extracts unique tool names and their parameter signatures from
        the ``actions`` field in ``evaluation_criteria``, then generates
        proper Anthropic tool-use schemas.
        """
        with open(tasks_file, encoding="utf-8") as f:
            tasks = json.load(f)

        # Collect unique (tool_name -> {param_name -> set_of_example_values})
        tool_params: dict[str, dict[str, type]] = {}
        for t in tasks:
            for a in t.get("evaluation_criteria", {}).get("actions", []):
                name = a.get("name", "")
                if not name:
                    continue
                args = a.get("arguments", {})
                if name not in tool_params:
                    tool_params[name] = {}
                for pname, pval in args.items():
                    if pname not in tool_params[name]:
                        tool_params[name][pname] = type(pval)

        # Also check db.json for entity keys that imply lookup tools
        db_file = tasks_file.parent / "db.json"
        db: dict = {}
        if db_file.exists():
            with open(db_file, encoding="utf-8") as f:
                db = json.load(f)
        else:
            # Try db.toml for telecom domain
            toml_file = tasks_file.parent / "db.toml"
            if toml_file.exists():
                import tomllib
                with open(toml_file, "rb") as f:
                    db = tomllib.load(f)

        # Generate schemas
        tools: list[dict] = []
        for name, params in sorted(tool_params.items()):
            props: dict[str, Any] = {}
            required: list[str] = []
            for pname, ptype in params.items():
                type_str = "string"
                if ptype == int:
                    type_str = "integer"
                elif ptype == float:
                    type_str = "number"
                elif ptype == bool:
                    type_str = "boolean"
                props[pname] = {"type": type_str}
                required.append(pname)

            tools.append({
                "name": name,
                "description": f"Call the {name} tool.",
                "input_schema": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })

        return tools

    # ------------------------------------------------------------------
    # Fallback dataset loader (for testing without tau2_bench)
    # ------------------------------------------------------------------

    @staticmethod
    def load_dataset_from_json(path: str) -> list[dict]:
        """Load tasks from a local JSON file.

        Useful when ``tau2_bench`` is not installed.  The JSON file should
        be a list of dicts with keys:
        ``task_id``, ``instruction``, ``tools``, ``expected_outputs``.
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [
            {
                "task_id": t.get("task_id", str(i)),
                "instruction": t.get("instruction", ""),
                "domain": t.get("domain", "unknown"),
                "tools": t.get("tools", []),
                "expected_outputs": t.get("expected_outputs", []),
                "metadata": t.get("metadata", {}),
            }
            for i, t in enumerate(data)
        ]

    # ------------------------------------------------------------------
    # Policy loading
    # ------------------------------------------------------------------

    def _load_policy(self, domain: str) -> str:
        """Load the domain policy markdown file."""
        fname = self._POLICY_FILES.get(domain)
        if not fname:
            return ""
        policy_path = self.data_dir / "domains" / domain / fname
        if policy_path.exists():
            return policy_path.read_text(encoding="utf-8")
        return ""

    def _load_domain_db(self, domain: str) -> dict | None:
        """Load domain database (db.json or db.toml) for realistic simulation."""
        db_json = self.data_dir / "domains" / domain / "db.json"
        if db_json.exists():
            try:
                return json.loads(db_json.read_text(encoding="utf-8"))
            except Exception:
                return None
        db_toml = self.data_dir / "domains" / domain / "db.toml"
        if db_toml.exists():
            try:
                import tomllib
                with open(db_toml, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    # Single-task execution
    # ------------------------------------------------------------------

    def run_task(
        self,
        agent: BaseAgent,
        task: dict,
        mcp_client: Any = None,
    ) -> dict:
        """Run a single tau2-bench task through *agent*.

        Strategy by agent type:
        - **TraditionalAgent** (get_tools() returns None): Inject domain
          tools, patch run_turn to handle tool calls by recording them.
        - **OntoSkillsAgent** (has MCP tools): Merge domain tools with
          MCP tools.  Route: MCP tool names -> MCP client, domain tools
          -> recorded/acknowledged.

        Parameters
        ----------
        agent:
            A BaseAgent subclass instance.
        task:
            Task dict from ``load_dataset``.
        mcp_client:
            Optional MCPClient instance for OntoSkillsAgent.  If None and
            the agent has MCP tools, MCP tool calls will return errors.

        Returns
        -------
        dict with ``task_id``, ``model_answer``, ``tool_calls_recorded``,
        ``metrics`` (AgentResult).
        """
        domain_tools = task.get("tools", [])
        domain_tool_names = {t["name"] for t in domain_tools} if domain_tools else set()

        # Record tool calls made during this task.
        recorded_tool_calls: list[dict] = []

        # Load domain DB for realistic tool simulation.
        db_data = self._load_domain_db(task.get("domain", ""))

        # Build the task prompt with domain policy and tool-use instructions.
        prompt = task["instruction"]
        domain = task.get("domain", "")
        policy = self._load_policy(domain)

        tool_list = ", ".join(sorted(domain_tool_names)) if domain_tool_names else "none"
        tool_instructions = (
            f"\n\nIMPORTANT: You have the following tools available: [{tool_list}].\n"
            "You MUST call at least one of these tools to look up information before "
            "providing your final answer.\n"
            "Do NOT guess or fabricate information — always call the appropriate tool first.\n"
            "For example, if the user mentions a user ID, call get_user_details first. "
            "If they mention a reservation, call get_reservation_details first.\n"
            "After gathering information via tools, follow the policy to respond.\n"
            "Your first response should be a tool call, not a direct answer."
        )

        if policy:
            prompt = (
                f"You are a customer service agent for a {domain} company.\n"
                f"Follow this policy strictly:\n\n{policy}\n\n"
                f"---\n\n{prompt}"
                f"{tool_instructions}"
            )
        else:
            prompt += tool_instructions

        # -- Determine if agent has MCP tools (OntoSkillsAgent) ----------
        agent_tools = agent.get_tools()
        has_mcp = agent_tools is not None and any(
            t.get("name") in _MCP_TOOL_NAMES for t in agent_tools
        )

        # -- Patching strategy ------------------------------------------
        original_get_tools = agent.get_tools
        original_get_system_prompt = agent.get_system_prompt
        original_run_turn = agent.run_turn

        if not has_mcp:
            # TraditionalAgent path: no MCP tools, inject domain tools.
            self._patch_traditional(
                agent, domain_tools, domain_tool_names,
                recorded_tool_calls, db_data,
            )
        else:
            # OntoSkillsAgent path: when domain policy is loaded,
            # remove MCP tools entirely — they add token overhead
            # without benefit when the policy covers all needed knowledge.
            self._patch_ontoskills(
                agent, domain_tools, domain_tool_names,
                recorded_tool_calls, mcp_client, db_data,
                domain_only=bool(policy),
            )

        try:
            # Pre-fetch skill knowledge for OntoSkillsAgent with MCP.
            # Skip when domain policy is already loaded — it's redundant
            # and just adds token overhead without improving accuracy.
            prefetched = ""
            if (
                has_mcp
                and mcp_client is not None
                and mcp_client._proc is not None
                and not policy  # only prefetch when no domain policy
                and hasattr(agent, "prefetch_skills")
            ):
                try:
                    prefetched = agent.prefetch_skills(prompt)
                    if prefetched:
                        agent._prefetched_knowledge = prefetched
                        logger.info(
                            "Pre-fetched %d chars for %s (no policy)",
                            len(prefetched), task["task_id"],
                        )
                except Exception as exc:
                    logger.warning("Prefetch failed for %s: %s",
                                   task["task_id"], exc)

            # Custom run-loop for both agent types.
            # Avoids calling agent.run() because:
            # 1. OntoSkillsAgent.run() clears _prefetched_knowledge,
            #    which wastes the prefetch done above.
            # 2. It double-starts the MCP subprocess.
            messages: list[dict] = [{"role": "user", "content": prompt}]
            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0

            for _ in range(15):
                assistant_msg, metrics = agent.run_turn(messages)
                turns += 1
                total_input += metrics["input_tokens"]
                total_output += metrics["output_tokens"]
                total_latency_ms += metrics["latency_ms"]
                total_tool_calls += metrics["tool_calls"]

                tool_use_blocks = [
                    b for b in (assistant_msg.get("content") or [])
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]

                if tool_use_blocks:
                    # run_turn already appended assistant_msg + tool_results.
                    pass
                else:
                    messages.append(assistant_msg)
                    break

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
                    if answer.strip():
                        break

            result = AgentResult(
                answer=answer,
                input_tokens=total_input,
                output_tokens=total_output,
                total_latency_ms=total_latency_ms,
                tool_calls=total_tool_calls,
                turns=turns,
            )

        except Exception as exc:
            logger.warning(
                "Agent error on task %s: %s", task["task_id"], exc
            )
            result = AgentResult(
                answer=f"[Agent error: {exc}]",
                input_tokens=0,
                output_tokens=0,
                total_latency_ms=0.0,
                tool_calls=0,
                turns=0,
            )
        finally:
            # Restore original methods.
            agent.get_tools = original_get_tools  # type: ignore[assignment]
            agent.get_system_prompt = original_get_system_prompt  # type: ignore[assignment]
            agent.run_turn = original_run_turn  # type: ignore[assignment]
            # Clear pre-fetched knowledge.
            if hasattr(agent, "_prefetched_knowledge"):
                agent._prefetched_knowledge = ""

        return {
            "task_id": task["task_id"],
            "model_answer": result.answer,
            "tool_calls_recorded": recorded_tool_calls,
            "metrics": result,
        }

    # ------------------------------------------------------------------
    # Patching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _patch_traditional(
        agent: BaseAgent,
        domain_tools: list[dict],
        domain_tool_names: set[str],
        recorded_tool_calls: list[dict],
        db_data: dict | None = None,
    ) -> None:
        """Patch a TraditionalAgent to inject domain tools."""

        original_get_tools = agent.get_tools
        original_get_system_prompt = agent.get_system_prompt
        original_run_turn = agent.run_turn

        tool_list = ", ".join(sorted(domain_tool_names)) if domain_tool_names else "none"

        def _patched_system_prompt() -> str:
            return (
                "You are a customer service agent with access to the following "
                f"tools: [{tool_list}].\n\n"
                "IMPORTANT RULES:\n"
                "1. ALWAYS call the appropriate tool FIRST before answering.\n"
                "2. Do NOT ask the user for information you can look up yourself.\n"
                "3. Use tool results to provide accurate, policy-compliant responses.\n"
                "4. Be professional and helpful.\n"
                "5. If you need to perform an action (cancel, refund, book, etc.), "
                "call the tool — do not just describe what you would do."
            )

        def _patched_get_tools() -> list[dict] | None:
            base_tools = original_get_tools()
            if base_tools is None:
                return list(domain_tools)
            names = {t["name"] for t in base_tools}
            extra = [t for t in domain_tools if t["name"] not in names]
            return [*base_tools, *extra]

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            """Execute one turn with domain tool handling."""
            start = time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000

            # Build assistant message from response content blocks.
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

            # Handle tool_use blocks.
            tool_calls = 0
            tool_result_blocks: list[dict] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                # Record the tool call.
                recorded_tool_calls.append({
                    "name": tool_name,
                    "input": tool_input,
                })

                if tool_name in domain_tool_names:
                    # Simulate a realistic tool response using real DB data.
                    result_text = _simulate_tool_response(
                        tool_name, tool_input, domain_tool_names,
                        db_data=db_data,
                    )
                    is_error = False
                else:
                    result_text = f"Error: unknown tool {tool_name}"
                    is_error = True

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_text,
                    "is_error": is_error,
                })

            # Append assistant + tool_result messages in correct order.
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

        agent.get_tools = _patched_get_tools  # type: ignore[assignment]
        agent.get_system_prompt = _patched_system_prompt  # type: ignore[assignment]
        agent.run_turn = _patched_run_turn  # type: ignore[assignment]

    @staticmethod
    def _patch_ontoskills(
        agent: BaseAgent,
        domain_tools: list[dict],
        domain_tool_names: set[str],
        recorded_tool_calls: list[dict],
        mcp_client: Any,
        db_data: dict | None = None,
        *,
        domain_only: bool = False,
    ) -> None:
        """Patch an OntoSkillsAgent to merge MCP + domain tools.

        Tool routing:
        - MCP tool names -> dispatch to mcp_client (or error if None)
        - Domain tool names -> record and acknowledge
        - Unknown tools -> error

        When *domain_only* is True, MCP tool schemas are removed and only
        domain tools are provided.  Used when the domain policy already
        covers all needed knowledge.
        """

        original_get_tools = agent.get_tools
        original_get_system_prompt = agent.get_system_prompt
        original_run_turn = agent.run_turn

        tool_list = ", ".join(sorted(domain_tool_names)) if domain_tool_names else "none"

        def _patched_get_tools() -> list[dict] | None:
            if domain_only:
                return list(domain_tools) if domain_tools else None
            base_tools = original_get_tools()
            if base_tools is None:
                return list(domain_tools)
            names = {t["name"] for t in base_tools}
            extra = [t for t in domain_tools if t["name"] not in names]
            return [*base_tools, *extra]

        def _patched_system_prompt() -> str:
            return (
                "You are a customer service agent with access to the following "
                f"tools: [{tool_list}].\n\n"
                "IMPORTANT RULES:\n"
                "1. ALWAYS call the appropriate tool FIRST before answering.\n"
                "2. Do NOT ask the user for information you can look up yourself.\n"
                "3. Use tool results to provide accurate, policy-compliant responses.\n"
                "4. Be professional and helpful.\n"
                "5. If you need to perform an action (cancel, refund, book, etc.), "
                "call the tool — do not just describe what you would do."
            )

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            """Execute one turn with MCP + domain tool routing."""
            start = time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000

            # Build assistant message from response content blocks.
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

            # Handle tool_use blocks with routing.
            tool_calls = 0
            tool_result_blocks: list[dict] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                if tool_name in _MCP_TOOL_NAMES:
                    # Route to MCP client.
                    recorded_tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                    })
                    if mcp_client is not None:
                        try:
                            mcp_result = mcp_client.call_tool(
                                tool_name, tool_input
                            )
                            result_text = json.dumps(
                                mcp_result, ensure_ascii=False
                            )
                            is_error = False
                        except Exception as exc:
                            result_text = (
                                f"Error calling MCP tool {tool_name}: {exc}"
                            )
                            is_error = True
                    else:
                        result_text = (
                            f"Error: MCP tool {tool_name} called but no "
                            f"MCP client available."
                        )
                        is_error = True

                elif tool_name in domain_tool_names:
                    # Record domain tool call.
                    recorded_tool_calls.append({
                        "name": tool_name,
                        "input": tool_input,
                    })
                    result_text = _simulate_tool_response(
                        tool_name, tool_input, domain_tool_names,
                        db_data=db_data,
                    )
                    is_error = False

                else:
                    result_text = f"Error: unknown tool {tool_name}"
                    is_error = True

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_text,
                    "is_error": is_error,
                })

            # Append assistant + tool_result messages in correct order.
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

        agent.get_tools = _patched_get_tools  # type: ignore[assignment]
        agent.get_system_prompt = _patched_system_prompt  # type: ignore[assignment]
        agent.run_turn = _patched_run_turn  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Full benchmark run
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        agent: BaseAgent,
        domain: str = "airline",
        split: str = "test",
        max_tasks: int | None = None,
        mcp_client: Any = None,
        shuffle: bool = True,
        seed: int = 42,
    ) -> list[dict]:
        """Run all (or *max_tasks*) tau2-bench tasks through *agent*.

        Parameters
        ----------
        agent:
            A BaseAgent subclass instance.
        domain:
            tau2-bench domain (e.g. ``"airline"``, ``"retail"``).
        split:
            Dataset split (e.g. ``"test"``, ``"validation"``).
        max_tasks:
            Limit on the number of tasks to run.
        mcp_client:
            Optional MCPClient for OntoSkillsAgent.  If None and the agent
            has MCP tools, the wrapper will start the MCP subprocess.
        shuffle:
            Shuffle tasks before selection (default True).
        seed:
            Random seed for shuffling (default 42).

        Returns a list of result dicts (one per task).
        """
        import random

        tasks = self.load_dataset(domain=domain, split=split)
        if shuffle:
            random.Random(seed).shuffle(tasks)
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        # Start MCP once for OntoSkillsAgent if not provided.
        from benchmark.agents.traditional import TraditionalAgent
        is_traditional = isinstance(agent, TraditionalAgent)

        own_mcp = False
        if not is_traditional and mcp_client is None and hasattr(agent, "_mcp_client"):
            mcp_client = agent._mcp_client
            mcp_client.__enter__()
            mcp_client.initialize()
            own_mcp = True

        results: list[dict] = []
        try:
            for i, task in enumerate(tasks, 1):
                tid = task["task_id"]
                logger.info("Task %d/%d: %s", i, len(tasks), tid)
                try:
                    result = self.run_task(agent, task, mcp_client=mcp_client)
                except Exception:
                    logger.exception("Task %s failed", tid)
                    result = {
                        "task_id": tid,
                        "model_answer": "",
                        "tool_calls_recorded": [],
                        "metrics": None,
                    }
                results.append(result)
        finally:
            if own_mcp:
                try:
                    mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

        return results

    # ------------------------------------------------------------------
    # Scoring (simplified string matching)
    # ------------------------------------------------------------------

    @staticmethod
    def score(
        results: list[dict],
        expected_by_task: dict[str, list[str]],
        *,
        expected_actions_by_task: dict[str, list[dict]] | None = None,
        case_insensitive: bool = True,
        strip_whitespace: bool = True,
    ) -> dict:
        """Score results against expected outputs using string + action matching.

        Two scoring dimensions:
        1. **Text matching**: ``model_answer`` checked against expected text
           strings (nl_assertions, communicate_info).
        2. **Action matching**: ``tool_calls_recorded`` checked against
           expected tool-call actions.

        A task is correct if it satisfies **both** dimensions (when present).

        Parameters
        ----------
        results:
            List of result dicts from ``run_benchmark`` / ``run_task``.
        expected_by_task:
            Mapping of ``task_id`` -> list of expected output strings.
        expected_actions_by_task:
            Mapping of ``task_id`` -> list of expected action dicts
            (``{"name": ..., "arguments": {...}}``).
        case_insensitive:
            Compare lowercased strings.
        strip_whitespace:
            Strip leading/trailing whitespace before comparing.

        Returns
        -------
        dict with ``accuracy`` (float 0-1), ``correct``, ``total``,
        and ``per_task`` details.
        """
        if expected_actions_by_task is None:
            expected_actions_by_task = {}

        per_task: list[dict] = []
        correct = 0
        total = 0

        for r in results:
            task_id = r["task_id"]
            model_answer = r.get("model_answer", "")
            expected_list = expected_by_task.get(task_id, [])
            expected_actions = expected_actions_by_task.get(task_id, [])
            recorded_calls = r.get("tool_calls_recorded", [])

            has_text = bool(expected_list)
            has_actions = bool(expected_actions)

            if not has_text and not has_actions:
                per_task.append({
                    "task_id": task_id,
                    "model_answer": model_answer,
                    "expected_outputs": expected_list,
                    "expected_actions": expected_actions,
                    "correct": None,
                })
                continue

            total += 1
            text_ok = True
            actions_ok = True

            # Check text matching.
            if has_text:
                text_ok = _check_match(
                    model_answer,
                    expected_list,
                    case_insensitive=case_insensitive,
                    strip_whitespace=strip_whitespace,
                )

            # Check action matching.
            if has_actions:
                actions_ok = _check_actions(recorded_calls, expected_actions)

            match = text_ok and actions_ok
            if match:
                correct += 1

            per_task.append({
                "task_id": task_id,
                "model_answer": model_answer,
                "expected_outputs": expected_list,
                "expected_actions": [
                    f"{a['name']}({json.dumps(a.get('arguments', {}))})"
                    for a in expected_actions
                ],
                "recorded_tool_calls": [
                    f"{c['name']}({json.dumps(c.get('input', {}))})"
                    for c in recorded_calls
                ],
                "text_match": text_ok,
                "actions_match": actions_ok,
                "correct": match,
            })

        accuracy = correct / total if total > 0 else 0.0
        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "per_task": per_task,
        }

    # ------------------------------------------------------------------
    # pass^k metric
    # ------------------------------------------------------------------

    @staticmethod
    def compute_pass_k(
        results_per_trial: list[list[dict]],
        expected_by_task: dict[str, list[str]],
        k: int = 1,
        *,
        case_insensitive: bool = True,
        strip_whitespace: bool = True,
    ) -> float:
        """Compute the pass^k metric.

        ``pass^k = average over tasks of C(successes, k) / C(trials, k)``

        Parameters
        ----------
        results_per_trial:
            List of trial result lists.  Each inner list is the output of
            ``run_benchmark`` for a single trial run.
        expected_by_task:
            Mapping of ``task_id`` -> list of expected output strings.
        k:
            The ``k`` in pass^k.  Must be >= 1 and <= number of trials.

        Returns
        -------
        float
            The pass^k score in [0, 1].
        """
        n_trials = len(results_per_trial)
        if n_trials == 0:
            return 0.0
        if k < 1 or k > n_trials:
            raise ValueError(
                f"k must be between 1 and {n_trials}, got {k}"
            )

        # Collect task IDs from all trials.
        all_task_ids: list[str] = []
        if results_per_trial[0]:
            all_task_ids = [
                r["task_id"] for r in results_per_trial[0]
            ]

        pass_k_values: list[float] = []
        for task_id in all_task_ids:
            successes = 0
            for trial_results in results_per_trial:
                # Find the result for this task in this trial.
                task_result = next(
                    (r for r in trial_results if r["task_id"] == task_id),
                    None,
                )
                if task_result is None:
                    continue
                expected_list = expected_by_task.get(task_id, [])
                if expected_list and _check_match(
                    task_result.get("model_answer", ""),
                    expected_list,
                    case_insensitive=case_insensitive,
                    strip_whitespace=strip_whitespace,
                ):
                    successes += 1

            # pass^k = C(successes, k) / C(n_trials, k)
            if successes >= k:
                pass_k_values.append(comb(successes, k) / comb(n_trials, k))
            else:
                pass_k_values.append(0.0)

        return sum(pass_k_values) / len(pass_k_values) if pass_k_values else 0.0

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    @staticmethod
    def write_results(results: list[dict], output_path: str) -> None:
        """Write results as JSON (list of result dicts)."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        def _default(obj):
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=_default)

        logger.info("Wrote %d results to %s", len(results), path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_match(
    answer: str,
    expected_list: list[str],
    *,
    case_insensitive: bool = True,
    strip_whitespace: bool = True,
) -> bool:
    """Check if *answer* matches any string in *expected_list*.

    Three strategies:
    1. Substring containment: the answer contains an expected string.
    2. Keyword matching: extract key content words from behavioral
       assertions and check they appear in the answer.
    3. Semantic synonym matching for common patterns (refuse/cannot/unable,
       cancel/cancellation, compensate/compensation, etc.).
    """
    import re as _re

    a = answer
    if strip_whitespace:
        a = a.strip()
    if case_insensitive:
        a_cmp = a.lower()
    else:
        a_cmp = a

    for exp in expected_list:
        e = exp
        if strip_whitespace:
            e = e.strip()
        if case_insensitive:
            e_cmp = e.lower()
        else:
            e_cmp = e

        # Exact match or substring containment.
        if a_cmp == e_cmp or e_cmp in a_cmp:
            return True

        # Keyword matching for behavioral assertions.
        keywords = _extract_keywords(e_cmp)
        if not keywords:
            continue

        # Check if at least half the keywords (rounded up) appear in answer
        # or their synonyms do.
        _SYNONYMS = {
            "refuse": {"refuse", "cannot", "can't", "unable", "not able", "won't", "will not", "not possible"},
            "cancel": {"cancel", "cancellation"},
            "cancellation": {"cancel", "cancellation"},
            "compensation": {"compensation", "compensate", "voucher", "refund", "credit"},
            "compensate": {"compensation", "compensate", "voucher", "refund", "credit"},
            "delay": {"delay", "delayed", "late"},
            "delayed": {"delay", "delayed", "late"},
            "approve": {"approve", "confirm", "process"},
            "deny": {"deny", "refuse", "reject", "decline"},
            "offer": {"offer", "provide", "give", "propose"},
            "upgrade": {"upgrade", "upgraded"},
            "check": {"check", "verify", "confirm", "look up", "review"},
            "detect": {"detect", "find", "discover", "notice", "realize", "identify"},
            "realize": {"realize", "notice", "discover", "find", "detect"},
        }
        matched_kw = 0
        for kw in keywords:
            kw_stem = kw.rstrip(".,;:!?")
            synonyms = _SYNONYMS.get(kw_stem, {kw_stem})
            if any(s in a_cmp for s in synonyms):
                matched_kw += 1

        threshold = max(1, (len(keywords) + 1) // 2)
        if matched_kw >= threshold:
            return True

    return False


def _extract_keywords(text: str) -> list[str]:
    """Extract key content words from a behavioral assertion string."""
    import re as _re

    _STOP = frozenset({
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need",
        "must", "ought", "to", "of", "at", "by", "for", "with",
        "from", "in", "on", "up", "out", "into", "that", "this",
        "these", "those", "and", "but", "or", "not", "if", "it",
        "its", "agent", "user", "should", "unless", "actually",
        "also", "proceed", "unless", "indeed", "unless",
    })

    words = _re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in _STOP and len(w) > 2]


def _check_actions(
    recorded: list[dict],
    expected: list[dict],
) -> bool:
    """Check if recorded tool calls cover the expected actions.

    An expected action matches if any recorded call has the same tool name
    and the expected arguments are a subset of the recorded arguments.
    """
    if not expected:
        return True

    matched = 0
    for exp in expected:
        exp_name = exp.get("name", "")
        exp_args = exp.get("arguments", {})
        for rec in recorded:
            if rec.get("name") != exp_name:
                continue
            rec_args = rec.get("input", rec.get("arguments", {}))
            # Check that all expected argument key-values are present.
            if all(rec_args.get(k) == v for k, v in exp_args.items()):
                matched += 1
                break

    return matched == len(expected)


def _lookup_db(tool_name: str, tool_input: dict, db_data: dict) -> dict | None:
    """Look up real data from the domain database.

    Searches all top-level collections (users, reservations, flights, etc.)
    for records matching the tool input parameters.
    """
    name_lower = tool_name.lower()
    input_keys = set(tool_input.keys())

    for collection_name, collection in db_data.items():
        if not isinstance(collection, dict):
            continue

        # Try to match by ID fields in the tool input.
        for key, val in tool_input.items():
            if not isinstance(val, str) or not val:
                continue
            record = collection.get(val)
            if isinstance(record, dict):
                return record

    # Try searching within collection values for partial matches.
    for collection_name, collection in db_data.items():
        if not isinstance(collection, dict):
            continue
        for record_id, record in collection.items():
            if not isinstance(record, dict):
                continue
            # Check if record matches tool input fields.
            match = True
            for key, val in tool_input.items():
                if isinstance(val, str) and val:
                    rec_val = record.get(key)
                    if rec_val is not None and str(rec_val).lower() == val.lower():
                        continue
                    # Also check nested fields.
                    found = False
                    for v in record.values():
                        if isinstance(v, dict) and v.get(key) is not None:
                            if str(v[key]).lower() == val.lower():
                                found = True
                                break
                        elif isinstance(v, str) and v.lower() == val.lower():
                            found = True
                            break
                    if not found:
                        match = False
                        break
            if match:
                return record

    return None


def _simulate_tool_response(
    tool_name: str,
    tool_input: dict,
    available_tools: set[str],
    *,
    db_data: dict | None = None,
) -> str:
    """Generate a realistic tool response using real DB data when available.

    Falls back to deterministic mock data when no DB data is found.
    """
    # Try real DB lookup first.
    if db_data:
        result = _lookup_db(tool_name, tool_input, db_data)
        if result is not None:
            return json.dumps(result, ensure_ascii=False)

    import random as _random

    # Seed from tool name + input for deterministic responses within a task.
    seed = hash(f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}")
    rng = _random.Random(seed)

    # Detect what kind of tool this is by name or input keys.
    name_lower = tool_name.lower()
    input_keys = set(tool_input.keys())

    if any(k in input_keys for k in ("user_id", "customer_id")) or "user" in name_lower:
        uid = tool_input.get("user_id", tool_input.get("customer_id", "user_001"))
        return json.dumps({
            "user_id": uid,
            "name": rng.choice(["John Smith", "Jane Doe", "Alex Johnson", "Maria Garcia", "Wei Chen"]),
            "email": f"{uid.replace('_', '.')}{rng.choice(['@email.com', '@gmail.com'])}",
            "membership_tier": rng.choice(["regular", "silver", "gold", "platinum"]),
            "account_status": "active",
        })

    if any(k in input_keys for k in ("reservation_id", "booking_id")) or "reservation" in name_lower or "booking" in name_lower:
        rid = tool_input.get("reservation_id", tool_input.get("booking_id", "RES001"))
        return json.dumps({
            "reservation_id": rid,
            "status": rng.choice(["confirmed", "pending", "cancelled", "completed"]),
            "cabin_class": rng.choice(["economy", "business", "first"]),
            "seat": f"{rng.randint(1, 40)}{rng.choice(['A', 'B', 'C', 'D', 'E', 'F'])}",
            "flight_date": "2024-05-20",
            "departure": rng.choice(["JFK", "LAX", "ORD", "SFO", "ATL"]),
            "arrival": rng.choice(["LHR", "CDG", "NRT", "DXB", "SYD"]),
        })

    if "flight" in name_lower or "schedule" in name_lower:
        return json.dumps({
            "flight_number": f"{rng.choice(['AA', 'UA', 'DL', 'BA'])}{rng.randint(100, 999)}",
            "departure": "2024-05-20T08:00:00",
            "arrival": "2024-05-20T14:00:00",
            "status": rng.choice(["on_time", "delayed", "cancelled"]),
            "gate": f"{rng.choice(['A', 'B', 'C'])}{rng.randint(1, 30)}",
        })

    if "cancel" in name_lower or "refund" in name_lower:
        return json.dumps({
            "status": "processed",
            "confirmation": f"CONF-{rng.randint(100000, 999999)}",
            "refund_amount": f"${rng.randint(50, 500)}.{rng.randint(0, 99):02d}",
        })

    if "payment" in name_lower or "pay" in name_lower:
        return json.dumps({
            "payment_status": "success",
            "transaction_id": f"TXN-{rng.randint(100000, 999999)}",
            "amount_charged": f"${rng.randint(50, 1000)}.{rng.randint(0, 99):02d}",
        })

    if "transfer" in name_lower:
        return json.dumps({
            "status": "transferred",
            "agent_id": f"AGENT-{rng.randint(100, 999)}",
        })

    # Generic response for unknown tool types.
    return json.dumps({
        "status": "success",
        "tool": tool_name,
        "parameters_received": tool_input,
        "result": "Operation completed successfully.",
    })
