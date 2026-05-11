from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path

from .base import AgentEngine, EngineOutput

logger = logging.getLogger(__name__)

_OPENCODE_BIN_PATH = os.environ.get("OPENCODE_BIN_PATH") or str(
    Path("~/.opencode/bin/opencode").expanduser()
)

# Where to download opencode for in-container install.
_OPENCODE_VERSION = "1.14.48"
_OPENCODE_DOWNLOAD_URL = (
    f"https://github.com/anomalyco/opencode/releases/download/"
    f"v{_OPENCODE_VERSION}/opencode-linux-x64.tar.gz"
)


class OpencodeEngine(AgentEngine):
    name = "opencode"
    bin_name = "opencode"
    bin_path = _OPENCODE_BIN_PATH
    model = "opencode-go/deepseek-v4-flash"
    skills_path = "~/.opencode/skills"
    download_url = _OPENCODE_DOWNLOAD_URL

    @property
    def env_vars(self) -> dict[str, str]:
        return {
            "OPENCODE_API_KEY": os.environ.get("OPENCODE_API_KEY", ""),
            "HOME": "/root",
        }

    def build_run_cmd(self, instruction: str) -> str:
        return (
            f"opencode run {shlex.quote(instruction)} "
            f"--format json -m {self.model} "
            f"--dangerously-skip-permissions"
        )

    def parse_output(self, stdout: str) -> EngineOutput:
        """Parse opencode NDJSON format (line-delimited JSON events)."""
        output = EngineOutput()
        if not stdout:
            return output

        tool_counts: dict[str, int] = {}
        total_tokens: dict = {}
        seen_step_finish = False

        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue

            ev_type = ev.get("type", "")
            part = ev.get("part", {})

            if ev_type == "tool_use" and isinstance(part, dict):
                tool_name = part.get("tool") or part.get("name", "?")
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

            if ev_type == "step_finish" and isinstance(part, dict):
                if part.get("type") == "step-finish":
                    tokens = part.get("tokens", {})
                    if isinstance(tokens, dict):
                        total_tokens = tokens
                    cost = part.get("cost", 0.0)
                    if isinstance(cost, (int, float)):
                        output.cost = cost
                    seen_step_finish = True

        output.tool_calls = tool_counts
        output.tokens = total_tokens
        output.num_turns = sum(tool_counts.values())
        return output

    def mcp_config(self, ontomcp_path: str, ontology_root: str) -> tuple[str, str] | None:
        return None
