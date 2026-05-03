# benchmark/state.py
"""Benchmark state persistence for resume per-attempt."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BenchmarkState:
    """Persists benchmark progress to disk for resume.

    Written after every single attempt so a crash preserves all
    completed attempts.
    """

    def __init__(self, path: Path, data: dict) -> None:
        self._path = path
        self._data = data

    @classmethod
    def create(
        cls,
        path: Path,
        run_id: str,
        mode: str,
        skill_hints: bool,
    ) -> "BenchmarkState":
        data = {
            "run_id": run_id,
            "mode": mode,
            "skill_hints": skill_hints,
            "tasks": {},
        }
        state = cls(path, data)
        state._flush()
        return state

    @classmethod
    def load(cls, path: Path) -> "BenchmarkState":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path, data)

    def matches(self, run_id: str, mode: str, skill_hints: bool) -> bool:
        return (
            self._data["run_id"] == run_id
            and self._data["mode"] == mode
            and self._data["skill_hints"] == skill_hints
        )

    def is_empty(self) -> bool:
        return len(self._data["tasks"]) == 0

    def should_run(self, task_id: str) -> bool:
        task = self._data["tasks"].get(task_id)
        if task is None:
            return True
        if task["status"] == "completed":
            return False
        return True

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
