"""GAIA benchmark wrapper.

Loads the GAIA dataset from HuggingFace, runs tasks through a BaseAgent
subclass, and scores results using exact-match comparison.

Dataset: ``gaia-benchmark/GAIA``
Levels:  ``2023_level1``, ``2023_level2``, ``2023_level3``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from datasets import load_dataset  # type: ignore[import-untyped]

from benchmark.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# read_file tool schema — given to both agents so they can read attachments
# ---------------------------------------------------------------------------

READ_FILE_TOOL: dict[str, Any] = {
    "name": "read_file",
    "description": "Read the contents of a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file to read.",
            },
        },
        "required": ["path"],
    },
}


class GAIAWrapper:
    """GAIA benchmark wrapper.

    Parameters
    ----------
    data_dir:
        Directory to cache downloaded GAIA data and attachment files.
    """

    _VALID_LEVELS = ("2023_level1", "2023_level2", "2023_level3")
    _VALID_SPLITS = ("test", "validation")

    def __init__(self, data_dir: str = "benchmark/data/gaia") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def load_dataset(
        self,
        level: str = "2023_level1",
        split: str = "test",
    ) -> list[dict]:
        """Load GAIA tasks from HuggingFace.

        Returns a list of dicts with keys:
        ``task_id``, ``question``, ``file_path``, ``gold_answer``.
        """
        if level not in self._VALID_LEVELS:
            raise ValueError(
                f"Invalid level {level!r}. Choose from {self._VALID_LEVELS}"
            )
        if split not in self._VALID_SPLITS:
            raise ValueError(
                f"Invalid split {split!r}. Choose from {self._VALID_SPLITS}"
            )

        ds = load_dataset("gaia-benchmark/GAIA", level, split=split, trust_remote_code=True)  # type: ignore[call-arg]

        tasks: list[dict] = []
        for row in ds:
            task_id = row["task_id"]
            question = row["question"]

            # Handle file attachment — GAIA stores it as a dataset File object
            file_path: str | None = None
            raw_file = row.get("file_name") or row.get("file")
            if raw_file:
                # If it is a dict-like with a "path" key (HF datasets file
                # feature), resolve to a local path.  Otherwise treat it as a
                # filename string.
                if isinstance(raw_file, dict) and "path" in raw_file:
                    attachment_dir = self.data_dir / "attachments" / level
                    attachment_dir.mkdir(parents=True, exist_ok=True)
                    dest = attachment_dir / Path(raw_file["path"]).name
                    if not dest.exists():
                        import shutil

                        shutil.copy2(raw_file["path"], dest)
                    file_path = str(dest)
                elif isinstance(raw_file, str) and raw_file.strip():
                    # It may be a filename or a local path from HF cache.
                    p = Path(raw_file)
                    if p.exists():
                        file_path = str(p)
                    else:
                        file_path = raw_file

            # The gold answer may or may not be present (gated dataset).
            gold_answer: str | None = row.get("final_answer", None)

            tasks.append({
                "task_id": str(task_id),
                "question": question,
                "file_path": file_path,
                "gold_answer": gold_answer,
            })

        logger.info("Loaded %d GAIA tasks (level=%s, split=%s)", len(tasks), level, split)
        return tasks

    # ------------------------------------------------------------------
    # Single-task execution
    # ------------------------------------------------------------------

    def run_task(self, agent: BaseAgent, task: dict) -> dict:
        """Run a single GAIA task through an agent.

        Both agents receive a ``read_file`` tool so they can inspect file
        attachments.  For TraditionalAgent (which normally has no tools) this
        is the only tool provided.

        Returns a dict with:
        ``task_id``, ``model_answer``, ``metrics`` (AgentResult).
        """
        # Build the task prompt, including file-attachment hint when present.
        prompt = task["question"]
        if task.get("file_path"):
            prompt += (
                f"\n\n[Attachment available at: {task['file_path']}. "
                "Use the read_file tool to inspect it if needed.]"
            )

        # Inject read_file into the agent's tools for this run.
        original_get_tools = agent.get_tools

        def _patched_get_tools() -> list[dict] | None:
            base_tools = original_get_tools()
            if base_tools is None:
                return [READ_FILE_TOOL]
            # Avoid duplicating if already present.
            names = {t["name"] for t in base_tools}
            if "read_file" not in names:
                return [*base_tools, READ_FILE_TOOL]
            return base_tools

        agent.get_tools = _patched_get_tools  # type: ignore[assignment]

        try:
            result: AgentResult = agent.run(prompt, max_turns=15)
        except RuntimeError as exc:
            # TraditionalAgent cannot execute tool calls — if the model
            # attempts to call read_file this will raise.  Return the
            # error message as the answer so the benchmark can continue.
            logger.warning("Agent RuntimeError on task %s: %s", task["task_id"], exc)
            result = AgentResult(
                answer=f"[Agent error: {exc}]",
                input_tokens=0,
                output_tokens=0,
                total_latency_ms=0.0,
                tool_calls=0,
                turns=0,
                context_overflow=False,
            )
        finally:
            # Restore original method.
            agent.get_tools = original_get_tools  # type: ignore[assignment]

        return {
            "task_id": task["task_id"],
            "model_answer": result.answer,
            "metrics": result,
        }

    # ------------------------------------------------------------------
    # Full benchmark run
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        agent: BaseAgent,
        level: str = "2023_level1",
        split: str = "test",
        max_tasks: int | None = None,
    ) -> list[dict]:
        """Run all (or *max_tasks*) GAIA tasks through *agent*.

        Returns a list of result dicts (one per task).
        """
        tasks = self.load_dataset(level=level, split=split)
        if max_tasks is not None:
            tasks = tasks[:max_tasks]

        results: list[dict] = []
        for i, task in enumerate(tasks, 1):
            logger.info("Task %d/%d: %s", i, len(tasks), task["task_id"])
            try:
                result = self.run_task(agent, task)
            except Exception:
                logger.exception("Task %s failed", task["task_id"])
                result = {
                    "task_id": task["task_id"],
                    "model_answer": "",
                    "metrics": None,
                }
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score(results: list[dict], gold_answers: dict[str, str]) -> dict:
        """Score results against gold answers using case-insensitive exact match.

        Parameters
        ----------
        results:
            List of result dicts from ``run_benchmark`` / ``run_task``.
        gold_answers:
            Mapping of ``task_id`` -> gold answer string.

        Returns
        -------
        dict with ``accuracy`` (float 0-1) and ``per_task`` details.
        """
        per_task: list[dict] = []
        correct = 0
        total = 0

        for r in results:
            task_id = r["task_id"]
            model_answer = r.get("model_answer", "")
            gold = gold_answers.get(task_id)

            if gold is None:
                match = None  # no gold answer available
            else:
                total += 1
                match = model_answer.strip().lower() == gold.strip().lower()
                if match:
                    correct += 1

            per_task.append({
                "task_id": task_id,
                "model_answer": model_answer,
                "gold_answer": gold,
                "correct": match,
            })

        accuracy = correct / total if total > 0 else 0.0
        return {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
            "per_task": per_task,
        }

    # ------------------------------------------------------------------
    # Submission output
    # ------------------------------------------------------------------

    def write_submission(self, results: list[dict], output_path: str) -> None:
        """Write results as JSONL (one JSON object per line).

        Each line: ``{"task_id": ..., "model_answer": ...}``
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for r in results:
                entry = {
                    "task_id": r["task_id"],
                    "model_answer": r.get("model_answer", ""),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("Wrote %d results to %s", len(results), path)
