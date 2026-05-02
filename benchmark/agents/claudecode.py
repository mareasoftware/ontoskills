"""Claude Code CLI agent for the OntoSkills benchmark.

Uses the Claude Code CLI in ``--print`` mode for realistic evaluation:
file exploration, multi-turn reasoning, tool use (Read, Write, Bash).

Two modes:
  - ``traditional`` — skills copied to ``.claude/skills/`` (Claude Code's
    native skill discovery, same as Claude Code in production)
  - ``ontoskills`` — skills loaded via MCP tools (ontomcp with compiled TTLs),
    no skills in ``.claude/skills/`` (the MCP tools are the discovery mechanism)

Both modes use the same base prompt and file access tools.  The only
difference is **how skills are discovered and loaded**.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .base import AgentResult, BaseAgent
from .utils import extract_python_code

logger = logging.getLogger(__name__)

# Default ontomcp binary path.
_ONTOMCP_BIN = os.path.expanduser("~/.ontoskills/bin/ontomcp")


class ClaudeCodeAgent(BaseAgent):
    """Agent that delegates to the Claude Code CLI for realistic evaluation.

    Parameters
    ----------
    model:
        Model ID (e.g. ``glm-5.1``).
    mode:
        ``"traditional"`` or ``"ontoskills"``.  Determines how skills are
        provided to Claude Code.
    skills_dir:
        Path to SKILL.md files (used in traditional mode for script copying).
    ontomcp_bin:
        Path to the ontomcp binary (used in ontoskills mode).
    api_key:
        Anthropic API key (or proxy key).
    """

    def __init__(
        self,
        model: str,
        mode: str = "traditional",
        skills_dir: str | None = None,
        ontomcp_bin: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model=model, api_key=api_key)
        if mode not in ("traditional", "ontoskills"):
            raise ValueError(f"mode must be 'traditional' or 'ontoskills', got '{mode}'")
        self.mode = mode
        self.skills_dir = skills_dir
        self.ontomcp_bin = ontomcp_bin or _ONTOMCP_BIN
        self.claude_bin = self._find_claude_bin()
        self._tools: list[dict] | None = None
        self._work_dir: Path | None = None
        self._mcp_config_path: str | None = None
        self._ontology_root: str | None = None

    @staticmethod
    def _find_claude_bin() -> str:
        import shutil as sh
        path = sh.which("claude")
        if not path:
            raise FileNotFoundError(
                "claude CLI not found. Install Claude Code: "
                "npm install -g @anthropic-ai/claude-code"
            )
        return path

    def get_system_prompt(self) -> str:
        raise NotImplementedError("Use run_with_cli() for ClaudeCodeAgent")

    def get_tools(self) -> list[dict] | None:
        return self._tools

    # ------------------------------------------------------------------
    # Task environment setup
    # ------------------------------------------------------------------

    def setup_task_env(self, task: dict) -> Path:
        """Prepare a working directory with task files for Claude Code.

        In ``traditional`` mode: copies SKILL.md files to ``.claude/skills/``.
        In ``ontoskills`` mode: creates an MCP config for ontomcp (no skills
        in ``.claude/skills/`` — the agent discovers skills via MCP tools).
        """
        task_dir = Path(task["task_dir"])
        if self._work_dir and self._work_dir.exists():
            shutil.rmtree(self._work_dir, ignore_errors=True)
        work_dir = Path(tempfile.mkdtemp(prefix=f"sb_cc_{self.mode}_"))
        self._work_dir = work_dir

        # --- Copy environment files (not Dockerfile, not skills/) ---
        env_src = task_dir / "environment"
        if env_src.is_dir():
            for item in env_src.iterdir():
                if item.name == "Dockerfile":
                    shutil.copy2(item, work_dir / "Dockerfile.reference")
                    continue
                if item.name == "skills":
                    continue  # handled per mode below
                if item.is_dir():
                    shutil.copytree(item, work_dir / item.name)
                else:
                    shutil.copy2(item, work_dir / item.name)

            # Copy skill helper scripts (available in both modes).
            skill_ids = task.get("skill_ids", [])
            for sid in skill_ids:
                scripts_src = env_src / "skills" / sid / "scripts"
                if scripts_src.is_dir():
                    scripts_dest = work_dir / "skill_scripts" / sid
                    shutil.copytree(scripts_src, scripts_dest)

        # --- Copy tests ---
        tests_src = task_dir / "tests"
        if tests_src.is_dir():
            shutil.copytree(tests_src, work_dir / "tests")

        # --- Write instruction ---
        instruction = task.get("instruction", "")
        (work_dir / "TASK_INSTRUCTION.md").write_text(instruction, encoding="utf-8")

        # --- Mode-specific skill setup ---
        skill_ids = task.get("skill_ids", [])
        skills_content = task.get("skills_content", {})

        if self.mode == "traditional":
            self._setup_traditional_skills(work_dir, skills_content, skill_ids, env_src)
        else:
            self._setup_ontoskills_mcp(work_dir, skill_ids)

        # --- Write CLAUDE.md ---
        self._write_claude_md(work_dir)

        return work_dir

    def _setup_traditional_skills(
        self,
        work_dir: Path,
        skills_content: dict[str, str],
        skill_ids: list[str],
        env_src: Path,
    ) -> None:
        """Copy SKILL.md files to .claude/skills/ for native discovery."""
        if not skills_content:
            return

        skills_dest = work_dir / ".claude" / "skills"
        skills_dest.mkdir(parents=True, exist_ok=True)

        for sid, content in skills_content.items():
            skill_dir = skills_dest / sid
            skill_dir.mkdir(exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

        logger.debug(
            "Traditional mode: %d skills in .claude/skills/",
            len(skills_content),
        )

    def _setup_ontoskills_mcp(
        self,
        work_dir: Path,
        skill_ids: list[str],
    ) -> None:
        """Create MCP config for ontomcp."""
        ontology_root = self._ontology_root or self._prepare_ontology_root()
        if not ontology_root:
            logger.warning("OntoSkills: no ontology root available, MCP disabled")
            return

        mcp_config = {
            "mcpServers": {
                "ontoskills": {
                    "command": self.ontomcp_bin,
                    "args": ["--ontology-root", ontology_root],
                    "type": "stdio",
                }
            }
        }

        config_path = work_dir / ".mcp_config.json"
        config_path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
        self._mcp_config_path = str(config_path)

        logger.debug(
            "OntoSkills mode: MCP config at %s (ontology_root=%s)",
            config_path, ontology_root,
        )

    def _prepare_ontology_root(self) -> str | None:
        """Prepare a SkillsBench-only ontology root for faster MCP loading."""
        if self._ontology_root:
            return self._ontology_root

        packages_root = os.path.expanduser("~/.ontoskills/packages")
        src = Path(packages_root) / "skillsbench"
        if not src.is_dir():
            logger.warning("No skillsbench package at %s", src)
            return None

        dst = Path(tempfile.gettempdir()) / "skillsbench_ontology" / "skillsbench"
        dst.parent.mkdir(parents=True, exist_ok=True)

        src_ttl_count = sum(1 for _ in src.rglob("ontoskill.ttl"))
        dst_ttl_count = sum(1 for _ in dst.rglob("ontoskill.ttl")) if dst.exists() else 0

        if not dst.exists() or src_ttl_count != dst_ttl_count:
            if dst.exists():
                shutil.rmtree(str(dst))
            try:
                shutil.copytree(str(src), str(dst))
                logger.info(
                    "Refreshed SkillsBench ontology: %d TTLs (was %d) at %s",
                    src_ttl_count, dst_ttl_count, dst.parent,
                )
            except FileExistsError:
                pass

        self._ontology_root = str(dst.parent)
        return self._ontology_root

    def _write_claude_md(self, work_dir: Path) -> None:
        """Write CLAUDE.md with task-specific instructions."""
        skill_section = ""
        if self.mode == "traditional":
            skill_section = (
                "- `.claude/skills/` — skill documentation.  "
                "**Read the relevant skills BEFORE writing code.**\n"
            )
        else:
            skill_section = (
                "- MCP tools — use `ontoskill` to find or load skill knowledge.\n"
            )

        # Parse WORKDIR and COPY lines from Dockerfile.reference.
        workdir = "/root"
        copy_lines: list[str] = []
        dockerfile_path = work_dir / "Dockerfile.reference"
        if dockerfile_path.exists():
            for line in dockerfile_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("WORKDIR"):
                    parts = stripped.split(None, 1)
                    if len(parts) > 1:
                        workdir = parts[1].strip()
                if stripped.upper().startswith("COPY"):
                    copy_lines.append(stripped)

        copy_section = ""
        if copy_lines:
            copy_section = (
                "### File mapping (from Dockerfile)\n"
                + "\n".join(f"- `{c}`" for c in copy_lines) + "\n\n"
            )

        claude_md = (
            "# Task Environment\n\n"
            "## Your task\n"
            "Read TASK_INSTRUCTION.md for the task description.\n\n"
            "## CRITICAL: Container vs Host paths\n"
            "You are working on the HOST machine, but your solution.py will run inside a Docker container.\n"
            f"- Container WORKDIR: `{workdir}`\n"
            "- Your solution.py runs as `/tmp/agent_solution.py` inside the container.\n"
            "- **ALL paths in solution.py MUST be CONTAINER paths** (e.g., `/root/data.csv`), "
            "NOT host paths (e.g., `/tmp/sb_cc_...`).\n"
            "- The local files you see are copies of what's inside the container.\n"
            "- Paths in TASK_INSTRUCTION.md are already container paths — use them directly.\n\n"
            f"{copy_section}"
            "## Key files\n"
            "- `tests/test_outputs.py` — **READ THIS FIRST** to understand exactly what output is expected.\n"
            "- `Dockerfile.reference` — packages installed + file layout in container.\n"
            f"{skill_section}"
            "- `skill_scripts/` — helper scripts from skills. In your solution.py, import with:\n"
            "  ```python\n"
            "  import sys; sys.path.insert(0, '/tmp/skill_scripts/<skill-id>')\n"
            "  ```\n"
            "- Data files in the root directory — input data for the task.\n\n"
            "## Output\n"
            "Write a `solution.py` script that produces all required output files.\n"
            "The script will be executed inside a Docker container with `python3 solution.py`.\n"
            "**COMPLIANCE:** Follow the procedures, constraints, and best practices defined in the skills strictly. "
            "Your code must pass all tests in `tests/test_outputs.py`.\n"
            "**DO NOT reference any `/tmp/sb_cc_...` paths in your code.** "
            "Use the container paths from TASK_INSTRUCTION.md.\n"
        )

        (work_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Remove temp working directories."""
        if self._work_dir and self._work_dir.exists():
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None

    # ------------------------------------------------------------------
    # CLI execution
    # ------------------------------------------------------------------

    def run_with_cli(
        self,
        task: dict,
        max_turns: int | None = None,
        max_budget: float = 2.00,
        timeout: int = 900,
    ) -> dict:
        """Run the task using Claude Code CLI in --print mode.

        Returns a dict with solution_path, work_dir, result text, usage, etc.
        """
        work_dir = self._work_dir
        if not work_dir:
            raise RuntimeError("Call setup_task_env() first")

        instruction = task.get("instruction", "")
        skill_ids = task.get("skill_ids", [])

        # Build mode-specific skill hint.
        hints_enabled = task.get("skill_hints", True)
        if not hints_enabled:
            skill_hint = ""
        elif self.mode == "traditional":
            skill_hint = (
                f"Relevant skills: {', '.join(skill_ids)}. "
                f"Read them from .claude/skills/ before writing code."
            ) if skill_ids else ""
        else:
            skill_hint = (
                f"Relevant skills: {', '.join(skill_ids)}. "
                f"Call ontoskill with query describing the task to load skill knowledge."
            ) if skill_ids else ""

        prompt = (
            "Read TASK_INSTRUCTION.md to understand the task.\n"
            "Write a solution.py script that produces all required output files.\n"
            "The script runs inside a Docker container with: python3 solution.py\n"
            "IMPORTANT: Use CONTAINER paths in your code (e.g., /root/data.csv), "
            "NOT host paths (e.g., /tmp/sb_cc_...). Read Dockerfile.reference for the container file layout.\n"
            f"{skill_hint}\n"
            f"TASK: {instruction}"
        )

        # Build CLI command.
        cmd = [
            self.claude_bin,
            "-p",
            "--model", self.model,
            "--bare",
            "--output-format", "json",
            "--max-budget-usd", str(max_budget),
            "--dangerously-skip-permissions",
        ]

        # Only set max-turns if explicitly provided (otherwise Claude Code decides).
        if max_turns is not None:
            cmd.extend(["--max-turns", str(max_turns)])

        if self._mcp_config_path:
            cmd.extend(["--mcp-config", self._mcp_config_path])

        # Use -- to separate flags from the positional prompt argument.
        # Without this, --mcp-config (which accepts multiple values) would
        # consume the prompt as another config path.
        cmd.append("--")
        cmd.append(prompt)

        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = self.api_key
        if os.environ.get("ANTHROPIC_BASE_URL"):
            env["ANTHROPIC_BASE_URL"] = os.environ["ANTHROPIC_BASE_URL"]

        start = time.perf_counter()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(work_dir),
                env=env,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                stdout, stderr = proc.communicate()
                duration_ms = (time.perf_counter() - start) * 1000
                logger.warning("Claude Code timed out after %ds", timeout)
                return {
                    "result": "[timeout]",
                    "work_dir": str(work_dir),
                    "solution_path": str(work_dir / "solution.py"),
                    "duration_ms": duration_ms,
                    "usage": {},
                    "num_turns": 0,
                    "total_cost_usd": 0,
                }

            duration_ms = (time.perf_counter() - start) * 1000
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Parse JSON output.
            cli_result: dict = {}
            try:
                parsed = json.loads(stdout_text)
                cli_result["result"] = parsed.get("result", "")
                cli_result["usage"] = parsed.get("usage", {})
                cli_result["num_turns"] = parsed.get("num_turns", 0)
                cli_result["total_cost_usd"] = parsed.get("total_cost_usd", 0)
            except json.JSONDecodeError:
                cli_result["result"] = stdout_text
                cli_result["usage"] = {}
                cli_result["num_turns"] = 0
                cli_result["total_cost_usd"] = 0

            if proc.returncode != 0 and stderr_text:
                logger.warning("Claude Code stderr: %s", stderr_text[:500])

            cli_result["duration_ms"] = duration_ms
            cli_result["work_dir"] = str(work_dir)
            cli_result["solution_path"] = str(work_dir / "solution.py")

            # Fallback: extract code from response if no file written.
            if not (work_dir / "solution.py").exists():
                answer = cli_result.get("result", "")
                code = extract_python_code(answer)
                if code:
                    (work_dir / "solution.py").write_text(code, encoding="utf-8")
                    logger.info("Extracted solution.py from response text (%d chars)", len(code))
                else:
                    logger.warning("Claude Code did not create solution.py")

            return cli_result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.warning("Claude Code error: %s", exc)
            return {
                "result": f"[error: {exc}]",
                "work_dir": str(work_dir),
                "solution_path": str(work_dir / "solution.py"),
                "duration_ms": duration_ms,
                "usage": {},
                "num_turns": 0,
                "total_cost_usd": 0,
            }

    def run_with_feedback(
        self,
        task: dict,
        feedback: str,
        max_budget: float = 0.67,
        timeout: int = 300,
    ) -> dict:
        """Run a follow-up attempt with Docker/test error feedback.

        Like run_with_cli() but with a feedback prompt instead of the original
        task prompt. The work_dir and env are already set up from the first call.
        """
        work_dir = self._work_dir
        if not work_dir:
            raise RuntimeError("Call setup_task_env() first")

        task_instruction = task.get("instruction", "")
        prompt = (
            "Your previous solution.py failed verification inside a Docker container.\n\n"
        )
        if task_instruction:
            prompt += f"Original task: {task_instruction[:500]}\n\n"
        prompt += (
            f"{feedback}\n\n"
            "Write a corrected solution.py that fixes the errors above.\n"
            "IMPORTANT: Use CONTAINER paths (e.g., /root/data.csv), NOT host paths.\n"
        )

        cmd = [
            self.claude_bin,
            "-p",
            "--model", self.model,
            "--bare",
            "--output-format", "json",
            "--max-budget-usd", str(max_budget),
            "--dangerously-skip-permissions",
        ]

        if self._mcp_config_path:
            cmd.extend(["--mcp-config", self._mcp_config_path])

        cmd.append("--")
        cmd.append(prompt)

        env = os.environ.copy()
        env["ANTHROPIC_API_KEY"] = self.api_key
        if os.environ.get("ANTHROPIC_BASE_URL"):
            env["ANTHROPIC_BASE_URL"] = os.environ["ANTHROPIC_BASE_URL"]

        start = time.perf_counter()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(work_dir),
                env=env,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                stdout, stderr = proc.communicate()
                duration_ms = (time.perf_counter() - start) * 1000
                return {
                    "result": "[timeout]",
                    "work_dir": str(work_dir),
                    "solution_path": str(work_dir / "solution.py"),
                    "duration_ms": duration_ms,
                    "usage": {},
                    "num_turns": 0,
                    "total_cost_usd": 0,
                }

            duration_ms = (time.perf_counter() - start) * 1000
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode != 0 and stderr_text:
                logger.warning("Claude Code feedback stderr: %s", stderr_text[:500])

            cli_result: dict = {}
            try:
                parsed = json.loads(stdout_text)
                cli_result["result"] = parsed.get("result", "")
                cli_result["usage"] = parsed.get("usage", {})
                cli_result["num_turns"] = parsed.get("num_turns", 0)
                cli_result["total_cost_usd"] = parsed.get("total_cost_usd", 0)
            except json.JSONDecodeError:
                cli_result["result"] = stdout_text
                cli_result["usage"] = {}
                cli_result["num_turns"] = 0
                cli_result["total_cost_usd"] = 0

            cli_result["duration_ms"] = duration_ms
            cli_result["work_dir"] = str(work_dir)
            cli_result["solution_path"] = str(work_dir / "solution.py")

            if not (work_dir / "solution.py").exists():
                answer = cli_result.get("result", "")
                code = extract_python_code(answer)
                if code:
                    (work_dir / "solution.py").write_text(code, encoding="utf-8")

            return cli_result

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return {
                "result": f"[error: {exc}]",
                "work_dir": str(work_dir),
                "solution_path": str(work_dir / "solution.py"),
                "duration_ms": duration_ms,
                "usage": {},
                "num_turns": 0,
                "total_cost_usd": 0,
            }

    # ------------------------------------------------------------------
    # BaseAgent interface (unused — CLI mode only)
    # ------------------------------------------------------------------

    def run(self, task_prompt: str, max_turns: int = 10) -> AgentResult:
        raise NotImplementedError("Use run_with_cli() for ClaudeCodeAgent")

    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        raise NotImplementedError("Use run_with_cli() for ClaudeCodeAgent")
