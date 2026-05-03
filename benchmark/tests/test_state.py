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
