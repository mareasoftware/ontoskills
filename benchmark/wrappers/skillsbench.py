"""SkillsBench benchmark wrapper — BenchFlow-aligned deterministic evaluation.

Uses BenchFlow's Trial for container lifecycle and Harbor Verifier for
deterministic scoring.  Supports two evaluation modes:

  - **ACP** (``acp``): Agent runs inside the container via BenchFlow ACP.
    Skills are injected into the Dockerfile.  100% SkillsBench aligned.
  - **ACP-MCP** (``acp-mcp``): Same as ACP but with ontomcp MCP tools
    injected into the container for skill discovery.

Both modes use BenchFlow's RetryConfig for clean retries with exponential
backoff, and ``_run_pooled()`` for parallel worker execution with
state-backed resume via ``BenchmarkState``.

Legacy API mode (``run_task`` / ``run_benchmark``) remains for other
wrappers (GAIA, SWE-bench, PerPackage) that share the same interface.

Requires: docker (or podman with docker alias), benchflow, harbor packages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from benchmark.agents.utils import extract_python_code
from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# Tasks with exotic base images or multi-container setups that won't build.
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

DEFAULT_REPO_PATH = os.path.expanduser("~/.ontoskills/skillsbench")

RATE_LIMIT_BACKOFF = [5, 10, 20, 60, 120]
RATE_LIMIT_CONSECUTIVE_MAX = 5


def _is_rate_limit_error(error: str | None) -> bool:
    if not error:
        return False
    error_lower = error.lower()
    return any(
        kw in error_lower
        for kw in ("rate limit", "429", "ratelimiterror", "too many requests")
    )


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
    """SkillsBench wrapper using BenchFlow Trial for container management.

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

        toml_path = task_dir / "task.toml"
        metadata = {}
        if toml_path.exists():
            metadata = _parse_toml_simple(toml_path.read_text(encoding="utf-8"))
        meta = metadata.get("metadata", {})

        instr_path = task_dir / "instruction.md"
        instruction = instr_path.read_text(encoding="utf-8") if instr_path.exists() else ""

        dockerfile_path = task_dir / "environment" / "Dockerfile"
        dockerfile = dockerfile_path.read_text(encoding="utf-8") if dockerfile_path.exists() else ""

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

        agent_meta = metadata.get("agent", {})

        return {
            "task_id": task_id,
            "difficulty": meta.get("difficulty", "unknown"),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "instruction": instruction,
            "dockerfile": dockerfile,
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
        only_tasks: list[str] | None = None,
    ) -> list[dict]:
        """Load SkillsBench tasks from the local repo clone."""
        if not self.tasks_dir.is_dir():
            raise FileNotFoundError(
                f"SkillsBench tasks directory not found: {self.tasks_dir}\n"
                f"Clone the repo first: git clone https://github.com/benchflow-ai/skillsbench {self.repo_path}"
            )

        pkg_root = Path(packages_root) if packages_root else None
        only_set = set(only_tasks) if only_tasks else None
        tasks = []
        skipped_missing = 0
        for task_dir in sorted(self.tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            if only_set is not None and task_id not in only_set:
                continue
            if task_id in _SKIP_TASKS:
                continue
            task = self._load_task_from_repo(task_id)
            if not task or not task["skill_ids"]:
                continue

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
            logger.info("Skipped %d tasks with uncompiled skills", skipped_missing)
        logger.info("Loaded %d tasks with skills (from %s)", len(tasks), self.repo_path)

        if shuffle:
            random.Random(seed).shuffle(tasks)
        if skip_first > 0:
            tasks = tasks[skip_first:]
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        return tasks

    def load_dataset(self, **kwargs) -> list[dict]:
        return self.load_tasks(**kwargs)

    # ------------------------------------------------------------------
    # Agent prompt for code generation (API mode)
    # ------------------------------------------------------------------

    def _build_code_gen_prompt(self, task: dict, skill_hints: bool = True) -> str:
        """Build the prompt for the API-mode agent.

        SkillsBench-aligned: skill_nudge (name level) + instruction.md content.
        Matches BenchFlow _resolve_prompts() with skill_nudge="name".
        """
        instruction = task["instruction"]
        skill_ids = task.get("skill_ids", [])

        if not skill_hints or not skill_ids:
            return instruction

        names = ", ".join(skill_ids)
        nudge = f"Skills available at ~/.claude/skills: {names}. Read them before starting."
        return f"{nudge}\n\n{instruction}"

    # ------------------------------------------------------------------
    # BenchFlow Trial integration (async)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_agent_env(skill_nudge: str) -> dict[str, str]:
        """Build agent environment dict with API key and provider vars."""
        agent_env: dict[str, str] = {"BENCHFLOW_SKILL_NUDGE": skill_nudge}
        agent_env["CLAUDE_CODE_SIMPLE"] = "1"
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if api_key:
            agent_env["ANTHROPIC_API_KEY"] = api_key
            agent_env["ANTHROPIC_AUTH_TOKEN"] = api_key
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        if base_url:
            agent_env["ANTHROPIC_BASE_URL"] = base_url
        # BenchFlow provider resolution — glm-5.1 has no built-in provider,
        # so we must pass the proxy URL and key explicitly.
        if api_key:
            agent_env["BENCHFLOW_PROVIDER_API_KEY"] = api_key
        if base_url:
            agent_env["BENCHFLOW_PROVIDER_BASE_URL"] = base_url
            agent_env["BENCHFLOW_PROVIDER_PROTOCOL"] = "anthropic-messages"
        return agent_env

    async def _run_acp_trial(
        self,
        task: dict,
        *,
        skills_dir: str | None = None,
        skill_nudge: str = "name",
    ) -> dict:
        """Full ACP Trial: agent inside container (100% SkillsBench aligned).

        Uses Trial.run() for the complete lifecycle: setup → start →
        install_agent → connect (ACP) → execute → verify → cleanup.
        """
        from benchflow.trial import Trial, TrialConfig

        task_path = Path(task["task_dir"])
        task_id = task["task_id"]
        jobs_dir = task_path.parent.parent / ".benchflow_jobs"

        agent_env = self._build_agent_env(skill_nudge)

        config = TrialConfig.from_legacy(
            task_path=task_path,
            agent="opencode",
            model="glm-5.1",
            jobs_dir=str(jobs_dir),
            environment="docker",
            skills_dir=skills_dir,
            agent_env=agent_env,
        )

        trial = await Trial.create(config)
        try:
            result = await trial.run()
        except Exception as exc:
            logger.exception("ACP Trial failed for %s: %s", task_id, exc)
            return {
                "task_id": task_id,
                "reward": 0.0,
                "rewards": None,
                "error": str(exc),
                "verifier_error": None,
                "build_ok": False,
                "n_tool_calls": 0,
            }
        finally:
            try:
                await trial.cleanup()
            except Exception:
                pass

        reward = result.rewards.get("reward", 0.0) if result.rewards else 0.0
        build_ok = result.error is None
        return {
            "task_id": task_id,
            "reward": reward,
            "rewards": result.rewards,
            "error": result.error,
            "verifier_error": result.verifier_error,
            "build_ok": build_ok,
            "n_tool_calls": result.n_tool_calls,
        }

    async def _inject_mcp_into_container(self, env, task: dict) -> None:
        """Inject ontomcp binary + TTL files + MCP config into container."""
        import subprocess as sp

        from benchmark.config import ONTOMCP_BIN_PATH

        ontology_root = self._prepare_skillsbench_ontology_root()
        if not ontology_root:
            raise RuntimeError("No SkillsBench ontology root available for MCP injection")

        ontomcp_bin = Path(ONTOMCP_BIN_PATH)
        if not ontomcp_bin.exists():
            raise FileNotFoundError(f"ontomcp binary not found at {ontomcp_bin}")

        # Upload ontomcp binary.
        await env.upload_file(str(ontomcp_bin), "/usr/local/bin/ontomcp")
        await env.exec("chmod +x /usr/local/bin/ontomcp", timeout_sec=30)

        # Upload TTL files as tar for efficiency.
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
            tar_path = f.name
        try:
            sp.run(
                ["tar", "czf", tar_path, "-C", ontology_root, "."],
                check=True, capture_output=True,
            )
            await env.upload_file(tar_path, "/tmp/ontoskills_ttl.tar.gz")
        finally:
            os.unlink(tar_path)
        await env.exec(
            "mkdir -p /opt/ontoskills/packages && "
            "tar xzf /tmp/ontoskills_ttl.tar.gz -C /opt/ontoskills/packages",
            timeout_sec=60,
        )

        # Write .mcp_config.json to the container's WORKDIR.
        result = await env.exec("pwd", timeout_sec=10)
        cwd = (result.stdout or "").strip() or "/root"
        mcp_dst = f"{cwd}/.mcp_config.json"
        mcp_config = json.dumps({
            "mcpServers": {
                "ontoskills": {
                    "command": "/usr/local/bin/ontomcp",
                    "args": ["--ontology-root", "/opt/ontoskills/packages"],
                    "type": "stdio",
                }
            }
        })
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        ) as f:
            f.write(mcp_config)
            config_tmp = f.name
        try:
            await env.upload_file(config_tmp, mcp_dst)
        finally:
            os.unlink(config_tmp)

        logger.info("MCP injected: ontomcp + TTLs + .mcp_config.json at %s", mcp_dst)

    async def _run_acp_mcp_trial(
        self,
        task: dict,
        *,
        skill_nudge: str = "name",
    ) -> dict:
        """ACP Trial with MCP tools injected into the container.

        Splits Trial lifecycle using public API so we can inject
        ontomcp binary + TTL files + .mcp_config.json between
        start() and install_agent().

        Overrides the prompt nudge to mention the ``ontoskill`` MCP tool
        instead of ``~/.claude/skills`` (which does not exist in MCP mode).
        """
        from benchflow.trial import Trial, TrialConfig

        task_path = Path(task["task_dir"])
        task_id = task["task_id"]
        jobs_dir = task_path.parent.parent / ".benchflow_jobs"

        # Build MCP-specific prompt: read instruction.md and prepend
        # an MCP tool nudge.  Disable BenchFlow's built-in skill_nudge
        # because it mentions ~/.claude/skills which doesn't exist here.
        instr_path = task_path / "instruction.md"
        instruction = instr_path.read_text(encoding="utf-8").strip() if instr_path.exists() else ""

        if skill_nudge and task.get("skill_ids"):
            names = ", ".join(task["skill_ids"])
            snippet = task["skill_ids"][0]
            nudge = (
                f"Skills available via the ontoskill tool: {names}. "
                f"Call ontoskill(q=\"{snippet}\") to load its full context, "
                f"or use ontoskill(q=\"your task description\") to discover "
                f"relevant skills."
            )
            instruction = nudge + "\n\n" + instruction

        agent_env = self._build_agent_env("")  # disable BenchFlow's skill_nudge

        config = TrialConfig.from_legacy(
            task_path=task_path,
            agent="opencode",
            model="glm-5.1",
            prompts=[instruction],
            jobs_dir=str(jobs_dir),
            environment="docker",
            agent_env=agent_env,
        )

        trial = await Trial.create(config)
        try:
            await trial.setup()
            await trial.start()

            # MCP injection point — between start and install_agent.
            await self._inject_mcp_into_container(trial.env, task)

            await trial.install_agent()
            await trial.connect()
            await trial.execute()

            try:
                await trial.disconnect()
            except Exception:
                pass

            await trial.verify()

            result = trial._build_result()
            reward = result.rewards.get("reward", 0.0) if result.rewards else 0.0
            build_ok = result.error is None
            return {
                "task_id": task_id,
                "reward": reward,
                "rewards": result.rewards,
                "error": result.error,
                "verifier_error": result.verifier_error,
                "build_ok": build_ok,
                "n_tool_calls": result.n_tool_calls,
            }
        except Exception as exc:
            logger.exception("ACP MCP Trial failed for %s: %s", task_id, exc)
            return {
                "task_id": task_id,
                "reward": 0.0,
                "rewards": None,
                "error": str(exc),
                "verifier_error": None,
                "build_ok": False,
                "n_tool_calls": 0,
            }
        finally:
            try:
                await trial.cleanup()
            except Exception:
                pass

    async def _run_pooled(
        self,
        tasks: list[dict],
        state: "BenchmarkState",
        trial_runner,
        *,
        max_attempts: int = 5,
        workers: int = 2,
    ) -> list[dict]:
        """Run tasks with N parallel workers and state-backed resume.

        Rate-limit errors are treated as free attempts (not counted toward
        max_attempts).  After ``RATE_LIMIT_CONSECUTIVE_MAX`` consecutive
        rate-limit responses the workers gracefully shut down so the
        benchmark can be resumed later.
        """
        from benchflow.job import RetryConfig

        queue: asyncio.Queue[tuple[str, dict, int]] = asyncio.Queue()
        shutdown_event = asyncio.Event()

        for task in tasks:
            tid = task["task_id"]
            if not state.should_run(tid):
                continue
            attempt = state.next_attempt(tid)
            queue.put_nowait((tid, task, attempt))

        if queue.empty():
            logger.info("All tasks already completed, nothing to run.")
            return state.get_results()

        retry_config = RetryConfig(max_retries=max_attempts - 1)

        async def worker(worker_id: int) -> None:
            while not shutdown_event.is_set():
                try:
                    tid, task, attempt = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                logger.info(
                    "Worker %d: %s attempt %d/%d",
                    worker_id, tid, attempt, max_attempts,
                )

                result = await trial_runner(task)

                if _is_rate_limit_error(result.get("error")):
                    state.record_attempt(tid, result, counted=False)
                    rl_count = state.increment_rate_limit()

                    if rl_count > RATE_LIMIT_CONSECUTIVE_MAX:
                        logger.warning(
                            "Rate limit threshold reached (%d consecutive), "
                            "shutting down gracefully. Resume with --resume.",
                            rl_count,
                        )
                        shutdown_event.set()
                        queue.put_nowait((tid, task, attempt))
                        queue.task_done()
                        return

                    backoff = RATE_LIMIT_BACKOFF[min(rl_count - 1, len(RATE_LIMIT_BACKOFF) - 1)]
                    logger.info(
                        "Task %s: rate limited (free attempt, consecutive RL %d/%d), "
                        "retry in %ds",
                        tid, rl_count, RATE_LIMIT_CONSECUTIVE_MAX, backoff,
                    )
                    await asyncio.sleep(backoff)
                    queue.put_nowait((tid, task, attempt))
                    queue.task_done()
                    continue

                state.reset_rate_limit()
                result["attempt"] = attempt
                state.record_attempt(tid, result, counted=True)

                reward = result.get("reward", 0.0)
                if reward >= 1.0:
                    logger.info("Task %s: PASSED on attempt %d", tid, attempt)
                    state.mark_completed(tid)
                elif attempt >= max_attempts:
                    logger.info("Task %s: exhausted %d attempts", tid, max_attempts)
                    state.mark_completed(tid)
                else:
                    delay = retry_config.backoff_delay(attempt - 1)
                    logger.info(
                        "Task %s: attempt %d reward=%.3f, retry in %.1fs",
                        tid, attempt, reward, delay,
                    )
                    await asyncio.sleep(delay)
                    queue.put_nowait((tid, task, attempt + 1))

                queue.task_done()

        await asyncio.gather(*[worker(i) for i in range(workers)])

        if shutdown_event.is_set():
            logger.warning(
                "Benchmark shut down due to rate limits. "
                "%d task(s) remain in progress — resume with --resume.",
                sum(1 for t in tasks if state.should_run(t["task_id"])),
            )

        return state.get_results()

    async def _run_pooled_task_first(
        self,
        tasks: list[dict],
        states: list["BenchmarkState"],
        trial_runners: list,
        cases: list[tuple[str, bool]],
        *,
        max_attempts: int = 5,
        workers: int = 2,
    ) -> None:
        """Run all5 benchmark with task-first iteration + Docker pruning.

        For each task, runs all cases sequentially, then prunes Docker.
        Disk usage bounded to ~workers tasks worth of images.

        Rate-limit errors are free attempts; after
        ``RATE_LIMIT_CONSECUTIVE_MAX`` consecutive rate-limit responses
        the workers gracefully shut down for later resume.
        """
        queue: asyncio.Queue[dict] = asyncio.Queue()
        shutdown_event = asyncio.Event()

        for task in tasks:
            tid = task["task_id"]
            needs_work = any(
                states[i].should_run(tid) for i in range(len(cases))
            )
            if needs_work:
                queue.put_nowait(task)

        if queue.empty():
            logger.info("All tasks already completed for all cases.")
            return

        async def _docker_prune() -> None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "system", "prune", "-a", "-f",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                logger.info("Docker prune completed")
            except Exception:
                pass

        async def worker(worker_id: int) -> None:
            while not shutdown_event.is_set():
                try:
                    task = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                tid = task["task_id"]

                for case_idx, (mode, hints) in enumerate(cases):
                    if shutdown_event.is_set():
                        break

                    state = states[case_idx]
                    if not state.should_run(tid):
                        continue

                    runner = trial_runners[case_idx]
                    label = f"{mode}+{'hints' if hints else 'nohints'}"

                    attempt = state.next_attempt(tid)
                    while attempt <= max_attempts:
                        if not state.should_run(tid) or shutdown_event.is_set():
                            break

                        logger.info(
                            "Worker %d: %s [%s] attempt %d/%d",
                            worker_id, tid, label, attempt, max_attempts,
                        )

                        result = await runner(task)

                        if _is_rate_limit_error(result.get("error")):
                            state.record_attempt(tid, result, counted=False)
                            rl_count = state.increment_rate_limit()

                            if rl_count > RATE_LIMIT_CONSECUTIVE_MAX:
                                logger.warning(
                                    "Rate limit threshold reached (%d consecutive), "
                                    "shutting down gracefully. Resume with --resume.",
                                    rl_count,
                                )
                                shutdown_event.set()
                                break

                            idx = min(rl_count - 1, len(RATE_LIMIT_BACKOFF) - 1)
                            backoff = RATE_LIMIT_BACKOFF[idx]
                            logger.info(
                                "Task %s [%s]: rate limited "
                                "(free attempt, consecutive RL %d/%d), retry in %ds",
                                tid, label, rl_count, RATE_LIMIT_CONSECUTIVE_MAX, backoff,
                            )
                            await asyncio.sleep(backoff)
                            continue

                        state.reset_rate_limit()
                        result["attempt"] = attempt
                        state.record_attempt(tid, result, counted=True)

                        reward = result.get("reward", 0.0)
                        if reward >= 1.0:
                            logger.info(
                                "Task %s [%s]: PASSED on attempt %d",
                                tid, label, attempt,
                            )
                            state.mark_completed(tid)
                            break

                        attempt += 1

                        if attempt > max_attempts:
                            logger.info(
                                "Task %s [%s]: exhausted %d attempts",
                                tid, label, max_attempts,
                            )
                            state.mark_completed(tid)
                            break
                        else:
                            delay = min(1.0 * 2.0 ** attempt, 30.0)
                            logger.info(
                                "Task %s [%s]: attempt %d reward=%.3f, retry in %.1fs",
                                tid, label, attempt, reward, delay,
                            )
                            await asyncio.sleep(delay)

                if shutdown_event.is_set():
                    break

                logger.info("Worker %d: pruning Docker after task %s", worker_id, tid)
                await _docker_prune()

        await asyncio.gather(*[worker(i) for i in range(workers)])

        if shutdown_event.is_set():
            total_remaining = sum(
                1 for t in tasks
                for s in states
                if s.should_run(t["task_id"])
            )
            logger.warning(
                "Benchmark shut down due to rate limits. "
                "%d case(s) remain in progress — resume with --resume.",
                total_remaining,
            )

    # ------------------------------------------------------------------
    # API mode (for TraditionalAgent / OntoSkillsAgent)
    # ------------------------------------------------------------------

    def run_task(
        self,
        agent: BaseAgent,
        task: dict,
        mcp_client: Any = None,
        skill_hints: bool = True,
    ) -> dict:
        """Run a single SkillsBench task via API agent, verify with BenchFlow Trial."""
        skill_ids = task.get("skill_ids", [])
        is_ontoskills = (
            mcp_client is not None and hasattr(agent, "prefetch_skills_by_ids")
        )

        prompt = self._build_code_gen_prompt(task, skill_hints=skill_hints)

        prefetch_latency_ms = 0.0
        if is_ontoskills and skill_ids and mcp_client._proc is not None:
            try:
                t_pre_start = time.perf_counter()
                prefetched = agent.prefetch_skills_by_ids(skill_ids, query=task["instruction"])
                prefetch_latency_ms = (time.perf_counter() - t_pre_start) * 1000
                if prefetched and hasattr(agent, "_prefetched_knowledge"):
                    agent._prefetched_knowledge = prefetched
            except Exception as exc:
                logger.warning("MCP prefetch failed for %s: %s", task["task_id"], exc)

        original_run_turn = agent.run_turn

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            start = time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (time.perf_counter() - start) * 1000

            content_blocks: list[dict] = []
            for block in response.content:
                if block.type == "text":
                    content_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    content_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            assistant_msg: dict = {"role": "assistant", "content": content_blocks}

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
                    content = agent._resolve_skill(tool_input.get("skill_name", ""))
                    result_text = content or f"Skill '{tool_input.get('skill_name', '')}' not found."
                    is_error = not content
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
                t_tool_end = time.perf_counter()
                latency_ms += (t_tool_end - t_tool_start) * 1000
                messages.append(assistant_msg)
                messages.append({"role": "user", "content": tool_result_blocks})

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

            answer = ""
            for block in reversed(messages):
                if isinstance(block, dict) and block.get("role") == "assistant":
                    content = block.get("content", "")
                    if isinstance(content, str):
                        answer = content
                    elif isinstance(content, list):
                        texts = [
                            b["text"] for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        answer = "\n".join(texts)
                    break

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
        """Run SkillsBench tasks: generate solutions via API agent, verify with Trial."""
        packages_root = os.path.expanduser("~/.ontoskills/packages")
        tasks = self.load_tasks(
            max_tasks=max_tasks, shuffle=shuffle, seed=seed,
            packages_root=packages_root, skip_first=skip_first,
        )

        if not tasks:
            logger.error("No tasks to run.")
            return []

        from benchmark.agents.traditional import TraditionalAgent
        is_traditional = isinstance(agent, TraditionalAgent)

        mcp_client = None
        if not is_traditional and hasattr(agent, "_mcp_client"):
            skillsbench_root = self._prepare_skillsbench_ontology_root()
            if skillsbench_root:
                agent._mcp_client._ontology_root = skillsbench_root
            mcp_client = agent._mcp_client
            mcp_client.__enter__()
            mcp_client.initialize()

        results: list[dict] = []
        try:
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
                    result = self.run_task(
                        task_agent, task, mcp_client=mcp_client,
                        skill_hints=skill_hints,
                    )

                    # Verify via Trial.
                    solution_script = result.get("solution_script", "")
                    if solution_script.strip():
                        verification = asyncio.run(
                            self._run_with_trial(task, solution_script)
                        )
                        result["verification"] = verification
                        result["reward"] = verification.get("reward", 0.0)
                    else:
                        result["verification"] = {"reward": 0.0}
                        result["reward"] = 0.0

                except Exception:
                    logger.exception("Task %s failed", task["task_id"])
                    result = {
                        "task_id": task["task_id"],
                        "model_answer": "",
                        "solution_script": "",
                        "metrics": None,
                        "reward": 0.0,
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
    # Trial verification (for legacy API mode)
    # ------------------------------------------------------------------

    async def _run_with_trial(self, task: dict, solution_script: str) -> dict:
        """Verify a solution script via BenchFlow Trial (legacy API mode)."""
        from benchflow.trial import Trial, TrialConfig

        task_path = Path(task["task_dir"])
        task_id = task["task_id"]
        jobs_dir = task_path.parent.parent / ".benchflow_jobs"

        config = TrialConfig.from_legacy(
            task_path=task_path,
            agent="opencode",
            model="glm-5.1",
            jobs_dir=str(jobs_dir),
            environment="docker",
        )

        trial = await Trial.create(config)
        try:
            await trial.setup()
            await trial.start()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False,
            ) as f:
                f.write(solution_script)
                tmp_path = f.name
            try:
                await trial.env.upload_file(tmp_path, "/tmp/agent_solution.py")
            finally:
                os.unlink(tmp_path)

            await trial.env.exec("python3 /tmp/agent_solution.py", timeout_sec=300)
            await trial.verify()

            result = trial._build_result()
            reward = result.rewards.get("reward", 0.0) if result.rewards else 0.0
            return {"reward": reward, "rewards": result.rewards, "test_details": []}
        except Exception as exc:
            logger.exception("Trial verification failed for %s: %s", task_id, exc)
            return {"reward": 0.0, "test_details": []}
        finally:
            try:
                await trial.cleanup()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Scoring (uses BenchFlow extract_reward)
    # ------------------------------------------------------------------

    @staticmethod
    def score(results: list[dict]) -> dict:
        """Compute scores from Docker verification results."""
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
            "scoring_method": "benchflow_trial",
            "pass_rate": passed / total if total > 0 else 0.0,
            "avg_reward": avg_reward,
            "tasks_passed": passed,
            "tasks_partial": partial,
            "tasks_failed": total - passed - partial,
            "total_tasks": total,
            "per_task": per_task,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_skillsbench_ontology_root(self) -> str | None:
        """Create a SkillsBench-only ontology root for faster MCP loading."""
        packages_root = os.path.expanduser("~/.ontoskills/packages")
        src = Path(packages_root) / "skillsbench"
        if not src.is_dir():
            return None

        dst = Path(tempfile.gettempdir()) / "skillsbench_ontology" / "skillsbench"
        dst.parent.mkdir(parents=True, exist_ok=True)

        src_ttl_count = sum(1 for _ in src.rglob("ontoskill.ttl"))
        dst_ttl_count = sum(1 for _ in dst.rglob("ontoskill.ttl")) if dst.exists() else 0

        if dst.is_dir() and src_ttl_count == dst_ttl_count:
            return str(dst.parent)

        if dst.exists():
            shutil.rmtree(str(dst))
        try:
            shutil.copytree(str(src), str(dst))
            logger.info(
                "Refreshed SkillsBench ontology: %d TTLs (was %d) at %s",
                src_ttl_count, dst_ttl_count, dst.parent,
            )
            return str(dst.parent)
        except FileExistsError:
            return str(dst.parent)
        except Exception as exc:
            logger.warning("Failed to prepare SkillsBench ontology root: %s", exc)
            return None

    def _make_scoped_traditional_agent(
        self, model: str, skills_content: dict[str, str],
    ) -> BaseAgent:
        """Create a TraditionalAgent scoped to the task's skills."""
        from benchmark.agents.traditional import TraditionalAgent, _parse_frontmatter

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        agent = TraditionalAgent.__new__(TraditionalAgent)
        BaseAgent.__init__(agent, model=model, api_key=api_key)

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
