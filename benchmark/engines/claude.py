from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path

from .base import AgentEngine, EngineOutput

logger = logging.getLogger(__name__)

_CLAUDE_BIN_PATH = os.environ.get("CLAUDE_BIN_PATH") or str(
    Path("~/.local/share/claude/versions/2.1.128").expanduser()
)


class ClaudeEngine(AgentEngine):
    name = "claude"
    bin_name = "claude"
    bin_path = _CLAUDE_BIN_PATH
    model = "glm-5.1"
    skills_path = "$HOME/.claude/skills"
    download_url = None  # uploaded from host binary

    @property
    def env_vars(self) -> dict[str, str]:
        key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        return {
            "ANTHROPIC_API_KEY": key,
            "ANTHROPIC_AUTH_TOKEN": key,
            "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", ""),
            "ANTHROPIC_MODEL": self.model,
            "HOME": "/root",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        }

    def build_run_cmd(self, instruction: str) -> str:
        return (
            f"claude -p {shlex.quote(instruction)} "
            f"--output-format json --max-turns 50 "
            f"--dangerously-skip-permissions"
        )

    def parse_output(self, stdout: str) -> EngineOutput:
        """Parse claude JSON array output format."""
        output = EngineOutput()
        if not stdout:
            return output

        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                for item in reversed(data):
                    if isinstance(item, dict):
                        nt = item.get("num_turns")
                        if nt is not None:
                            output.num_turns = int(nt)
                            break
            elif isinstance(data, dict):
                nt = data.get("num_turns")
                if nt is not None:
                    output.num_turns = int(nt)
        except json.JSONDecodeError:
            for line in reversed(stdout.strip().split("\n")):
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        nt = item.get("num_turns")
                        if nt is not None:
                            output.num_turns = int(nt)
                            break
                except (json.JSONDecodeError, AttributeError):
                    continue

        output.tool_calls = _claude_tool_usage(stdout)
        return output

    def mcp_config(self, ontomcp_path: str, ontology_root: str) -> tuple[str, str]:
        content = json.dumps({
            "mcpServers": {
                "onto": {
                    "command": ontomcp_path,
                    "args": ["--ontology-root", ontology_root],
                    "alwaysLoad": False,
                }
            }
        })
        return (".mcp.json", content)


def _claude_tool_usage(stdout: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        events = json.loads(stdout)
        if isinstance(events, list):
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                if ev.get("type") == "tool_use":
                    name = ev.get("name", ev.get("tool_name", "?"))
                    counts[name] = counts.get(name, 0) + 1
                if ev.get("type") == "assistant":
                    msg = ev.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", block.get("tool_name", "?"))
                                counts[name] = counts.get(name, 0) + 1
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return counts
