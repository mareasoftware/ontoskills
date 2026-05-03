# benchmark/tests/test_pipelining.py
"""Tests for worker pool pipelining."""

import asyncio
import sys
import types
import pytest
from pathlib import Path
from benchmark.state import BenchmarkState

# Mock benchflow.job.RetryConfig if benchflow is not installed.
if "benchflow" not in sys.modules:
    _benchflow = types.ModuleType("benchflow")
    _benchflow_job = types.ModuleType("benchflow.job")

    class _RetryConfig:
        def __init__(self, max_retries=4):
            self.max_retries = max_retries

        def backoff_delay(self, attempt):
            return 0.01  # minimal delay in tests

    _benchflow_job.RetryConfig = _RetryConfig
    _benchflow.job = _benchflow_job
    sys.modules["benchflow"] = _benchflow
    sys.modules["benchflow.job"] = _benchflow_job

from benchmark.wrappers.skillsbench import SkillsBenchWrapper


class TestWorkerPool:
    def test_pooled_runs_all_tasks(self, tmp_path):
        """Worker pool processes all tasks in the queue."""
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="test", mode="acp", skill_hints=True,
        )

        tasks = [
            {"task_id": "t1", "task_dir": "/fake/t1"},
            {"task_id": "t2", "task_dir": "/fake/t2"},
            {"task_id": "t3", "task_dir": "/fake/t3"},
        ]

        call_log = []

        async def mock_runner(task, **kwargs):
            call_log.append(task["task_id"])
            return {"task_id": task["task_id"], "reward": 1.0}

        wrapper = SkillsBenchWrapper.__new__(SkillsBenchWrapper)
        results = asyncio.run(wrapper._run_pooled(
            tasks=tasks,
            state=state,
            trial_runner=mock_runner,
            max_attempts=3,
            workers=2,
        ))

        assert len(results) == 3
        assert set(r["task_id"] for r in results) == {"t1", "t2", "t3"}
        assert state.is_fully_done(["t1", "t2", "t3"])

    def test_pooled_retries_on_failure(self, tmp_path):
        """Worker retries tasks that don't pass."""
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="test", mode="acp", skill_hints=True,
        )

        tasks = [{"task_id": "t1", "task_dir": "/fake/t1"}]
        attempt = {"n": 0}

        async def mock_runner(task, **kwargs):
            attempt["n"] += 1
            if attempt["n"] < 3:
                return {"task_id": task["task_id"], "reward": 0.0}
            return {"task_id": task["task_id"], "reward": 1.0}

        wrapper = SkillsBenchWrapper.__new__(SkillsBenchWrapper)
        results = asyncio.run(wrapper._run_pooled(
            tasks=tasks,
            state=state,
            trial_runner=mock_runner,
            max_attempts=5,
            workers=1,
        ))

        assert len(results) == 1
        assert results[0]["reward"] == 1.0
        assert attempt["n"] == 3

    def test_pooled_resumes_from_state(self, tmp_path):
        """Worker pool skips already-completed tasks."""
        path = tmp_path / "state.json"
        state = BenchmarkState.create(
            path=path, run_id="test", mode="acp", skill_hints=True,
        )
        state.record_attempt("t1", {"attempt": 1, "reward": 1.0})
        state.mark_completed("t1")

        tasks = [
            {"task_id": "t1", "task_dir": "/fake/t1"},
            {"task_id": "t2", "task_dir": "/fake/t2"},
        ]

        call_log = []

        async def mock_runner(task, **kwargs):
            call_log.append(task["task_id"])
            return {"task_id": task["task_id"], "reward": 1.0}

        wrapper = SkillsBenchWrapper.__new__(SkillsBenchWrapper)
        results = asyncio.run(wrapper._run_pooled(
            tasks=tasks,
            state=state,
            trial_runner=mock_runner,
            max_attempts=3,
            workers=1,
        ))

        assert "t1" not in call_log
        assert "t2" in call_log
