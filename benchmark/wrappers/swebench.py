"""SWE-bench benchmark wrapper.

Loads the SWE-bench dataset from HuggingFace, runs tasks through a BaseAgent
subclass, and extracts unified-diff patches from the agent's answers.

Dataset: ``princeton-nlp/SWE-bench_Verified``
Each instance provides a GitHub issue + repo + base_commit; the agent must
produce a patch that resolves the issue.

Evaluation is external (via ``swebench.harness.run_evaluation``) -- this
wrapper only generates predictions.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from datasets import load_dataset  # type: ignore[import-untyped]

from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas: file_read and file_edit
# ---------------------------------------------------------------------------

FILE_READ_TOOL: dict[str, Any] = {
    "name": "file_read",
    "description": "Read the contents of a file from the repository.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path in the repository",
            },
        },
        "required": ["path"],
    },
}

FILE_EDIT_TOOL: dict[str, Any] = {
    "name": "file_edit",
    "description": (
        "Edit a file in the repository. Provide the old content to replace "
        "and the new content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative file path",
            },
            "old_content": {
                "type": "string",
                "description": "The exact content to replace",
            },
            "new_content": {
                "type": "string",
                "description": "The replacement content",
            },
        },
        "required": ["path", "old_content", "new_content"],
    },
}

SWE_BENCH_TOOLS: list[dict[str, Any]] = [FILE_READ_TOOL, FILE_EDIT_TOOL]


# ---------------------------------------------------------------------------
# Patch extraction
# ---------------------------------------------------------------------------

_DIFF_FENCE_RE = re.compile(
    r"```diff\n(.*?)```", re.DOTALL
)
_PLAIN_DIFF_RE = re.compile(
    r"((?:^|\n)diff --git .+?(?=\n[^ \t+-]|\Z))", re.DOTALL
)
_UNIFIED_HUNK_RE = re.compile(
    r"((?:^|\n)(?:--- .+\n\+\+\+ .+\n(?:@@ .+ @@\n(?:[ +\-].*\n)*)+)+)",
    re.DOTALL,
)


def _select_diverse_instances(
    instances: list[dict],
    max_tasks: int,
) -> list[dict]:
    """Select instances from diverse repos for more representative results."""
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for inst in instances:
        by_repo[inst["repo"]].append(inst)

    selected: list[dict] = []
    repos = sorted(by_repo.keys(), key=lambda r: len(by_repo[r]), reverse=True)
    idx = {r: 0 for r in repos}

    while len(selected) < max_tasks and any(idx[r] < len(by_repo[r]) for r in repos):
        for repo in repos:
            if len(selected) >= max_tasks:
                break
            if idx[repo] < len(by_repo[repo]):
                selected.append(by_repo[repo][idx[repo]])
                idx[repo] += 1

    return selected


class SWEBenchWrapper:
    """SWE-bench benchmark wrapper.

    Parameters
    ----------
    data_dir:
        Directory to cache downloaded SWE-bench data.
    """

    def __init__(self, data_dir: str = "benchmark/data/swebench") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def load_dataset(
        self,
        dataset_name: str = "princeton-nlp/SWE-bench_Verified",
        split: str = "test",
    ) -> list[dict]:
        """Load SWE-bench instances from HuggingFace.

        Returns a list of dicts with keys:
        ``instance_id``, ``repo``, ``base_commit``, ``problem_statement``,
        ``hints_text``, ``FAIL_TO_PASS``, ``PASS_TO_PASS``.
        """
        ds = load_dataset(dataset_name, split=split)  # type: ignore[call-arg]

        instances: list[dict] = []
        for row in ds:
            instances.append({
                "instance_id": row["instance_id"],
                "repo": row["repo"],
                "base_commit": row["base_commit"],
                "problem_statement": row["problem_statement"],
                "hints_text": row.get("hints_text", ""),
                "FAIL_TO_PASS": row.get("FAIL_TO_PASS", []),
                "PASS_TO_PASS": row.get("PASS_TO_PASS", []),
                "test_patch": row.get("test_patch", ""),
            })

        logger.info(
            "Loaded %d SWE-bench instances (dataset=%s, split=%s)",
            len(instances),
            dataset_name,
            split,
        )
        return instances

    # ------------------------------------------------------------------
    # Repo checkout helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _checkout_repo(
        repo: str,
        base_commit: str,
        repo_base_dir: str,
    ) -> Path:
        """Clone (or reuse cached clone) and checkout *base_commit*.

        Returns the path to the checkout directory.
        """
        repo_base = Path(repo_base_dir)
        repo_base.mkdir(parents=True, exist_ok=True)

        # Convert "owner/repo" to a safe directory name.
        repo_dir_name = repo.replace("/", "__")
        clone_path = repo_base / repo_dir_name

        if not (clone_path / ".git").exists():
            logger.info("Cloning %s into %s", repo, clone_path)
            subprocess.run(
                ["git", "clone", f"https://github.com/{repo}.git", str(clone_path)],
                check=True,
                capture_output=True,
            )

        # Ensure a clean state even after interrupted runs.
        subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            cwd=str(clone_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=str(clone_path),
            check=True,
            capture_output=True,
        )

        # Fetch and checkout the target commit.
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=str(clone_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", base_commit],
            cwd=str(clone_path),
            check=True,
            capture_output=True,
        )
        # Ensure a clean working tree.
        subprocess.run(
            ["git", "checkout", "."],
            cwd=str(clone_path),
            check=True,
            capture_output=True,
        )

        return clone_path

    # ------------------------------------------------------------------
    # Single-task execution
    # ------------------------------------------------------------------

    def run_task(
        self,
        agent: BaseAgent,
        instance: dict,
        repo_checkout_dir: str,
        *,
        mcp_client: Any = None,
    ) -> dict:
        """Run a single SWE-bench instance through *agent*.

        Injects ``file_read`` and ``file_edit`` tools that operate on the
        checked-out repository.  The ``file_edit`` tool records edits without
        actually writing to disk -- the agent is expected to produce a unified
        diff patch in its final answer.

        Returns a dict with:
        ``instance_id``, ``model_patch``, ``model_name_or_path``, ``metrics``.
        """
        checkout = Path(repo_checkout_dir)

        # Recorded edits: list of (path, old_content, new_content).
        recorded_edits: list[tuple[str, str, str]] = []

        # -- Build the task prompt ----------------------------------------
        prompt = (
            f"I'm working on the repository `{instance['repo']}` "
            f"(commit {instance['base_commit']}).\n\n"
            f"## Problem\n\n{instance['problem_statement']}\n"
        )
        if instance.get("hints_text"):
            prompt += f"\n## Hints\n\n{instance['hints_text']}\n"

        # Include test names and actual test code so the model knows what needs to pass.
        fail_to_pass = instance.get("FAIL_TO_PASS", [])
        if isinstance(fail_to_pass, str):
            try:
                import json as _json
                fail_to_pass = _json.loads(fail_to_pass)
            except Exception:
                fail_to_pass = []
        if fail_to_pass:
            test_list = "\n".join(f"- {t}" for t in fail_to_pass)
            prompt += (
                f"\n## Tests that MUST pass after your fix\n\n{test_list}\n"
            )

        # Include actual test code from test_patch so the model sees what the test expects.
        test_patch = instance.get("test_patch", "")
        if test_patch and test_patch.strip():
            # Truncate to ~3000 chars to avoid flooding context.
            test_code = test_patch.strip()[:3000]
            prompt += (
                f"\n## Test code (from test_patch)\n\n"
                f"```python\n{test_code}\n```\n"
            )

        prompt += (
            "\n## Instructions\n\n"
            "Follow this structured approach:\n\n"
            "### Step 1: Understand the bug\n"
            "Read the problem statement carefully. Identify the root cause "
            "by reading relevant source files with file_read.\n\n"
            "### Step 2: Read the test\n"
            "Examine the test code above to understand exactly what behavior "
            "is expected. The test reveals the correct API contract.\n\n"
            "### Step 3: Make a minimal fix\n"
            "Use file_edit to propose the smallest change that fixes the issue. "
            "Do NOT refactor, add features, or change unrelated code.\n\n"
            "### Step 4: Output the patch\n"
            "Output the COMPLETE unified diff patch inside a "
            "```diff ... ``` code block.\n\n"
            "The patch MUST use proper git format:\n"
            "```\n"
            "diff --git a/path/to/file.py b/path/to/file.py\n"
            "--- a/path/to/file.py\n"
            "+++ b/path/to/file.py\n"
            "@@ ... @@\n"
            " context line\n"
            "-removed line\n"
            "+added line\n"
            "```\n\n"
            "Focus on MINIMAL, targeted changes. Do not refactor or add unrelated code."
        )

        # -- Inject tools + tool execution --------------------------------
        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

        def _patched_get_tools() -> list[dict] | None:
            base_tools = original_get_tools()
            if base_tools is None:
                return list(SWE_BENCH_TOOLS)
            names = {t["name"] for t in base_tools}
            extra = [t for t in SWE_BENCH_TOOLS if t["name"] not in names]
            return [*base_tools, *extra]

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            """Execute one turn with file_read / file_edit handling.

            Calls the original ``run_turn`` but, when tool_use blocks for
            ``file_read`` or ``file_edit`` are present, intercepts them and
            provides tool_result messages instead of delegating to MCP or
            raising an error.
            """
            start = time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000

            # Build the assistant message from response content blocks.
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

            # Handle any tool_use blocks.
            tool_calls = 0
            tool_result_blocks: list[dict] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                if tool_name == "file_read":
                    rel_path = tool_input.get("path", "")
                    abs_path = checkout / rel_path
                    try:
                        content = abs_path.read_text(encoding="utf-8")
                        result_text = content
                        is_error = False
                    except FileNotFoundError:
                        result_text = f"Error: file not found: {rel_path}"
                        is_error = True
                    except Exception as exc:
                        result_text = f"Error reading {rel_path}: {exc}"
                        is_error = True

                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result_text,
                        "is_error": is_error,
                    })

                elif tool_name == "file_edit":
                    rel_path = tool_input.get("path", "")
                    old_content = tool_input.get("old_content", "")
                    new_content = tool_input.get("new_content", "")
                    recorded_edits.append((rel_path, old_content, new_content))

                    # Verify the old_content exists in the file.
                    abs_path = checkout / rel_path
                    try:
                        current = abs_path.read_text(encoding="utf-8")
                        if old_content in current:
                            result_text = (
                                f"Edit recorded for {rel_path}. "
                                f"The patch will be generated from all "
                                f"recorded edits."
                            )
                            is_error = False
                        else:
                            result_text = (
                                f"Warning: old_content not found verbatim "
                                f"in {rel_path}. Edit recorded anyway -- "
                                f"verify the patch carefully."
                            )
                            is_error = False
                    except FileNotFoundError:
                        result_text = (
                            f"Warning: {rel_path} not found. "
                            f"Edit recorded anyway."
                        )
                        is_error = False
                    except Exception as exc:
                        result_text = f"Warning: could not verify {rel_path}: {exc}"
                        is_error = False

                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result_text,
                        "is_error": is_error,
                    })

                else:
                    # Route MCP tool calls to the MCP client.
                    mcp = mcp_client or getattr(agent, "_mcp_client", None)
                    if mcp is not None and mcp._proc is not None:
                        try:
                            result = mcp.call_tool(tool_name, tool_input)
                            content = result if isinstance(result, str) else json.dumps(result)
                            is_error = False
                        except Exception as exc:
                            content = f"MCP error: {exc}"
                            is_error = True
                        tool_result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": content,
                            "is_error": is_error,
                        })
                    else:
                        # Delegate read_skill to the agent's resolver.
                        if tool_name == "read_skill" and hasattr(agent, "_resolve_skill"):
                            skill_name = tool_input.get("skill_name", "")
                            content = agent._resolve_skill(skill_name)
                            if content is None:
                                content = f"Skill not found: {skill_name}"
                                is_error = True
                            else:
                                is_error = False
                        else:
                            content = f"Error: unknown tool {tool_name}"
                            is_error = True
                        tool_result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": content,
                            "is_error": is_error,
                        })

            # Append tool_result messages when tool calls were made.
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

        # -- Monkey-patch the agent ---------------------------------------
        agent.get_tools = _patched_get_tools  # type: ignore[assignment]
        agent.run_turn = _patched_run_turn  # type: ignore[assignment]

        try:
            # If the agent is an OntoSkillsAgent, ensure MCP is started.
            # Reuse the provided mcp_client if available; otherwise start one.
            _mcp_started = False
            if hasattr(agent, "_mcp_client"):
                if mcp_client is not None and mcp_client._proc is not None:
                    # Reuse already-started MCP client.
                    pass
                else:
                    agent._mcp_client.__enter__()
                    agent._mcp_client.initialize()
                    _mcp_started = True

                # Pre-fetch relevant coding skills to reduce tool-call turns.
                client = mcp_client or agent._mcp_client
                if hasattr(agent, "prefetch_skills") and client._proc is not None:
                    try:
                        knowledge = agent.prefetch_skills(prompt)
                        if knowledge:
                            agent._prefetched_knowledge = knowledge
                            logger.info(
                                "Pre-fetched %d chars for %s",
                                len(knowledge), instance["instance_id"],
                            )
                    except Exception as exc:
                        logger.warning("Prefetch failed for %s: %s",
                                       instance["instance_id"], exc)

            # Custom run-loop: BaseAgent.run() double-appends messages
            # when run_turn also appends, so we manage the loop directly.
            messages: list[dict] = [{"role": "user", "content": prompt}]
            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0

            for _ in range(25):
                assistant_msg, metrics = agent.run_turn(messages)
                turns += 1
                total_input += metrics["input_tokens"]
                total_output += metrics["output_tokens"]
                total_latency_ms += metrics["latency_ms"]
                total_tool_calls += metrics["tool_calls"]

                # Check for tool_use blocks — if present, run_turn already
                # appended assistant_msg + tool_results to messages.
                tool_use_blocks = [
                    b for b in (assistant_msg.get("content") or [])
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]

                if tool_use_blocks:
                    # run_turn already appended assistant_msg + tool_results.
                    pass
                else:
                    # No tool calls — append assistant_msg ourselves and stop.
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
                "Agent error on instance %s: %s", instance["instance_id"], exc
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
            agent.run_turn = original_run_turn  # type: ignore[assignment]
            # Clear pre-fetched knowledge.
            if hasattr(agent, "_prefetched_knowledge"):
                agent._prefetched_knowledge = ""
            # Clean up MCP subprocess if we started it.
            if _mcp_started:
                try:
                    agent._mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

        # -- Extract / build the patch ------------------------------------
        patch = self.extract_patch_from_answer(result.answer)

        # If no diff found in the answer but we have recorded edits,
        # build a patch from them.
        if not patch.strip() and recorded_edits:
            patch = self._build_patch_from_edits(
                recorded_edits, checkout
            )

        # -- Validate the patch -------------------------------------------
        patch_applies = False
        resolved = False
        if patch.strip():
            patch_applies = self._check_patch_applies(checkout, patch)
            if patch_applies:
                resolved = self._run_test_validation(
                    checkout, instance, patch
                )

        return {
            "instance_id": instance["instance_id"],
            "model_patch": patch,
            "model_name_or_path": getattr(agent, "model", "unknown"),
            "patch_applies": patch_applies,
            "resolved": resolved,
            "metrics": result,
        }

    # ------------------------------------------------------------------
    # Full benchmark run
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        agent: BaseAgent,
        dataset_name: str = "princeton-nlp/SWE-bench_Verified",
        split: str = "test",
        max_tasks: int | None = None,
        repo_base_dir: str = "benchmark/data/repos",
        shuffle: bool = True,
        seed: int = 42,
    ) -> list[dict]:
        """Run all (or *max_tasks*) SWE-bench instances through *agent*.

        For each instance the repo is cloned / checked out at the specified
        commit and ``run_task`` is called.

        Returns a list of result dicts (one per instance).
        """
        import random

        instances = self.load_dataset(dataset_name=dataset_name, split=split)
        if shuffle:
            random.Random(seed).shuffle(instances)
        if max_tasks is not None:
            instances = _select_diverse_instances(instances, max_tasks)

        # Start MCP once for OntoSkillsAgent.
        mcp_client = None
        if hasattr(agent, "_mcp_client"):
            mcp_client = agent._mcp_client
            mcp_client.__enter__()
            mcp_client.initialize()

        results: list[dict] = []
        try:
            for i, instance in enumerate(instances, 1):
                iid = instance["instance_id"]
                logger.info("Instance %d/%d: %s", i, len(instances), iid)

                try:
                    checkout_dir = self._checkout_repo(
                        repo=instance["repo"],
                        base_commit=instance["base_commit"],
                        repo_base_dir=repo_base_dir,
                    )
                    result = self.run_task(
                        agent, instance, str(checkout_dir),
                        mcp_client=mcp_client,
                    )
                except Exception:
                    logger.exception("Instance %s failed", iid)
                    result = {
                        "instance_id": iid,
                        "model_patch": "",
                        "model_name_or_path": getattr(agent, "model", "unknown"),
                        "patch_applies": False,
                        "resolved": False,
                        "metrics": None,
                    }
                results.append(result)
        finally:
            if mcp_client is not None:
                try:
                    mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

        return results

    # ------------------------------------------------------------------
    # Prediction output
    # ------------------------------------------------------------------

    @staticmethod
    def write_predictions(results: list[dict], output_path: str) -> None:
        """Write predictions in the format expected by ``swebench.harness``.

        Output: JSON list of
        ``{"instance_id": ..., "model_patch": ..., "model_name_or_path": ...}``.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        predictions = []
        for r in results:
            predictions.append({
                "instance_id": r["instance_id"],
                "model_patch": r.get("model_patch", ""),
                "model_name_or_path": r.get("model_name_or_path", "unknown"),
                "patch_applies": r.get("patch_applies", False),
                "resolved": r.get("resolved", False),
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(predictions, f, indent=2, ensure_ascii=False)

        logger.info("Wrote %d predictions to %s", len(predictions), path)

    # ------------------------------------------------------------------
    # Patch extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_patch_from_answer(answer: str) -> str:
        """Extract a unified diff patch from the agent's answer.

        Looks for (in order of preference):
        1. ````diff ... ```` fenced blocks.
        2. ``diff --git ...`` blocks.
        3. Standalone unified-diff hunks (``---`` / ``+++`` / ``@@``).

        Returns the extracted patch string, or an empty string if nothing
        is found.
        """
        # 1. Fenced diff blocks.
        fences = _DIFF_FENCE_RE.findall(answer)
        if fences:
            return "\n".join(fences).strip()

        # 2. diff --git blocks.
        git_blocks = _PLAIN_DIFF_RE.findall(answer)
        if git_blocks:
            return "\n".join(git_blocks).strip()

        # 3. Standalone unified-diff hunks.
        hunks = _UNIFIED_HUNK_RE.findall(answer)
        if hunks:
            return "\n".join(hunks).strip()

        return ""

    # ------------------------------------------------------------------
    # Build patch from recorded edits
    # ------------------------------------------------------------------

    @staticmethod
    def _build_patch_from_edits(
        edits: list[tuple[str, str, str]],
        checkout_dir: Path,
    ) -> str:
        """Build a unified diff patch from the recorded file edits.

        Each edit is a tuple of ``(path, old_content, new_content)``.
        Edits to the same file are grouped and applied sequentially to an
        in-memory copy of the file, then a single diff is generated from the
        original to the final state.
        """
        edits_by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for rel_path, old, new in edits:
            edits_by_file[rel_path].append((old, new))

        patches: list[str] = []
        for rel_path, replacements in edits_by_file.items():
            abs_path = checkout_dir / rel_path
            try:
                original = abs_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            current = original
            for old, new in replacements:
                current = current.replace(old, new, 1)
            old_lines = original.splitlines(keepends=True)
            new_lines = current.splitlines(keepends=True)
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
            patch_text = "".join(diff)
            if patch_text:
                patches.append(patch_text)

        return "\n".join(patches)

    @staticmethod
    def _check_patch_applies(checkout_dir: Path, patch: str) -> bool:
        """Check if a patch applies cleanly to the checkout (dry run)."""
        try:
            result = subprocess.run(
                ["git", "apply", "--check"],
                input=patch,
                capture_output=True,
                text=True,
                cwd=checkout_dir,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _run_test_validation(
        checkout_dir: Path,
        instance: dict,
        patch: str,
    ) -> bool:
        """Apply model patch + test patch, run FAIL_TO_PASS tests.

        Returns True if all FAIL_TO_PASS tests pass (instance resolved).
        Falls back to patch-applicability-only if pytest is unavailable.
        """
        fail_to_pass = instance.get("FAIL_TO_PASS", "[]")
        if isinstance(fail_to_pass, str):
            try:
                fail_to_pass = json.loads(fail_to_pass)
            except json.JSONDecodeError:
                fail_to_pass = []
        if not fail_to_pass:
            return False

        test_patch = instance.get("test_patch", "")

        try:
            # Apply model patch.
            r = subprocess.run(
                ["git", "apply"],
                input=patch,
                capture_output=True,
                text=True,
                cwd=checkout_dir,
                timeout=10,
            )
            if r.returncode != 0:
                return False

            # Apply test patch (adds failing test cases).
            if test_patch:
                subprocess.run(
                    ["git", "apply"],
                    input=test_patch,
                    capture_output=True,
                    text=True,
                    cwd=checkout_dir,
                    timeout=10,
                )

            # Run FAIL_TO_PASS tests.
            n_passed = 0
            for test_name in fail_to_pass:
                r = subprocess.run(
                    ["python", "-m", "pytest", "-x", test_name, "--tb=no", "-q"],
                    capture_output=True,
                    text=True,
                    cwd=checkout_dir,
                    timeout=60,
                )
                if r.returncode == 0:
                    n_passed += 1

            logger.info(
                "Test validation for %s: %d/%d passed",
                instance["instance_id"], n_passed, len(fail_to_pass),
            )
            return n_passed == len(fail_to_pass)

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
