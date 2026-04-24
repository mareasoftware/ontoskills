"""Per-package benchmark wrapper.

Runs tasks scoped to a specific skill package (e.g. superpowers) through
both TraditionalAgent (loads only matching SKILL.md files) and
OntoSkillsAgent (uses MCP search to find relevant skills dynamically).

Each task presents a realistic coding scenario where a specific skill
(or small set of skills) would be relevant.  The agent must demonstrate
knowledge of the skill's procedures, rules, and patterns.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task definitions: realistic scenarios mapped to superpowers skills
# ---------------------------------------------------------------------------

SUPERPOWERS_TASKS: list[dict[str, Any]] = [
    {
        "task_id": "sp-tdd-01",
        "skill_ids": ["test-driven-development"],
        "question": (
            "I need to implement a function that validates email addresses. "
            "It should accept standard formats (user@domain.com), reject "
            "obviously invalid inputs, and handle edge cases like '+' in "
            "local parts. Walk me through the TDD approach for this."
        ),
        "expected_keywords": [
            "red", "green", "refactor",
            "test first", "failing test",
            "assert",
        ],
    },
    {
        "task_id": "sp-debug-01",
        "skill_ids": ["systematic-debugging"],
        "question": (
            "My web app returns a 500 error intermittently when users submit "
            "a form. The logs show a NullPointerException sometimes. The form "
            "has required and optional fields. How should I systematically "
            "debug this?"
        ),
        "expected_keywords": [
            "reproduce", "hypothesis",
            "root cause",
            "binary search",
            "narrow",
        ],
    },
    {
        "task_id": "sp-plan-01",
        "skill_ids": ["writing-plans"],
        "question": (
            "I need to add user authentication to an existing Express.js app. "
            "It should support email/password login, OAuth2 with Google, "
            "session management, and password reset. Help me write an "
            "implementation plan."
        ),
        "expected_keywords": [
            "step", "phase",
            "prerequisite",
            "dependency",
            "verification",
        ],
    },
    {
        "task_id": "sp-review-01",
        "skill_ids": ["requesting-code-review", "receiving-code-review"],
        "question": (
            "I just finished implementing a caching layer for our API. "
            "It uses an in-memory LRU cache with TTL expiration. The PR has "
            "about 200 lines of changes. How should I request and handle "
            "code review for this?"
        ),
        "expected_keywords": [
            "context", "testing",
            "edge case",
            "review",
            "feedback",
        ],
    },
    {
        "task_id": "sp-worktree-01",
        "skill_ids": ["using-git-worktrees"],
        "question": (
            "I'm working on a feature branch but need to urgently fix a bug "
            "on main. I don't want to stash or lose my current work. "
            "How should I handle this with git worktrees?"
        ),
        "expected_keywords": [
            "worktree",
            "branch",
            "isolate",
            "switch",
            "merge",
        ],
    },
    {
        "task_id": "sp-parallel-01",
        "skill_ids": ["dispatching-parallel-agents", "subagent-driven-development"],
        "question": (
            "I have a large refactoring task: renaming a core interface "
            "across 50+ files, updating all imports, and fixing affected "
            "tests. How can I parallelize this work using multiple agents?"
        ),
        "expected_keywords": [
            "parallel",
            "agent",
            "dispatch",
            "isolate",
            "batch",
        ],
    },
    {
        "task_id": "sp-brainstorm-01",
        "skill_ids": ["brainstorming"],
        "question": (
            "We need to design a real-time notification system for our app. "
            "Users should get notified about mentions, replies, and system "
            "events. We need to support web, mobile push, and email channels. "
            "Help me brainstorm the architecture."
        ),
        "expected_keywords": [
            "websocket", "push",
            "queue",
            "channel",
            "scalab",
        ],
    },
    {
        "task_id": "sp-verify-01",
        "skill_ids": ["verification-before-completion"],
        "question": (
            "I think I've finished implementing the user profile page. "
            "It shows user info, allows editing, and has an avatar upload. "
            "What should I verify before marking this task complete?"
        ),
        "expected_keywords": [
            "test", "edge case",
            "error",
            "responsive",
            "accessib",
        ],
    },
]


class PerPackageWrapper:
    """Per-package benchmark wrapper.

    Parameters
    ----------
    skills_dir:
        Root directory containing SKILL.md files for the traditional agent.
    """

    def __init__(self, skills_dir: str = ".agents/skills") -> None:
        self.skills_dir = Path(skills_dir)

    # ------------------------------------------------------------------
    # Task loading
    # ------------------------------------------------------------------

    def load_tasks(
        self,
        package: str = "superpowers",
    ) -> list[dict]:
        """Load pre-defined tasks for a specific package.

        Currently only ``superpowers`` is supported.
        """
        if package == "superpowers":
            return list(SUPERPOWERS_TASKS)
        raise ValueError(
            f"Package {package!r} not supported. Only 'superpowers' is available."
        )

    # ------------------------------------------------------------------
    # Single-task execution
    # ------------------------------------------------------------------

    def run_task(
        self,
        agent: BaseAgent,
        task: dict,
    ) -> dict:
        """Run a single per-package task through *agent*.

        Returns a dict with:
        ``task_id``, ``model_answer``, ``metrics`` (AgentResult).
        """
        prompt = task["question"]

        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

        # Check if agent has MCP tools.
        agent_tools = agent.get_tools()
        has_mcp = agent_tools is not None and any(
            t.get("name") in ("search", "get_skill_context")
            for t in agent_tools
        )

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            """Execute one turn, routing MCP tool calls to MCP client."""
            start = time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000

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

            tool_calls = 0
            tool_result_blocks: list[dict] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                if has_mcp and hasattr(agent, "_mcp_client") and agent._mcp_client._proc is not None:
                    try:
                        mcp_result = agent._mcp_client.call_tool(
                            tool_name, tool_input
                        )
                        result_text = json.dumps(
                            mcp_result, ensure_ascii=False
                        )
                        is_error = False
                    except Exception as exc:
                        result_text = f"Error calling MCP tool {tool_name}: {exc}"
                        is_error = True
                else:
                    result_text = f"Error: tool {tool_name} not available"
                    is_error = True

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_text,
                    "is_error": is_error,
                })

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

        agent.get_tools = original_get_tools  # no tool schema changes needed
        agent.run_turn = _patched_run_turn

        try:
            # Start MCP lifecycle if OntoSkillsAgent.
            _mcp_started = False
            if has_mcp and hasattr(agent, "_mcp_client"):
                agent._mcp_client.__enter__()
                agent._mcp_client.initialize()
                _mcp_started = True

            # Custom run-loop.
            messages: list[dict] = [{"role": "user", "content": prompt}]
            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0

            for _ in range(10):
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
                    pass  # run_turn already appended
                else:
                    messages.append(assistant_msg)
                    break

            # Extract final answer.
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

            result = AgentResult(
                answer=answer,
                input_tokens=total_input,
                output_tokens=total_output,
                total_latency_ms=total_latency_ms,
                tool_calls=total_tool_calls,
                turns=turns,
                context_overflow=False,
            )
        except Exception as exc:
            logger.warning("Agent error on task %s: %s", task["task_id"], exc)
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
            agent.get_tools = original_get_tools
            agent.run_turn = original_run_turn
            if _mcp_started:
                try:
                    agent._mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

        return {
            "task_id": task["task_id"],
            "model_answer": result.answer,
            "metrics": result,
        }

    # ------------------------------------------------------------------
    # Full benchmark run
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        agent: BaseAgent,
        package: str = "superpowers",
        max_tasks: int | None = None,
    ) -> list[dict]:
        """Run all (or *max_tasks*) per-package tasks through *agent*.

        For TraditionalAgent, creates a fresh agent per task that loads
        only the 1-2 relevant SKILL.md files (simulating realistic usage
        where an agent loads skills on-demand, not all at once).

        For OntoSkillsAgent, reuses the same agent (MCP search finds
        relevant skills dynamically).
        """
        tasks = self.load_tasks(package=package)
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        # Detect agent type.
        from benchmark.agents.traditional import TraditionalAgent
        is_traditional = isinstance(agent, TraditionalAgent)

        results: list[dict] = []
        for i, task in enumerate(tasks, 1):
            logger.info("Task %d/%d: %s", i, len(tasks), task["task_id"])

            task_agent = agent
            if is_traditional:
                # Create a scoped agent that loads only relevant skills.
                task_agent = self._make_scoped_traditional_agent(
                    agent.model, task.get("skill_ids", []),
                )

            try:
                result = self.run_task(task_agent, task)
            except Exception:
                logger.exception("Task %s failed", task["task_id"])
                result = {
                    "task_id": task["task_id"],
                    "model_answer": "",
                    "metrics": None,
                }
            results.append(result)

        return results

    def _make_scoped_traditional_agent(
        self, model: str, skill_ids: list[str],
    ) -> BaseAgent:
        """Create a TraditionalAgent that loads only the specified skills.

        Each skill_id like "test-driven-development" maps to
        ``<skills_dir>/obra/superpowers/<skill_id>/SKILL.md``.
        """
        from benchmark.agents.traditional import TraditionalAgent

        # Build a temporary skills dict with only the relevant files.
        scoped_skills: dict[str, str] = {}
        for sid in skill_ids:
            skill_file = self.skills_dir / "obra" / "superpowers" / sid / "SKILL.md"
            if skill_file.exists():
                scoped_skills[f"obra/superpowers/{sid}"] = skill_file.read_text(encoding="utf-8")

        # Create agent and override its skills.
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        agent = TraditionalAgent.__new__(TraditionalAgent)
        BaseAgent.__init__(agent, model=model, api_key=api_key)
        agent.skills = scoped_skills
        agent._context_overflow = False
        agent._system_prompt = agent._build_system_prompt()
        return agent

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score(results: list[dict], tasks: list[dict]) -> dict:
        """Score results using keyword matching.

        Each task has ``expected_keywords``; the answer must contain at
        least half of them (case-insensitive).
        """
        keyword_map = {t["task_id"]: t.get("expected_keywords", []) for t in tasks}

        per_task: list[dict] = []
        total = 0
        keyword_hits = 0
        total_keywords = 0

        for r in results:
            task_id = r["task_id"]
            answer = (r.get("model_answer") or "").lower()
            keywords = keyword_map.get(task_id, [])

            if not keywords:
                per_task.append({
                    "task_id": task_id,
                    "keywords_matched": [],
                    "keywords_total": 0,
                    "passed": None,
                })
                continue

            total += 1
            total_keywords += len(keywords)
            matched = [kw for kw in keywords if kw.lower() in answer]
            keyword_hits += len(matched)

            # Pass if at least half the keywords are present.
            passed = len(matched) >= len(keywords) / 2

            per_task.append({
                "task_id": task_id,
                "keywords_matched": matched,
                "keywords_total": len(keywords),
                "keywords_missing": [kw for kw in keywords if kw.lower() not in answer],
                "passed": passed,
            })

        pass_rate = sum(1 for t in per_task if t.get("passed")) / total if total > 0 else 0.0
        keyword_coverage = keyword_hits / total_keywords if total_keywords > 0 else 0.0

        return {
            "pass_rate": pass_rate,
            "keyword_coverage": keyword_coverage,
            "tasks_passed": sum(1 for t in per_task if t.get("passed")),
            "total_tasks": total,
            "per_task": per_task,
        }
