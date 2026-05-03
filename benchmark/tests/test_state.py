# benchmark/tests/test_state.py
"""Tests for BenchmarkState — resume per-attempt persistence."""

import json
import pytest
from pathlib import Path
from benchmark.state import BenchmarkState


class TestBenchmarkStateCreation:
    def test_new_state_has_no_tasks(self, tmp_path):
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="test-run",
            mode="acp",
            skill_hints=True,
        )
        assert state.is_empty()
        assert state.should_run("any-task") is True

    def test_new_state_file_created_on_disk(self, tmp_path):
        path = tmp_path / "state.json"
        BenchmarkState.create(
            path=path, run_id="r", mode="acp", skill_hints=True,
        )
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["run_id"] == "r"
        assert data["mode"] == "acp"
        assert data["tasks"] == {}


class TestBenchmarkStateRecord:
    def test_record_attempt_writes_to_disk(self, tmp_path):
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="r", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 0.0, "duration_ms": 100})
        raw = json.loads((tmp_path / "state.json").read_text())
        assert raw["tasks"]["task-1"]["attempts"] == [
            {"attempt": 1, "reward": 0.0, "duration_ms": 100}
        ]

    def test_record_attempt_tracks_best_reward(self, tmp_path):
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="r", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 0.0, "duration_ms": 100})
        state.record_attempt("task-1", {"attempt": 2, "reward": 0.5, "duration_ms": 120})
        assert state.best_reward("task-1") == 0.5
        assert state.next_attempt("task-1") == 3

    def test_mark_completed_stops_should_run(self, tmp_path):
        state = BenchmarkState.create(
            path=tmp_path / "state.json",
            run_id="r", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 1.0, "duration_ms": 100})
        state.mark_completed("task-1")
        assert state.should_run("task-1") is False

    def test_resume_picks_up_from_last_attempt(self, tmp_path):
        path = tmp_path / "state.json"
        state = BenchmarkState.create(
            path=path, run_id="r", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 0.0, "duration_ms": 100})
        state.record_attempt("task-1", {"attempt": 2, "reward": 0.0, "duration_ms": 110})

        state2 = BenchmarkState.load_or_create(
            path=path, run_id="r", mode="acp", skill_hints=True,
        )
        assert state2.should_run("task-1") is True
        assert state2.next_attempt("task-1") == 3
        assert state2.best_reward("task-1") == 0.0
        assert state2.attempts_completed("task-1") == 2

    def test_resume_skips_completed_tasks(self, tmp_path):
        path = tmp_path / "state.json"
        state = BenchmarkState.create(
            path=path, run_id="r", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 1.0, "duration_ms": 100})
        state.mark_completed("task-1")

        state2 = BenchmarkState.load_or_create(
            path=path, run_id="r", mode="acp", skill_hints=True,
        )
        assert state2.should_run("task-1") is False
        assert state2.is_fully_done(["task-1"]) is True

    def test_mismatched_run_id_starts_fresh(self, tmp_path):
        path = tmp_path / "state.json"
        state = BenchmarkState.create(
            path=path, run_id="r1", mode="acp", skill_hints=True,
        )
        state.record_attempt("task-1", {"attempt": 1, "reward": 1.0, "duration_ms": 100})
        state.mark_completed("task-1")

        state2 = BenchmarkState.load_or_create(
            path=path, run_id="r2", mode="acp", skill_hints=True,
        )
        assert state2.should_run("task-1") is True
