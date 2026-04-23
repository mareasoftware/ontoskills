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

    _VALID_DOMAINS = ("mock", "airline", "retail", "telecom", "banking_knowledge")

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
        """Load tau2-bench tasks.

        Each task dict contains:
        ``task_id``, ``instruction``, ``domain``, ``tools`` (list of tool
        schemas), ``expected_outputs`` (list of expected response strings).

        Raises ``ImportError`` if ``tau2_bench`` is not installed.
        """
        if not _HAS_TAU2:
            raise ImportError(
                "tau2_bench is not installed. Install it with: "
                "pip install tau2-bench"
            )

        if domain not in self._VALID_DOMAINS:
            raise ValueError(
                f"Invalid domain {domain!r}. "
                f"Choose from {self._VALID_DOMAINS}"
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

        # Build the task prompt.
        prompt = task["instruction"]

        # -- Determine if agent has MCP tools (OntoSkillsAgent) ----------
        agent_tools = agent.get_tools()
        has_mcp = agent_tools is not None and any(
            t.get("name") in _MCP_TOOL_NAMES for t in agent_tools
        )

        # -- Patching strategy ------------------------------------------
        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

        if not has_mcp:
            # TraditionalAgent path: no MCP tools, inject domain tools.
            self._patch_traditional(
                agent, domain_tools, domain_tool_names,
                recorded_tool_calls,
            )
        else:
            # OntoSkillsAgent path: merge MCP + domain tools.
            self._patch_ontoskills(
                agent, domain_tools, domain_tool_names,
                recorded_tool_calls, mcp_client,
            )

        try:
            if has_mcp:
                # OntoSkillsAgent overrides run() for MCP lifecycle.
                # Use the agent's own run() -- the patched run_turn handles
                # tool routing.
                result: AgentResult = agent.run(prompt, max_turns=15)
            else:
                # TraditionalAgent: use BaseAgent.run() with patched methods.
                result = BaseAgent.run(agent, prompt, max_turns=15)
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
                context_overflow=False,
            )
        finally:
            # Restore original methods.
            agent.get_tools = original_get_tools  # type: ignore[assignment]
            agent.run_turn = original_run_turn  # type: ignore[assignment]

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
    ) -> None:
        """Patch a TraditionalAgent to inject domain tools."""

        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

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
                    # Acknowledge the domain tool call.
                    result_text = (
                        f"Tool {tool_name} called successfully. "
                        f"Parameters: {json.dumps(tool_input)}"
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

            # Append tool_result messages when tool calls were made.
            if tool_result_blocks:
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
        agent.run_turn = _patched_run_turn  # type: ignore[assignment]

    @staticmethod
    def _patch_ontoskills(
        agent: BaseAgent,
        domain_tools: list[dict],
        domain_tool_names: set[str],
        recorded_tool_calls: list[dict],
        mcp_client: Any,
    ) -> None:
        """Patch an OntoSkillsAgent to merge MCP + domain tools.

        Tool routing:
        - MCP tool names -> dispatch to mcp_client (or error if None)
        - Domain tool names -> record and acknowledge
        - Unknown tools -> error
        """

        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

        def _patched_get_tools() -> list[dict] | None:
            base_tools = original_get_tools()
            if base_tools is None:
                return list(domain_tools)
            names = {t["name"] for t in base_tools}
            extra = [t for t in domain_tools if t["name"] not in names]
            return [*base_tools, *extra]

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
                    result_text = (
                        f"Tool {tool_name} called successfully. "
                        f"Parameters: {json.dumps(tool_input)}"
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

            # Append tool_result messages when tool calls were made.
            if tool_result_blocks:
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
            Optional MCPClient for OntoSkillsAgent.

        Returns a list of result dicts (one per task).
        """
        tasks = self.load_dataset(domain=domain, split=split)
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        results: list[dict] = []
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

        return results

    # ------------------------------------------------------------------
    # Scoring (simplified string matching)
    # ------------------------------------------------------------------

    @staticmethod
    def score(
        results: list[dict],
        expected_by_task: dict[str, list[str]],
        *,
        case_insensitive: bool = True,
        strip_whitespace: bool = True,
    ) -> dict:
        """Score results against expected outputs using string matching.

        Parameters
        ----------
        results:
            List of result dicts from ``run_benchmark`` / ``run_task``.
        expected_by_task:
            Mapping of ``task_id`` -> list of expected output strings.
        case_insensitive:
            Compare lowercased strings.
        strip_whitespace:
            Strip leading/trailing whitespace before comparing.

        Returns
        -------
        dict with ``accuracy`` (float 0-1), ``correct``, ``total``,
        and ``per_task`` details.
        """
        per_task: list[dict] = []
        correct = 0
        total = 0

        for r in results:
            task_id = r["task_id"]
            model_answer = r.get("model_answer", "")
            expected_list = expected_by_task.get(task_id, [])

            if not expected_list:
                match = None  # no expected output available
            else:
                total += 1
                match = _check_match(
                    model_answer,
                    expected_list,
                    case_insensitive=case_insensitive,
                    strip_whitespace=strip_whitespace,
                )
                if match:
                    correct += 1

            per_task.append({
                "task_id": task_id,
                "model_answer": model_answer,
                "expected_outputs": expected_list,
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

        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

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

    Uses substring containment: the answer contains at least one expected
    output string (or vice-versa for shorter expected strings).
    """
    a = answer
    if strip_whitespace:
        a = a.strip()
    for exp in expected_list:
        e = exp
        if strip_whitespace:
            e = e.strip()
        if case_insensitive:
            a_cmp = a.lower()
            e_cmp = e.lower()
        else:
            a_cmp = a
            e_cmp = e
        # Exact match or substring containment.
        if a_cmp == e_cmp or e_cmp in a_cmp:
            return True
    return False
