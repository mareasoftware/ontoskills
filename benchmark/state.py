# benchmark/state.py
"""Benchmark state persistence for resume per-attempt."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RATE_LIMIT_CONSECUTIVE_MAX = 5


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
            "rate_limit_count": 0,
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
            self._data["mode"] == mode
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

    def record_attempt(self, task_id: str, result: dict, *, counted: bool = True) -> None:
        if task_id not in self._data["tasks"]:
            self._data["tasks"][task_id] = {
                "status": "in_progress",
                "attempts": [],
                "best_reward": 0.0,
            }
        task = self._data["tasks"][task_id]
        entry = dict(result)
        entry["counted"] = counted
        task["attempts"].append(entry)
        if counted:
            reward = result.get("reward", 0.0)
            if reward > task["best_reward"]:
                task["best_reward"] = reward
        self._flush()

    def mark_completed(self, task_id: str) -> None:
        if task_id in self._data["tasks"]:
            self._data["tasks"][task_id]["status"] = "completed"
            self._flush()

    def next_attempt(self, task_id: str) -> int:
        task = self._data["tasks"].get(task_id)
        if task is None:
            return 1
        counted = sum(1 for a in task["attempts"] if a.get("counted", True))
        return counted + 1

    def best_reward(self, task_id: str) -> float:
        task = self._data["tasks"].get(task_id)
        if task is None:
            return 0.0
        return task.get("best_reward", 0.0)

    def attempts_completed(self, task_id: str) -> int:
        task = self._data["tasks"].get(task_id)
        if task is None:
            return 0
        return sum(1 for a in task.get("attempts", []) if a.get("counted", True))

    def is_fully_done(self, all_task_ids: list[str]) -> bool:
        return all(
            self._data["tasks"].get(tid, {}).get("status") == "completed"
            for tid in all_task_ids
        )

    def get_results(self) -> list[dict]:
        results = []
        for tid, task in self._data["tasks"].items():
            attempts = task.get("attempts", [])
            best = task.get("best_reward", 0.0)
            best_attempt = max(attempts, key=lambda a: a.get("reward", 0.0)) if attempts else {}
            entry = dict(best_attempt)
            entry["task_id"] = tid
            entry["best_reward"] = best
            entry["attempts_completed"] = len(attempts)
            results.append(entry)
        return results

    @classmethod
    def load_or_create(
        cls,
        path: Path,
        run_id: str,
        mode: str,
        skill_hints: bool,
    ) -> "BenchmarkState":
        if path.exists():
            try:
                state = cls.load(path)
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.warning("Corrupted state file %s, starting fresh", path)
                return cls.create(path, run_id, mode, skill_hints)
            if state.matches(run_id, mode, skill_hints):
                logger.info("Resuming from %s (%d tasks done)", path, len(state.completed_task_ids()))
                return state
            logger.info("State file mismatch, starting fresh")
        return cls.create(path, run_id, mode, skill_hints)

    def completed_task_ids(self) -> list[str]:
        return [
            tid for tid, t in self._data["tasks"].items()
            if t["status"] == "completed"
        ]

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── rate limit tracking ──

    @property
    def rate_limit_count(self) -> int:
        return self._data.get("rate_limit_count", 0)

    def increment_rate_limit(self) -> int:
        self._data["rate_limit_count"] = self.rate_limit_count + 1
        self._flush()
        return self._data["rate_limit_count"]

    def reset_rate_limit(self) -> None:
        self._data["rate_limit_count"] = 0
        self._flush()
