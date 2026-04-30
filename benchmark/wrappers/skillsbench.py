"""SkillsBench benchmark wrapper — deterministic Docker-based evaluation.

Loads tasks from a local clone of benchflow-ai/skillsbench, has the agent
generate a complete Python solution script, executes it inside the task's
Docker container (via podman), then runs the task's pytest test suite for
deterministic scoring.

This matches the official SkillsBench evaluation methodology:
  1. Build Docker image from task's environment/Dockerfile
  2. Agent generates a solution script (same role as solve.sh)
  3. Execute the solution inside the container
  4. Run tests/test.sh (pytest verification)
  5. Read /logs/verifier/ctrf.json for fractional scoring (passed/total)
  6. Fall back to reward.txt (binary 0/1) if no CTRF report

Requires: podman (or docker) for container execution.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from benchmark.agents.utils import extract_python_code
from typing import Any

from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# Tasks with exotic base images that likely won't build on a standard machine.
_SKIP_TASKS = {
    "fix-build-agentops",       # bugswarm/cached-images — needs CI cache
    "fix-build-google-auto",    # bugswarm/cached-images — needs CI cache
    "setup-fuzzing-py",         # gcr.io/oss-fuzz-base/base-builder-python
    "suricata-custom-exfil",    # jasonish/suricata:7.0.11
    "fix-erlang-ssh-cve",       # needs Erlang, complex setup
    "organize-messy-files",     # BuildKit heredoc RUN <<'EOF' — Podman doesn't support
    "fix-visual-stability",     # docker-compose: needs API sidecar container
    "scheduling-email-assistant",  # docker-compose: multi-container
    "pedestrian-traffic-counting",  # docker-compose: multi-container
    "pg-essay-to-audiobook",    # docker-compose: multi-container
    "react-performance-debugging",  # docker-compose: multi-container
    "mhc-layer-impl",           # docker-compose: multi-container
}

# Default path to the local SkillsBench repo clone.
DEFAULT_REPO_PATH = "/tmp/skillsbench_full"

# Container runtime command.
_PODMAN = "podman"


def _parse_toml_simple(text: str) -> dict:
    """Parse simple TOML (flat sections, no nested tables)."""
    result: dict = {}
    current_section = result
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1].strip()
            parts = section_name.split(".")
            current_section = result
            for part in parts:
                if part not in current_section:
                    current_section[part] = {}
                current_section = current_section[part]
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()

        # Strip inline comment (TOML # comment after value).
        # But only outside quoted strings.
        if not value.startswith(('"', "'", "[")):
            if " #" in value:
                value = value[: value.index(" #")].rstrip()
            elif "\t#" in value:
                value = value[: value.index("\t#")].rstrip()

        if value.startswith('"') and value.endswith('"'):
            current_section[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            current_section[key] = value[1:-1]
        elif value.startswith("["):
            items = re.findall(r'["\']([^"\']+)["\']', value)
            current_section[key] = items
        elif value in ("true", "false"):
            current_section[key] = value == "true"
        else:
            try:
                current_section[key] = float(value) if "." in value else int(value)
            except ValueError:
                current_section[key] = value
    return result


class SkillsBenchWrapper:
    """SkillsBench wrapper with deterministic Docker-based evaluation.

    Parameters
    ----------
    repo_path:
        Path to the local clone of benchflow-ai/skillsbench (must have
        ``tasks/`` directory with per-task Dockerfiles and tests).
    """

    def __init__(self, repo_path: str = DEFAULT_REPO_PATH) -> None:
        self.repo_path = Path(repo_path)
        self.tasks_dir = self.repo_path / "tasks"

    # ------------------------------------------------------------------
    # Task loading (from local repo clone)
    # ------------------------------------------------------------------

    def _load_task_from_repo(self, task_id: str) -> dict | None:
        """Load a single task from the local repo clone."""
        task_dir = self.tasks_dir / task_id
        if not task_dir.is_dir():
            return None

        # Read metadata.
        toml_path = task_dir / "task.toml"
        metadata = {}
        if toml_path.exists():
            metadata = _parse_toml_simple(toml_path.read_text(encoding="utf-8"))
        meta = metadata.get("metadata", {})

        # Read instruction.
        instr_path = task_dir / "instruction.md"
        instruction = instr_path.read_text(encoding="utf-8") if instr_path.exists() else ""

        # Read Dockerfile (for prompt context).
        dockerfile_path = task_dir / "environment" / "Dockerfile"
        dockerfile = dockerfile_path.read_text(encoding="utf-8") if dockerfile_path.exists() else ""

        # Read skills.
        skill_ids: list[str] = []
        skills_content: dict[str, str] = {}
        skills_dir = task_dir / "environment" / "skills"
        if skills_dir.is_dir():
            for skill_dir in sorted(skills_dir.iterdir()):
                if skill_dir.is_dir():
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        skill_ids.append(skill_dir.name)
                        skills_content[skill_dir.name] = skill_md.read_text(encoding="utf-8")

        # Read test.sh (for context, though we'll run it inside container).
        test_sh_path = task_dir / "tests" / "test.sh"
        test_sh = test_sh_path.read_text(encoding="utf-8") if test_sh_path.exists() else ""

        # Read test file for prompt injection.
        test_py_path = task_dir / "tests" / "test_outputs.py"
        test_content = test_py_path.read_text(encoding="utf-8") if test_py_path.exists() else ""

        agent_meta = metadata.get("agent", {})

        return {
            "task_id": task_id,
            "difficulty": meta.get("difficulty", "unknown"),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "instruction": instruction,
            "dockerfile": dockerfile,
            "test_sh": test_sh,
            "test_content": test_content,
            "skill_ids": skill_ids,
            "skills_content": skills_content,
            "task_dir": str(task_dir),
            "agent_timeout_sec": int(float(agent_meta.get("timeout_sec", 900))),
        }

    def load_tasks(
        self,
        max_tasks: int | None = None,
        shuffle: bool = True,
        seed: int = 42,
        packages_root: str | None = None,
        skip_first: int = 0,
    ) -> list[dict]:
        """Load SkillsBench tasks from the local repo clone.

        Parameters
        ----------
        packages_root:
            Path to compiled TTL packages (e.g. ``~/.ontoskills/packages``).
            When provided, tasks whose skills are not fully compiled are
            skipped (logged as warnings).
        skip_first:
            Skip the first N tasks after shuffling. Use to continue from
            a previous run (e.g. ``skip_first=10`` to run tasks 11+).
        """
        if not self.tasks_dir.is_dir():
            raise FileNotFoundError(
                f"SkillsBench tasks directory not found: {self.tasks_dir}\n"
                f"Clone the repo first: git clone https://github.com/benchflow-ai/skillsbench {self.repo_path}"
            )

        pkg_root = Path(packages_root) if packages_root else None
        tasks = []
        skipped_missing = 0
        for task_dir in sorted(self.tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            if task_id in _SKIP_TASKS:
                continue
            task = self._load_task_from_repo(task_id)
            if not task or not task["skill_ids"]:
                continue

            # Skip tasks with skills not yet compiled to TTL.
            if pkg_root is not None:
                task_pkg = pkg_root / "skillsbench" / task_id
                missing = [
                    sid for sid in task["skill_ids"]
                    if not (task_pkg / sid / "ontoskill.ttl").exists()
                ]
                if missing:
                    logger.warning(
                        "Skipping %s: skills not compiled: %s",
                        task_id, ", ".join(missing),
                    )
                    skipped_missing += 1
                    continue

            tasks.append(task)

        if skipped_missing:
            logger.info(
                "Skipped %d tasks with uncompiled skills", skipped_missing,
            )
        logger.info("Loaded %d tasks with skills (from %s)", len(tasks), self.repo_path)

        if shuffle:
            random.Random(seed).shuffle(tasks)
        if skip_first > 0:
            tasks = tasks[skip_first:]
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        return tasks

    def load_dataset(self, **kwargs) -> list[dict]:
        """Alias for load_tasks."""
        return self.load_tasks(**kwargs)

    # ------------------------------------------------------------------
    # Docker / podman helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepull_base_images() -> None:
        """Pull common base images to warm the podman cache."""
        base_images = ["ubuntu:24.04", "python:3.12-slim"]
        for img in base_images:
            result = SkillsBenchWrapper._podman_cmd("pull", img, timeout=300)
            if result.returncode == 0:
                logger.info("Pre-pulled base image: %s", img)
            else:
                logger.warning("Failed to pre-pull %s: %s", img, result.stderr[:200])

    def prebuild_images(self, tasks: list[dict], workers: int = 3) -> list[dict]:
        """Pre-build Docker images for all tasks. Returns buildable tasks only."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        buildable: list[dict] = []

        def _build_one(t: dict) -> tuple[dict, bool]:
            image_tag = self._build_image(t["task_id"], t["task_dir"])
            return t, image_tag is not None

        logger.info("Phase 0: Pre-building %d Docker images (%d workers)", len(tasks), workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_build_one, t): t for t in tasks}
            for future in as_completed(futures):
                task, ok = future.result()
                if ok:
                    buildable.append(task)
                else:
                    logger.warning("Phase 0: Skipping %s (image build failed)", task["task_id"])

        logger.info("Phase 0: %d/%d tasks have valid images", len(buildable), len(tasks))
        return buildable

    @staticmethod
    def _podman_cmd(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
        """Run a podman command."""
        cmd = [_PODMAN, *args]
        logger.debug("Running: %s", " ".join(cmd))
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )

    def _build_image(self, task_id: str, task_dir: str) -> str | None:
        """Build the Docker image for a task. Returns image tag or None.

        Reuses existing image if already built (shared between agents).
        """
        image_tag = f"localhost/skillsbench/{task_id}:latest"

        # Check if image already exists (reused across agent runs).
        check = self._podman_cmd("image", "exists", image_tag)
        if check.returncode == 0:
            logger.info("Image %s already exists, reusing", image_tag)
            return image_tag

        env_dir = Path(task_dir) / "environment"
        logger.info("Building image %s from %s...", image_tag, env_dir)
        result = self._podman_cmd(
            "build", "-t", image_tag, "-f", str(env_dir / "Dockerfile"),
            str(env_dir),
        )
        if result.returncode != 0:
            logger.error("Build failed for %s:\n%s", task_id, result.stderr[-500:])
            return None
        logger.info("Built image %s", image_tag)
        return image_tag

    @staticmethod
    def _get_image_tag(task_id: str) -> str | None:
        """Get the Docker image tag for a task (from pre-built images)."""
        tag = f"localhost/skillsbench/{task_id}:latest"
        try:
            result = SkillsBenchWrapper._podman_cmd("image", "exists", tag)
            return tag if result.returncode == 0 else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def _run_solution(
        self,
        image_tag: str,
        task_id: str,
        solution_script: str,
        task_dir: str,
        work_dir: str | None = None,
    ) -> dict:
        """Run the agent's solution script inside the task container, then verify.

        Returns dict with fractional reward (0.0-1.0 from pytest pass rate),
        per-test details, and diagnostic output.
        """
        container_name = f"sb-{task_id}-{int(time.time())}-{os.getpid()}"
        results: dict = {
            "task_id": task_id,
            "reward": 0.0,
            "test_details": [],
            "test_output": "",
            "test_errors": "",
            "build_ok": True,
            "solution_ran": False,
            "tests_ran": False,
        }

        # Collect environment variables from task.toml [solution.env] / [verifier.env].
        task_metadata = {}
        toml_path = Path(task_dir) / "task.toml"
        if toml_path.exists():
            task_metadata = _parse_toml_simple(toml_path.read_text(encoding="utf-8"))
        env_flags: list[str] = []
        for section_key in ("solution.env", "verifier.env"):
            env_section = task_metadata
            for part in section_key.split("."):
                env_section = env_section.get(part, {}) if isinstance(env_section, dict) else {}
            for key, value in env_section.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_name = value[2:-1]
                    env_value = os.environ.get(env_name, "")
                    if env_value:
                        env_flags.extend(["--env", f"{key}={env_value}"])
                    else:
                        logger.warning("Task %s needs env %s but it's not set", task_id, env_name)

        try:
            # Create container with env vars.
            run_args = ["run", "-d", "--name", container_name] + env_flags + [image_tag, "sleep", "3600"]
            run_result = self._podman_cmd(*run_args)
            if run_result.returncode != 0:
                logger.error("Failed to create container for %s: %s", task_id, run_result.stderr)
                results["build_ok"] = False
                return results

            # Copy skills into container at standard agent paths.
            skills_src = Path(task_dir) / "environment" / "skills"
            if skills_src.is_dir():
                for target in [
                    "/root/.claude/skills",
                    "/root/.codex/skills",
                    "/root/.opencode/skill",
                    "/root/.agents/skills",
                ]:
                    self._podman_cmd(
                        "exec", container_name, "mkdir", "-p", target,
                    )
                    self._podman_cmd(
                        "cp", str(skills_src) + "/.", f"{container_name}:{target}/",
                    )

            # Write solution script into container.
            script_path = "/tmp/agent_solution.py"
            # Use podman cp with a temp file.
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(solution_script)
                tmp_script = f.name
            try:
                cp_result = self._podman_cmd("cp", tmp_script, f"{container_name}:{script_path}")
                if cp_result.returncode != 0:
                    logger.error("Failed to copy script to container: %s", cp_result.stderr)
                    return results
            finally:
                os.unlink(tmp_script)

            # Copy skill_scripts into container if present.
            if work_dir:
                scripts_src = Path(work_dir) / "skill_scripts"
                if scripts_src.is_dir():
                    self._podman_cmd(
                        "exec", container_name, "mkdir", "-p", "/tmp/skill_scripts",
                    )
                    self._podman_cmd(
                        "cp", str(scripts_src) + "/.", f"{container_name}:/tmp/skill_scripts/",
                    )

            # Run the solution script.
            logger.info("Running solution for %s...", task_id)
            exec_result = self._podman_cmd(
                "exec", container_name, "python3", script_path,
                timeout=300,
            )
            results["solution_output"] = exec_result.stdout[-2000:] if exec_result.stdout else ""
            results["solution_errors"] = exec_result.stderr[-2000:] if exec_result.stderr else ""
            results["solution_ran"] = True

            if exec_result.returncode != 0:
                logger.warning(
                    "Solution script failed for %s (exit %d):\n%s",
                    task_id, exec_result.returncode, exec_result.stderr[-500:],
                )
                # Don't return — still run tests in case partial output was created.

            # Copy test files into container.
            test_dir = Path(task_dir) / "tests"
            if test_dir.is_dir():
                self._podman_cmd("exec", container_name, "mkdir", "-p", "/tests")
                cp_tests = self._podman_cmd("cp", str(test_dir) + "/.", f"{container_name}:/tests/")
                if cp_tests.returncode != 0:
                    logger.error("Failed to copy tests: %s", cp_tests.stderr)

            # Run test.sh (pytest verification).
            logger.info("Running tests for %s...", task_id)
            test_result = self._podman_cmd(
                "exec", container_name, "bash", "/tests/test.sh",
                timeout=120,
            )
            results["test_output"] = test_result.stdout[-3000:] if test_result.stdout else ""
            results["test_errors"] = test_result.stderr[-3000:] if test_result.stderr else ""
            results["tests_ran"] = True

            # Try fractional scoring from CTRF report (passed/total).
            ctrf_reward, test_details = self._read_ctrf_reward(container_name)
            if ctrf_reward is not None:
                results["reward"] = ctrf_reward
                results["test_details"] = test_details
            else:
                # Fallback: read binary reward.txt.
                results["reward"] = self._read_reward_txt(container_name)

            logger.info(
                "Task %s: reward=%.3f (%s)",
                task_id, results["reward"],
                "PASS" if results["reward"] >= 1.0
                else "PARTIAL" if results["reward"] > 0.0
                else "FAIL",
            )

        except subprocess.TimeoutExpired:
            logger.error("Timeout running container for %s", task_id)
        except Exception as exc:
            logger.exception("Container error for %s: %s", task_id, exc)
        finally:
            # Cleanup container.
            self._podman_cmd("rm", "-f", container_name)

        return results

    def _read_ctrf_reward(self, container_name: str) -> tuple[float | None, list[dict]]:
        """Read CTRF JSON report and return (fractional reward, test_details).

        Returns (None, []) if CTRF report is missing or malformed.
        """
        ctrf_result = self._podman_cmd(
            "exec", container_name, "cat", "/logs/verifier/ctrf.json",
        )
        if ctrf_result.returncode != 0 or not ctrf_result.stdout.strip():
            return None, []

        try:
            ctrf = json.loads(ctrf_result.stdout.strip())
        except json.JSONDecodeError:
            return None, []

        summary = ctrf.get("results", {}).get("summary", {})
        total = summary.get("tests", 0)
        passed = summary.get("passed", 0)

        if total <= 0:
            return None, []

        test_details = [
            {
                "name": t.get("name", ""),
                "status": t.get("status", "unknown"),
                "message": t.get("message", ""),
            }
            for t in ctrf.get("results", {}).get("tests", [])
        ]

        return passed / total, test_details

    @staticmethod
    def _read_reward_txt(container_name: str) -> float:
        """Read binary reward.txt from container. Returns 0.0 on failure."""
        reward_result = SkillsBenchWrapper._podman_cmd(
            "exec", container_name, "cat", "/logs/verifier/reward.txt",
        )
        if reward_result.returncode == 0 and reward_result.stdout.strip():
            try:
                return float(reward_result.stdout.strip())
            except ValueError:
                pass
        return 0.0

    # ------------------------------------------------------------------
    # Agent prompt for code generation
    # ------------------------------------------------------------------

    def _build_code_gen_prompt(self, task: dict, skill_hints: bool = True) -> str:
        """Build the prompt that asks the agent to generate a solution script.

        Includes WORKDIR and file path info from the Dockerfile so the agent
        knows where files are inside the evaluation container.

        Parameters
        ----------
        skill_hints:
            When True (default), include skill names in the prompt so the agent
            knows which skills to load.  When False, the agent must discover
            skills on its own via search/browse tools.
        """
        instruction = task["instruction"]
        dockerfile = task.get("dockerfile", "")
        skill_ids = task.get("skill_ids", [])

        # Parse WORKDIR from Dockerfile.
        workdir = "/root"
        copy_lines: list[str] = []
        for line in dockerfile.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("WORKDIR"):
                workdir = stripped.split(None, 1)[1].strip() if len(stripped.split()) > 1 else workdir
            if stripped.upper().startswith("COPY"):
                copy_lines.append(stripped)

        # Build sys.path additions for skill scripts.
        skill_script_paths: list[str] = []
        task_dir = Path(task["task_dir"])
        for sid in skill_ids:
            scripts_dir = task_dir / "environment" / "skills" / sid / "scripts"
            if scripts_dir.is_dir():
                for script_file in scripts_dir.iterdir():
                    if script_file.suffix == ".py":
                        skill_script_paths.append(
                            f"/root/.claude/skills/{sid}/scripts"
                        )
                        break

        syspath_info = ""
        if skill_script_paths:
            unique_paths = list(dict.fromkeys(skill_script_paths))
            syspath_info = (
                "\n\nSKILL HELPER SCRIPTS are available at these paths "
                "(add them to sys.path to import):\n"
                + "\n".join(f"  sys.path.append('{p}')" for p in unique_paths)
            )

        # Extract installed packages from Dockerfile.
        pip_lines = []
        apt_lines = []
        for line in dockerfile.splitlines():
            stripped = line.strip()
            if "pip" in stripped and "install" in stripped:
                pip_lines.append(stripped)
            if "apt" in stripped and "install" in stripped:
                apt_lines.append(stripped)
        packages_info = ""
        if pip_lines:
            packages_info += "\nInstalled Python packages:\n" + "\n".join(pip_lines)
        if apt_lines:
            packages_info += "\nInstalled system packages:\n" + "\n".join(apt_lines)

        # Container path info.
        container_info = f"\n\nCONTAINER ENVIRONMENT:\n- Working directory: {workdir}\n- Solution script runs at: /tmp/agent_solution.py"
        if copy_lines:
            container_info += "\n- Files copied into container:\n  " + "\n  ".join(copy_lines[:5])

        skill_names = ", ".join(skill_ids) if skill_ids else "none"
        skill_hint_line = (
            f"8. Load the relevant skills using your available tools BEFORE writing code. Skills for this task: {skill_names}\n"
            if skill_hints else ""
        )

        # Inject test specification for test-first prompting.
        test_content = task.get("test_content", "")
        if len(test_content) > 10000:
            test_content = test_content[:10000] + "\n# ... (truncated)"
        test_section = ""
        if test_content:
            test_section = f"""

TEST SPECIFICATION (your solution must pass these tests):
```python
{test_content}
```
"""

        prompt = f"""You are an AI assistant solving a task. You must write a COMPLETE, self-contained Python 3 script that solves the task.

IMPORTANT RULES:
1. Write a single Python script that can be executed with `python3 script.py`
2. The script must produce all required output files at the correct paths (paths in the task instruction refer to container paths)
3. Do NOT use any packages not listed below — only use what's already installed
4. Do NOT prompt for user input — the script must run non-interactively
5. Handle errors gracefully — the script should not crash
6. Output exactly what the task asks for — file paths, formats, and data must match precisely
7. If skill helper scripts are mentioned below, import them via sys.path.append before importing{syspath_info}
{skill_hint_line}{packages_info}{container_info}
{test_section}
---

TASK INSTRUCTION:
{instruction}

---

Write your solution as a SINGLE Python script. Output ONLY the Python code inside a ```python code block. Do not add any explanation outside the code block."""

        return prompt

    # ------------------------------------------------------------------
    # Single-task execution
    # ------------------------------------------------------------------

    def run_task(
        self,
        agent: BaseAgent,
        task: dict,
        mcp_client: Any = None,
        skill_hints: bool = True,
    ) -> dict:
        """Run a single SkillsBench task: generate code via agent, verify with Docker.

        **Traditional agent**: has a skill registry + ``read_skill`` tool.
        The model decides which skills to read, then generates code (multi-turn).

        **OntoSkills agent**: skill knowledge is prefetched via MCP
        (``get_skill_context``) and injected into the system prompt as
        structured knowledge.  The model generates code in a single turn
        without tool calls — it already has the knowledge it needs.
        """
        skill_ids = task.get("skill_ids", [])
        is_ontoskills = (
            mcp_client is not None and hasattr(agent, "prefetch_skills_by_ids")
        )

        prompt = self._build_code_gen_prompt(task, skill_hints=skill_hints)

        # OntoSkills: prefetch skill knowledge via MCP, inject into system prompt.
        # The model gets structured TTL knowledge and generates code in one turn.
        prefetch_latency_ms = 0.0
        if is_ontoskills and skill_ids and mcp_client._proc is not None:
            try:
                t_pre_start = time.perf_counter()
                prefetched = agent.prefetch_skills_by_ids(skill_ids, query=task["instruction"])
                prefetch_latency_ms = (time.perf_counter() - t_pre_start) * 1000
                if prefetched and hasattr(agent, "_prefetched_knowledge"):
                    agent._prefetched_knowledge = prefetched
                    logger.info(
                        "MCP prefetch: %d chars for %s (%s) in %.2fms",
                        len(prefetched), task["task_id"],
                        ", ".join(skill_ids), prefetch_latency_ms
                    )
            except Exception as exc:
                logger.warning("MCP prefetch failed for %s: %s", task["task_id"], exc)

        original_run_turn = agent.run_turn

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
            t_tool_start = time.perf_counter()
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                if mcp_client is not None and mcp_client._proc is not None:
                    try:
                        mcp_result = mcp_client.call_tool(tool_name, tool_input)
                        from benchmark.agents.ontoskills import OntoSkillsAgent
                        result_text = OntoSkillsAgent._compact_tool_result_static(
                            tool_name, tool_input, mcp_result,
                        )
                        is_error = False
                    except Exception as exc:
                        result_text = f"Error calling MCP tool {tool_name}: {exc}"
                        is_error = True
                elif tool_name == "read_skill" and hasattr(agent, "_resolve_skill"):
                    skill_query = tool_input.get("skill_name", "")
                    content = agent._resolve_skill(skill_query)
                    if content:
                        result_text = content
                        is_error = False
                    else:
                        result_text = f"Skill '{skill_query}' not found."
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
                # Measure time for tool execution and add it to turn latency.
                t_tool_end = time.perf_counter()
                tool_latency_ms = (t_tool_end - t_tool_start) * 1000
                latency_ms += tool_latency_ms

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

        agent.run_turn = _patched_run_turn

        try:
            messages: list[dict] = [{"role": "user", "content": prompt}]
            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0

            for _ in range(6):
                assistant_msg, metrics = agent.run_turn(messages)
                
                # Add pre-fetch latency to the first turn if applicable.
                if turns == 0 and is_ontoskills:
                    metrics["latency_ms"] += prefetch_latency_ms

                turns += 1
                total_input += metrics["input_tokens"]
                total_output += metrics["output_tokens"]
                total_latency_ms += metrics["latency_ms"]
                total_tool_calls += metrics["tool_calls"]

                tool_use_blocks = [
                    b for b in (assistant_msg.get("content") or [])
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]

                if not tool_use_blocks:
                    messages.append(assistant_msg)
                    break

            # Extract the full agent response text.
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

            # Extract Python code from the response.
            solution_script = extract_python_code(answer)

            result = AgentResult(
                answer=answer,
                input_tokens=total_input,
                output_tokens=total_output,
                total_latency_ms=total_latency_ms,
                tool_calls=total_tool_calls,
                turns=turns,
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
            )
            solution_script = ""
        finally:
            agent.run_turn = original_run_turn
            if is_ontoskills and hasattr(agent, "_prefetched_knowledge"):
                agent._prefetched_knowledge = ""

        return {
            "task_id": task["task_id"],
            "model_answer": result.answer,
            "solution_script": solution_script,
            "metrics": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_latency_ms": result.total_latency_ms,
                "latency_ms": result.total_latency_ms,
                "tool_calls": result.tool_calls,
                "turns": result.turns,
                "num_turns": result.turns,
            },
        }

    # ------------------------------------------------------------------
    # Claude Code CLI mode
    # ------------------------------------------------------------------

    def run_task_claudecode(
        self,
        cc_agent: "ClaudeCodeAgent",  # noqa: F821
        task: dict,
        timeout: int = 900,
        max_budget: float = 2.00,
    ) -> dict:
        """Run a single task using the Claude Code CLI.

        Prepares a working directory with environment files, tests, and
        skills, then delegates to ``claude -p`` for realistic evaluation.
        """
        # Prepare working directory.
        work_dir = cc_agent.setup_task_env(task)

        try:
            task_timeout = task.get("agent_timeout_sec", timeout)
            cli_result = cc_agent.run_with_cli(
                task,
                max_budget=max_budget,
                timeout=task_timeout,
            )

            # Read solution script.
            solution_path = Path(cli_result["solution_path"])
            solution_script = ""
            if solution_path.exists():
                solution_script = solution_path.read_text(encoding="utf-8")

            usage = cli_result.get("usage", {})
            return {
                "task_id": task["task_id"],
                "model_answer": cli_result.get("result", ""),
                "solution_script": solution_script,
                "work_dir": cli_result.get("work_dir", ""),
                "metrics": {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "latency_ms": cli_result.get("duration_ms", 0),
                    "tool_calls": cli_result.get("num_turns", 0),
                    "cost_usd": cli_result.get("total_cost_usd", 0),
                },
            }
        except Exception as exc:
            logger.exception("Claude Code task %s failed", task["task_id"])
            return {
                "task_id": task["task_id"],
                "model_answer": f"[Error: {exc}]",
                "solution_script": "",
                "metrics": {},
            }

    # Asymmetric budget weights for multi-attempt.
    _ATTEMPT_WEIGHTS = [0.60, 0.25, 0.15]

    def run_task_claudecode_with_retry(
        self,
        cc_agent,  # ClaudeCodeAgent
        task: dict,
        timeout: int = 900,
        max_budget: float = 2.00,
        max_attempts: int = 3,
    ) -> dict:
        """Run a task with multi-turn Docker feedback (up to max_attempts).

        Flow: agent generates solution -> Docker verifies -> if failed, feed
        back errors -> agent fixes -> Docker re-verifies. Returns best result.

        Uses asymmetric budget: 60/25/15 across 3 attempts.
        """
        weights = self._ATTEMPT_WEIGHTS[:max_attempts]
        # Normalize if max_attempts < 3
        wsum = sum(weights)
        weights = [w / wsum for w in weights]

        best_result = None
        best_reward = -1.0

        task_dir = Path(task["task_dir"])
        task_id = task["task_id"]

        # Compute effective base timeout from task metadata or default.
        # Scale this base across attempts (not the raw default).
        task_base_timeout = task.get("agent_timeout_sec", timeout)

        # First attempt — standard run with 60% budget.
        budget_1 = max_budget * weights[0]
        timeout_1 = int(task_base_timeout * weights[0])
        task["agent_timeout_sec"] = timeout_1
        result = self.run_task_claudecode(
            cc_agent, task, timeout=timeout_1, max_budget=budget_1,
        )

        for attempt in range(max_attempts):
            # Docker verification.
            image_tag = self._get_image_tag(task_id)
            if not image_tag:
                logger.warning("No Docker image for %s, skipping verification", task_id)
                task["agent_timeout_sec"] = task_base_timeout
                return result

            solution_script = result.get("solution_script", "")

            # Skip Docker run if no solution was produced (timeout/error).
            if not solution_script.strip():
                logger.info("Task %s: attempt %d produced no solution, skipping verification", task_id, attempt + 1)
                if attempt == 0:
                    best_result = result.copy()
                    best_result["verification"] = {"reward": 0.0, "test_details": []}
                    best_result["reward"] = 0.0
                    best_result["attempts"] = 1
                break

            verification = self._run_solution(
                image_tag=image_tag,
                task_id=task_id,
                solution_script=solution_script,
                task_dir=str(task_dir),
                work_dir=result.get("work_dir"),
            )
            reward = verification.get("reward", 0.0)

            if reward > best_reward:
                best_reward = reward
                best_result = result.copy()
                best_result["verification"] = verification
                best_result["reward"] = reward
                best_result["attempts"] = attempt + 1

            if reward >= 1.0:
                logger.info("Task %s: PASSED on attempt %d", task_id, attempt + 1)
                best_result["metrics"] = result.get("metrics", {})
                task["agent_timeout_sec"] = task_base_timeout
                return best_result

            if attempt < max_attempts - 1:
                # Build feedback prompt.
                feedback_parts = []
                details = verification.get("test_details", [])
                failed_tests = [t for t in details if t.get("status") == "failed"]
                if failed_tests:
                    feedback_parts.append("### Failed Tests")
                    for t in failed_tests[:5]:
                        feedback_parts.append(f"- {t.get('name', '?')}: {t.get('message', '')[:200]}")

                sol_errors = verification.get("solution_errors", "")
                if sol_errors:
                    feedback_parts.append(f"### Solution Errors\n{sol_errors[-1000:]}")

                test_output = verification.get("test_output", "")
                if test_output and "AssertionError" in test_output:
                    lines = [l for l in test_output.split("\n") if "AssertionError" in l or "assert" in l]
                    if lines:
                        feedback_parts.append("### Assertion Failures\n" + "\n".join(lines[:5]))

                feedback = "\n\n".join(feedback_parts)
                if not feedback.strip():
                    break

                logger.info(
                    "Task %s: attempt %d reward=%.3f, retrying with feedback",
                    task_id, attempt + 1, reward,
                )

                # Asymmetric budget for subsequent attempts.
                w = weights[attempt + 1] if attempt + 1 < len(weights) else weights[-1]
                budget_next = max_budget * w
                timeout_next = int(task_base_timeout * w)
                task["agent_timeout_sec"] = timeout_next

                cli_result = cc_agent.run_with_feedback(
                    task,
                    feedback=feedback,
                    max_budget=budget_next,
                    timeout=timeout_next,
                )

                solution_path = Path(cli_result["solution_path"])
                solution_script = ""
                if solution_path.exists():
                    solution_script = solution_path.read_text(encoding="utf-8")

                result = {
                    "task_id": task_id,
                    "model_answer": cli_result.get("result", ""),
                    "solution_script": solution_script,
                    "work_dir": cli_result.get("work_dir", ""),
                    "metrics": {
                        "input_tokens": result.get("metrics", {}).get("input_tokens", 0)
                            + cli_result.get("usage", {}).get("input_tokens", 0),
                        "output_tokens": result.get("metrics", {}).get("output_tokens", 0)
                            + cli_result.get("usage", {}).get("output_tokens", 0),
                        "latency_ms": result.get("metrics", {}).get("latency_ms", 0)
                            + cli_result.get("duration_ms", 0),
                        "tool_calls": result.get("metrics", {}).get("tool_calls", 0)
                            + cli_result.get("num_turns", 0),
                        "cost_usd": result.get("metrics", {}).get("cost_usd", 0)
                            + cli_result.get("total_cost_usd", 0),
                    },
                }

        logger.info("Task %s: best reward=%.3f after %d attempts", task_id, best_reward, max_attempts)
        # Restore original timeout so it doesn't leak to the next task.
        task["agent_timeout_sec"] = task_base_timeout
        if best_result:
            best_result["metrics"] = result.get("metrics", {})
            return best_result
        return result

    def run_benchmark_claudecode(
        self,
        cc_agent: "ClaudeCodeAgent",  # noqa: F821
        max_tasks: int | None = None,
        shuffle: bool = True,
        seed: int = 42,
        workers: int = 3,
        timeout: int = 900,
        max_budget: float = 2.00,
        skip_first: int = 0,
        max_attempts: int = 1,
        skill_hints: bool = True,
    ) -> list[dict]:
        """Run SkillsBench tasks via Claude Code CLI, then verify with Docker.

        Args:
            max_attempts: 1 for single-attempt (like Harbor), 3 for multi-turn
                with asymmetric budget (60/25/15).
        """
        packages_root = os.path.expanduser("~/.ontoskills/packages")
        tasks = self.load_tasks(
            max_tasks=max_tasks, shuffle=shuffle, seed=seed,
            packages_root=packages_root, skip_first=skip_first,
        )

        # Phase 0: Pre-warm cache and build images before spending agent time.
        self._prepull_base_images()
        tasks = self.prebuild_images(tasks, workers=workers)
        if not tasks:
            logger.error("Phase 0: All tasks failed to build. Check podman/docker.")
            return []

        results: list[dict] = []
        incremental_path = os.environ.get("BENCHMARK_INCREMENTAL_PATH")
        try:
            # Phase 1: Generate solutions via Claude Code CLI.
            for i, task in enumerate(tasks, 1):
                logger.info(
                    "Claude Code [%d/%d]: %s (%s)",
                    i, len(tasks), task["task_id"], task.get("category", ""),
                )

                # Pass skill_hints to task dict so ClaudeCode agent can use it.
                task["skill_hints"] = skill_hints

                if max_attempts > 1:
                    result = self.run_task_claudecode_with_retry(
                        cc_agent, task, timeout=timeout, max_budget=max_budget,
                        max_attempts=max_attempts,
                    )
                else:
                    # Single-attempt: all budget in one call, then verify once.
                    result = self.run_task_claudecode(
                        cc_agent, task, timeout=timeout, max_budget=max_budget,
                    )
                    # Verify with Docker.
                    image_tag = self._get_image_tag(task["task_id"])
                    if image_tag and result.get("solution_script", "").strip():
                        verification = self._run_solution(
                            image_tag=image_tag,
                            task_id=task["task_id"],
                            solution_script=result["solution_script"],
                            task_dir=str(Path(task["task_dir"])),
                            work_dir=result.get("work_dir"),
                        )
                        result["verification"] = verification
                        result["reward"] = verification.get("reward", 0.0)
                        result["attempts"] = 1
                    else:
                        result["verification"] = {"reward": 0.0, "test_details": []}
                        result["reward"] = 0.0
                        result["attempts"] = 1
                results.append(result)

                # Save incrementally after each task so progress isn't lost on crash.
                if incremental_path:
                    import json as _json
                    _path = Path(incremental_path)
                    _path.parent.mkdir(parents=True, exist_ok=True)
                    _path.write_text(
                        _json.dumps(results, indent=2, default=str, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    logger.info("Incremental save: %d results -> %s", len(results), _path)

            # Docker verification is done inline per-task (multi-turn with retry).

        finally:
            cc_agent.cleanup()

        return results

    # ------------------------------------------------------------------
    # Docker verification (runs after all agent tasks)
    # ------------------------------------------------------------------

    def verify_with_docker(
        self,
        results: list[dict],
        tasks: list[dict],
        workers: int = 3,
    ) -> list[dict]:
        """Build Docker images and verify agent solutions with pytest.

        Uses ``workers`` parallel threads for build+verify. Images are cached
        and reused across agent runs (not deleted until cleanup).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        task_map = {t["task_id"]: t for t in tasks}
        n = len(results)

        # Separate tasks with/without solutions.
        to_verify: list[tuple[int, dict]] = []
        for i, r in enumerate(results):
            task_id = r["task_id"]
            task = task_map.get(task_id)
            solution = r.get("solution_script", "")
            if not task or not solution:
                r["reward"] = 0.0
                r["verification"] = {"error": "No solution script generated"}
            else:
                to_verify.append((i, r))

        if not to_verify:
            return results

        def _verify_one(idx: int, r: dict) -> None:
            task_id = r["task_id"]
            task = task_map[task_id]
            logger.info("Verifying %s...", task_id)
            image_tag = self._build_image(task_id, task["task_dir"])
            if not image_tag:
                r["reward"] = 0.0
                r["verification"] = {"error": "Docker build failed"}
                return
            verification = self._run_solution(
                image_tag, task_id, r["solution_script"], task["task_dir"],
                work_dir=r.get("work_dir"),
            )
            r["reward"] = verification["reward"]
            r["verification"] = verification

        logger.info(
            "Docker verification: %d tasks, %d workers", len(to_verify), workers,
        )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_verify_one, idx, r): idx for idx, r in to_verify}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                exc = future.exception()
                idx = futures[future]
                if exc:
                    logger.error("Worker error on %s: %s", results[idx]["task_id"], exc)
                    results[idx]["reward"] = 0.0
                    results[idx]["verification"] = {"error": str(exc)}
                else:
                    logger.info(
                        "[%d/%d] %s done (reward=%.3f)",
                        done_count, len(to_verify),
                        results[idx]["task_id"], results[idx].get("reward", 0),
                    )

        return results

    # ------------------------------------------------------------------
    # Full benchmark run
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        agent: BaseAgent,
        max_tasks: int | None = None,
        shuffle: bool = True,
        seed: int = 42,
        workers: int = 3,
        skip_first: int = 0,
        skill_hints: bool = True,
    ) -> list[dict]:
        """Run SkillsBench tasks: generate solutions, then verify with Docker."""
        packages_root = os.path.expanduser("~/.ontoskills/packages")
        tasks = self.load_tasks(
            max_tasks=max_tasks, shuffle=shuffle, seed=seed,
            packages_root=packages_root, skip_first=skip_first,
        )

        # Phase 0: Pre-warm cache and build images before spending agent time.
        self._prepull_base_images()
        tasks = self.prebuild_images(tasks, workers=workers)
        if not tasks:
            logger.error("Phase 0: All tasks failed to build. Check podman/docker.")
            return []

        from benchmark.agents.traditional import TraditionalAgent
        is_traditional = isinstance(agent, TraditionalAgent)

        # For OntoSkillsAgent: prepare a SkillsBench-only ontology root for
        # faster MCP loading.  Only 218 SkillsBench TTLs vs. 626 total.
        mcp_client = None
        if not is_traditional and hasattr(agent, "_mcp_client"):
            skillsbench_root = self._prepare_skillsbench_ontology_root()
            if skillsbench_root:
                agent._mcp_client._ontology_root = skillsbench_root
                logger.info(
                    "Using SkillsBench-only ontology root: %s", skillsbench_root,
                )
            mcp_client = agent._mcp_client
            mcp_client.__enter__()
            mcp_client.initialize()

        results: list[dict] = []
        try:
            # Phase 1: Generate solutions for all tasks.
            for i, task in enumerate(tasks, 1):
                logger.info(
                    "Generating [%d/%d]: %s (%s)",
                    i, len(tasks), task["task_id"], task.get("category", ""),
                )

                task_agent = agent
                if is_traditional:
                    task_agent = self._make_scoped_traditional_agent(
                        agent.model, task.get("skills_content", {}),
                    )

                try:
                    result = self.run_task(task_agent, task, mcp_client=mcp_client, skill_hints=skill_hints)
                except Exception:
                    logger.exception("Task %s failed", task["task_id"])
                    result = {
                        "task_id": task["task_id"],
                        "model_answer": "",
                        "solution_script": "",
                        "metrics": None,
                    }
                results.append(result)

            # Phase 2: Docker verification (deterministic scoring, parallel).
            logger.info("=== Docker verification phase (%d workers) ===", workers)
            results = self.verify_with_docker(results, tasks, workers=workers)

        finally:
            if mcp_client is not None:
                try:
                    mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

        return results

    def _prepare_skillsbench_ontology_root(self) -> str | None:
        """Create a SkillsBench-only ontology root for faster MCP loading.

        Copies the skillsbench package from the full ontology root into a
        temporary directory.  Returns the path or None on failure.
        """
        packages_root = os.path.expanduser("~/.ontoskills/packages")
        src = Path(packages_root) / "skillsbench"
        if not src.is_dir():
            return None

        dst = Path(tempfile.gettempdir()) / "skillsbench_ontology" / "skillsbench"
        dst.parent.mkdir(parents=True, exist_ok=True)
        src_mtime = src.stat().st_mtime
        dst_mtime = dst.stat().st_mtime if dst.exists() else 0
        if dst.is_dir() and src_mtime <= dst_mtime:
            return str(dst.parent)

        if dst.exists():
            shutil.rmtree(str(dst))
        try:
            shutil.copytree(str(src), str(dst))
            logger.info("Prepared SkillsBench ontology root at %s", dst.parent)
            return str(dst.parent)
        except FileExistsError:
            return str(dst.parent)
        except Exception as exc:
            logger.warning("Failed to prepare SkillsBench ontology root: %s", exc)
            return None

    def _make_scoped_traditional_agent(
        self, model: str, skills_content: dict[str, str],
    ) -> BaseAgent:
        """Create a TraditionalAgent scoped to the task's skills.

        The agent has a skill registry with names/descriptions and a
        ``read_skill`` tool to load full SKILL.md content.  The model
        must decide which skills to read and then generate code.
        """
        from benchmark.agents.traditional import TraditionalAgent, _parse_frontmatter

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        agent = TraditionalAgent.__new__(TraditionalAgent)
        BaseAgent.__init__(agent, model=model, api_key=api_key)

        # Build skill registry + lookup from the task's SKILL.md content.
        entries: list[str] = []
        skills_by_name: dict[str, str] = {}
        for sid, content in skills_content.items():
            fm = _parse_frontmatter(content)
            name = fm.get("name", sid)
            desc = fm.get("description", "")
            entries.append(f"- {name}: {desc}" if desc else f"- {name}")
            skills_by_name[name] = content
            skills_by_name[sid] = content

        agent.skills_dir = ""
        agent._skill_registry = "\n".join(entries)
        agent._skills_by_name = skills_by_name
        agent._system_prompt = agent._build_system_prompt()
        # Ensure read_skill tool is available (no override).
        if hasattr(agent, "_tools_override"):
            del agent._tools_override

        def _resolve_from_content(query: str) -> str | None:
            q = query.strip()
            val = skills_by_name.get(q)
            if val:
                return val
            for name, content in skills_by_name.items():
                if name.startswith(q) or q in name:
                    return content
            return None

        agent._resolve_skill = _resolve_from_content
        return agent

    # ------------------------------------------------------------------
    # Scoring (deterministic, from Docker reward.txt)
    # ------------------------------------------------------------------

    @staticmethod
    def score(results: list[dict]) -> dict:
        """Compute scores from Docker verification results.

        Uses fractional rewards from pytest CTRF reports (passed/total tests)
        where available, falling back to binary reward.txt.
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("reward", 0) >= 1.0)
        partial = sum(1 for r in results if 0 < r.get("reward", 0) < 1.0)
        avg_reward = sum(r.get("reward", 0.0) for r in results) / total if total > 0 else 0.0

        per_task = []
        for r in results:
            reward = r.get("reward", 0.0)
            entry = {
                "task_id": r["task_id"],
                "reward": reward,
                "passed": reward >= 1.0,
            }
            # Attach per-test details if available.
            verification = r.get("verification", {})
            test_details = verification.get("test_details", [])
            if test_details:
                entry["tests_passed"] = sum(
                    1 for t in test_details if t.get("status") == "passed"
                )
                entry["tests_total"] = len(test_details)
                entry["test_details"] = test_details
            per_task.append(entry)

        return {
            "scoring_method": "docker_pytest",
            "pass_rate": passed / total if total > 0 else 0.0,
            "avg_reward": avg_reward,
            "tasks_passed": passed,
            "tasks_partial": partial,
            "tasks_failed": total - passed - partial,
            "total_tasks": total,
            "per_task": per_task,
        }
