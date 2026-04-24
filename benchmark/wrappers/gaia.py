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

        # Use snapshot_download + local load to handle gated datasets.
        import os
        from huggingface_hub import snapshot_download

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        data_dir = snapshot_download(
            repo_id="gaia-benchmark/GAIA",
            repo_type="dataset",
            token=token,
        )
        ds = load_dataset(data_dir, level, split=split)

        tasks: list[dict] = []
        for row in ds:
            task_id = row["task_id"]
            # GAIA uses title-case column names
            question = row.get("Question", row.get("question", ""))

            # Handle file attachment.
            file_path: str | None = None
            raw_file = row.get("file_name") or row.get("file_path") or row.get("file")
            if raw_file:
                if isinstance(raw_file, dict) and "path" in raw_file:
                    attachment_dir = self.data_dir / "attachments" / level
                    attachment_dir.mkdir(parents=True, exist_ok=True)
                    dest = attachment_dir / Path(raw_file["path"]).name
                    if not dest.exists():
                        import shutil
                        shutil.copy2(raw_file["path"], dest)
                    file_path = str(dest)
                elif isinstance(raw_file, str) and raw_file.strip():
                    p = Path(raw_file)
                    if p.exists():
                        file_path = str(p)
                    else:
                        file_path = raw_file

            # Gold answer (title-case "Final answer" in GAIA).
            gold_answer: str | None = row.get("Final answer") or row.get("final_answer", None)
            # Some gold answers are "?" (withheld).
            if gold_answer and gold_answer.strip() in ("?", ""):
                gold_answer = None

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

        # Patch get_tools to include read_file.
        original_get_tools = agent.get_tools
        original_run_turn = agent.run_turn

        def _patched_get_tools() -> list[dict] | None:
            base_tools = original_get_tools()
            if base_tools is None:
                return [READ_FILE_TOOL]
            names = {t["name"] for t in base_tools}
            if "read_file" not in names:
                return [*base_tools, READ_FILE_TOOL]
            return base_tools

        def _patched_run_turn(messages: list[dict]) -> tuple[dict, dict]:
            """Execute one turn with read_file handling.

            Routes read_file calls to local file I/O, delegates MCP tool
            names to the original agent for MCP routing, and handles all
            other tool calls by recording them.
            """
            import time as _time

            start = _time.perf_counter()
            response = agent._call_api(messages)
            latency_ms = (_time.perf_counter() - start) * 1000

            content_blocks: list[dict] = []
            for block in response.content:
                if block.type == "text":
                    content_blocks.append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "tool_use":
                    content_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            assistant_msg: dict = {
                "role": "assistant",
                "content": content_blocks,
            }

            tool_calls = 0
            tool_result_blocks: list[dict] = []
            for block in content_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tool_name = block["name"]
                tool_input = block.get("input", {})

                if tool_name == "read_file":
                    file_path = tool_input.get("path", "")
                    try:
                        from pathlib import Path as _P
                        content = _P(file_path).read_text(encoding="utf-8")
                        result_text = content
                        is_error = False
                    except FileNotFoundError:
                        result_text = f"Error: file not found: {file_path}"
                        is_error = True
                    except Exception as exc:
                        result_text = f"Error reading {file_path}: {exc}"
                        is_error = True
                else:
                    # Delegate to the original run_turn for MCP tools etc.
                    # This shouldn't happen normally — only read_file is
                    # injected. Return an error for unknown tools.
                    result_text = f"Error: unknown tool {tool_name}"
                    is_error = True

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_text,
                    "is_error": is_error,
                })

            if tool_result_blocks:
                messages.append(assistant_msg)
                messages.append({
                    "role": "user",
                    "content": tool_result_blocks,
                })

            metrics: dict = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "tool_calls": tool_calls,
            }
            return assistant_msg, metrics

        agent.get_tools = _patched_get_tools  # type: ignore[assignment]
        agent.run_turn = _patched_run_turn  # type: ignore[assignment]

        try:
            # If the agent is an OntoSkillsAgent, start MCP lifecycle.
            _mcp_started = False
            if hasattr(agent, "_mcp_client"):
                agent._mcp_client.__enter__()
                agent._mcp_client.initialize()
                _mcp_started = True

            # Custom run-loop (same pattern as SWE-bench to avoid
            # double-appending when run_turn also appends messages).
            messages: list[dict] = [{"role": "user", "content": prompt}]
            total_input = 0
            total_output = 0
            total_latency_ms = 0.0
            total_tool_calls = 0
            turns = 0
            context_overflow = False

            for _ in range(15):
                assistant_msg, metrics = agent.run_turn(messages)
                turns += 1
                total_input += metrics["input_tokens"]
                total_output += metrics["output_tokens"]
                total_latency_ms += metrics["latency_ms"]
                total_tool_calls += metrics["tool_calls"]

                tool_use_blocks = [
                    b for b in (assistant_msg.get("content") or [])
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ]

                if tool_use_blocks:
                    # run_turn already appended assistant_msg + tool_results.
                    pass
                else:
                    messages.append(assistant_msg)
                    break

            # Extract final text answer.
            answer = ""
            for block in reversed(messages):
                if isinstance(block, dict) and block.get("role") == "assistant":
                    content = block.get("content", "")
                    if isinstance(content, str):
                        answer = content
                    elif isinstance(content, list):
                        texts = [
                            b["text"]
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        answer = "\n".join(texts)
                    break

            result = AgentResult(
                answer=answer,
                input_tokens=total_input,
                output_tokens=total_output,
                total_latency_ms=total_latency_ms,
                tool_calls=total_tool_calls,
                turns=turns,
                context_overflow=context_overflow,
            )
        except Exception as exc:
            logger.warning("Agent error on task %s: %s", task["task_id"], exc)
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
            agent.get_tools = original_get_tools  # type: ignore[assignment]
            agent.run_turn = original_run_turn  # type: ignore[assignment]
            if _mcp_started:
                try:
                    agent._mcp_client.__exit__(None, None, None)
                except Exception:
                    pass

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
