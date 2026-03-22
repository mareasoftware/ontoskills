"""Minimal .env loader for local compiler configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env() -> None:
    """Load a repo-local .env file without overriding existing env vars."""
    # src/ -> core/ -> project root
    project_root = Path(__file__).parent.parent.parent.resolve()
    env_path = project_root / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)
