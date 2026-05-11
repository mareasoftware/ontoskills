from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EngineOutput:
    """Parsed output from a CLI agent run."""
    num_turns: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0


class AgentEngine:
    """Encapsulates all differences between agent CLIs (claude vs opencode).

    Each engine knows its binary path, model name, environment variables,
    CLI command syntax, JSON output format, and MCP config format.
    """

    name: str = ""
    bin_name: str = ""
    bin_path: str = ""
    model: str = ""
    skills_path: str = ""
    download_url: str | None = None

    @property
    def env_vars(self) -> dict[str, str]:
        return {}

    def build_run_cmd(self, instruction: str) -> str:
        raise NotImplementedError

    def warmup_cmd(self) -> str:
        return f"{self.bin_name} --version 2>/dev/null; echo 'WARMUP_DONE'"

    def parse_output(self, stdout: str) -> EngineOutput:
        raise NotImplementedError

    def mcp_config(self, ontomcp_path: str, ontology_root: str) -> tuple[str, str] | None:
        """Return (filename, content) for MCP config, or None if not supported."""
        return None
