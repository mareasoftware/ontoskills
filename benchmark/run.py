#!/usr/bin/env python3
"""SkillsBench benchmark runner: OntoSkills MCP vs Traditional skill delivery.

Usage:
    python run.py --mode {acp,acp-mcp,baseline,both,all5,taskwise} --max-tasks <N>

Examples:
    # Run all 5 cases (baseline, acp+hints, acp-mcp+hints, acp+nohints, acp-mcp+nohints)
    python run.py --mode all5 --max-tasks 15

    # Run single mode
    python run.py --mode acp --max-tasks 25
    python run.py --mode acp-mcp --max-tasks 25

    # Resume from previous state
    python run.py --mode acp --resume

    # Force fresh start
    python run.py --mode acp --force-restart
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.config import ONTOMCP_BIN_PATH, TTL_ROOT
from benchmark.reporting.chart_data import generate_chart_data, save_chart_data

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# SkillsBench runners
# ---------------------------------------------------------------------------

def _run_skillsbench_acp(
    output_dir: Path,
    *,
    mode: str = "acp",
    label: str | None = None,
    model: str = "glm-5.1",
    max_tasks: int | None = None,
    shuffle: bool = True,
    seed: int = 42,
    skip_first: int = 0,
    max_attempts: int = 5,
    skill_hints: bool = True,
    skillsbench_repo: str = os.path.expanduser("~/.ontoskills/skillsbench"),
    only_tasks: list[str] | None = None,
    workers: int = 2,
    resume: bool = True,
    force_restart: bool = False,
    state_file: str | None = None,
) -> tuple[list[dict], float | None]:
    """Run SkillsBench via ACP with BenchmarkState resume and worker pool."""
    import asyncio
    import uuid

    from benchmark.state import BenchmarkState
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)

    packages_root = os.path.expanduser("~/.ontoskills/packages")
    tasks = wrapper.load_tasks(
        max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        packages_root=packages_root, skip_first=skip_first,
        only_tasks=only_tasks,
    )
    if not tasks:
        logger.error("No tasks to run.")
        return [], None

    effective_label = label or mode
    if state_file:
        state_path = Path(state_file)
    else:
        state_path = output_dir / "skillsbench" / effective_label / "benchmark_state.json"

    run_id = str(uuid.uuid4())[:8]
    if force_restart:
        state = BenchmarkState.create(state_path, run_id, mode, skill_hints)
    elif resume:
        state = BenchmarkState.load_or_create(state_path, run_id, mode, skill_hints)
    else:
        state = BenchmarkState.create(state_path, run_id, mode, skill_hints)

    all_task_ids = [t["task_id"] for t in tasks]
    if state.is_fully_done(all_task_ids):
        logger.info("All tasks already completed in state file.")
        results = state.get_results()
    else:
        nudge = "name" if skill_hints else ""

        if mode == "baseline":
            async def trial_runner(task: dict) -> dict:
                return await wrapper._run_acp_trial(task, skills_dir=None, skill_nudge="")
        elif mode == "acp":
            async def trial_runner(task: dict) -> dict:
                skills_dir = str(Path(task["task_dir"]) / "environment" / "skills")
                return await wrapper._run_acp_trial(task, skills_dir=skills_dir, skill_nudge=nudge)
        elif mode == "acp-mcp":
            async def trial_runner(task: dict) -> dict:
                return await wrapper._run_acp_mcp_trial(task, skill_nudge=nudge)
        else:
            raise ValueError(f"Unknown SkillsBench ACP mode: {mode}")

        results = asyncio.run(
            wrapper._run_pooled(
                tasks, state, trial_runner,
                max_attempts=max_attempts, workers=workers,
            )
        )

    score = SkillsBenchWrapper.score(results)
    logger.info(
        "SkillsBench %s: %d/%d passed (%.1f%%)",
        mode, score["tasks_passed"], score["total_tasks"], score["pass_rate"] * 100,
    )

    raw_path = output_dir / "skillsbench" / effective_label / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    score_path = output_dir / "skillsbench" / effective_label / "score.json"
    score_path.write_text(
        json.dumps(score, indent=2, default=str, ensure_ascii=False), encoding="utf-8",
    )

    chart = generate_chart_data("skillsbench", mode, results, score, model=model)
    save_chart_data(chart, str(output_dir / "skillsbench" / effective_label / "chart_data.json"))

    return results, score["pass_rate"]


def _run_skillsbench_task_first(
    output_dir: Path,
    *,
    model: str = "glm-5.1",
    max_tasks: int | None = None,
    shuffle: bool = True,
    seed: int = 42,
    skip_first: int = 0,
    max_attempts: int = 5,
    skillsbench_repo: str = os.path.expanduser("~/.ontoskills/skillsbench"),
    only_tasks: list[str] | None = None,
    workers: int = 2,
    force_restart: bool = False,
) -> dict[str, tuple[list[dict], float | None]]:
    """Run all5 benchmark with task-first iteration and Docker pruning."""
    import asyncio
    import uuid

    from benchmark.state import BenchmarkState
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)

    packages_root = os.path.expanduser("~/.ontoskills/packages")
    tasks = wrapper.load_tasks(
        max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        packages_root=packages_root, skip_first=skip_first,
        only_tasks=only_tasks,
    )
    if not tasks:
        logger.error("No tasks to run.")
        return {}

    cases: list[tuple[str, bool]] = [
        ("baseline", False),
        ("acp", True),
        ("acp-mcp", True),
        ("acp", False),
        ("acp-mcp", False),
    ]

    run_id = str(uuid.uuid4())[:8]
    states: list[BenchmarkState] = []
    labels: list[str] = []
    for mode, hints in cases:
        label = f"{mode}+{'hints' if hints else 'nohints'}"
        labels.append(label)
        state_path = output_dir / "skillsbench" / label / "benchmark_state.json"
        if force_restart:
            state = BenchmarkState.create(state_path, run_id, mode, hints)
        else:
            state = BenchmarkState.load_or_create(state_path, run_id, mode, hints)
        states.append(state)

    def _make_baseline_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            return await w._run_acp_trial(task, skills_dir=None, skill_nudge=nudge)
        return _runner

    def _make_acp_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            skills_dir = str(Path(task["task_dir"]) / "environment" / "skills")
            return await w._run_acp_trial(task, skills_dir=skills_dir, skill_nudge=nudge)
        return _runner

    def _make_mcp_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            return await w._run_acp_mcp_trial(task, skill_nudge=nudge)
        return _runner

    trial_runners: list = []
    for mode, hints in cases:
        nudge = "name" if hints else ""
        if mode == "baseline":
            trial_runners.append(_make_baseline_runner(wrapper, nudge))
        elif mode == "acp":
            trial_runners.append(_make_acp_runner(wrapper, nudge))
        elif mode == "acp-mcp":
            trial_runners.append(_make_mcp_runner(wrapper, nudge))
        else:
            raise ValueError(f"Unknown mode: {mode}")

    logger.info("Starting task-first all5: %d tasks, %d cases, %d workers", len(tasks), len(cases), workers)
    asyncio.run(
        wrapper._run_pooled_task_first(
            tasks, states, trial_runners, cases,
            max_attempts=max_attempts, workers=workers,
        )
    )

    case_results: dict[str, tuple[list[dict], float | None]] = {}
    for i, label in enumerate(labels):
        results = states[i].get_results()
        score = SkillsBenchWrapper.score(results)
        pass_rate = score["pass_rate"]

        case_dir = output_dir / "skillsbench" / label
        case_dir.mkdir(parents=True, exist_ok=True)
        _save_json(results, case_dir / "results.json")
        (case_dir / "score.json").write_text(
            json.dumps(score, indent=2, default=str, ensure_ascii=False), encoding="utf-8",
        )

        chart = generate_chart_data("skillsbench", cases[i][0], results, score, model=model)
        save_chart_data(chart, str(case_dir / "chart_data.json"))

        logger.info(
            "SkillsBench %s: %d/%d passed (%.1f%%)",
            label, score["tasks_passed"], score["total_tasks"], pass_rate * 100,
        )
        case_results[label] = (results, pass_rate)

    _generate_all5_summary(case_results, output_dir)

    return case_results


def _run_skillsbench_taskwise(
    output_dir: Path,
    *,
    model: str = "glm-5.1",
    max_tasks: int | None = None,
    shuffle: bool = True,
    seed: int = 42,
    skip_first: int = 0,
    max_attempts: int = 5,
    skillsbench_repo: str = os.path.expanduser("~/.ontoskills/skillsbench"),
    only_tasks: list[str] | None = None,
    workers: int = 2,
    force_restart: bool = False,
) -> dict[str, tuple[list[dict], float | None]]:
    """Task-first iteration with 3 cases (no nohints variants).

    For each task runs all 3 cases before moving to the next:
    baseline → acp+hints → acp-mcp+hints.
    """
    import asyncio
    import uuid

    from benchmark.state import BenchmarkState
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)

    packages_root = os.path.expanduser("~/.ontoskills/packages")
    tasks = wrapper.load_tasks(
        max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        packages_root=packages_root, skip_first=skip_first,
        only_tasks=only_tasks,
    )
    if not tasks:
        logger.error("No tasks to run.")
        return {}

    cases: list[tuple[str, bool]] = [
        ("baseline", False),
        ("acp", True),
        ("acp-mcp", True),
    ]

    run_id = str(uuid.uuid4())[:8]
    states: list[BenchmarkState] = []
    labels: list[str] = []
    for mode, hints in cases:
        label = f"{mode}+{'hints' if hints else 'nohints'}"
        labels.append(label)
        state_path = output_dir / "skillsbench" / label / "benchmark_state.json"
        if force_restart:
            state = BenchmarkState.create(state_path, run_id, mode, hints)
        else:
            state = BenchmarkState.load_or_create(state_path, run_id, mode, hints)
        states.append(state)

    def _make_baseline_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            return await w._run_acp_trial(task, skills_dir=None, skill_nudge=nudge)
        return _runner

    def _make_acp_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            skills_dir = str(Path(task["task_dir"]) / "environment" / "skills")
            return await w._run_acp_trial(task, skills_dir=skills_dir, skill_nudge=nudge)
        return _runner

    def _make_mcp_runner(w, nudge: str):
        async def _runner(task: dict) -> dict:
            return await w._run_acp_mcp_trial(task, skill_nudge=nudge)
        return _runner

    trial_runners: list = []
    for mode, hints in cases:
        nudge = "name" if hints else ""
        if mode == "baseline":
            trial_runners.append(_make_baseline_runner(wrapper, nudge))
        elif mode == "acp":
            trial_runners.append(_make_acp_runner(wrapper, nudge))
        elif mode == "acp-mcp":
            trial_runners.append(_make_mcp_runner(wrapper, nudge))
        else:
            raise ValueError(f"Unknown mode: {mode}")

    logger.info("Starting taskwise: %d tasks, %d cases, %d workers", len(tasks), len(cases), workers)
    asyncio.run(
        wrapper._run_pooled_task_first(
            tasks, states, trial_runners, cases,
            max_attempts=max_attempts, workers=workers,
        )
    )

    case_results: dict[str, tuple[list[dict], float | None]] = {}
    for i, label in enumerate(labels):
        results = states[i].get_results()
        score = SkillsBenchWrapper.score(results)
        pass_rate = score["pass_rate"]

        case_dir = output_dir / "skillsbench" / label
        case_dir.mkdir(parents=True, exist_ok=True)
        _save_json(results, case_dir / "results.json")
        (case_dir / "score.json").write_text(
            json.dumps(score, indent=2, default=str, ensure_ascii=False), encoding="utf-8",
        )

        chart = generate_chart_data("skillsbench", cases[i][0], results, score, model=model)
        save_chart_data(chart, str(case_dir / "chart_data.json"))

        logger.info(
            "SkillsBench %s: %d/%d passed (%.1f%%)",
            label, score["tasks_passed"], score["total_tasks"], pass_rate * 100,
        )
        case_results[label] = (results, pass_rate)

    return case_results


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _generate_all5_summary(
    case_results: dict[str, tuple[list[dict], float | None]],
    output_dir: Path,
) -> None:
    lines = ["# SkillsBench All5 Benchmark Summary\n"]
    lines.append("| Case | Pass Rate | Avg Reward | Tasks Passed | Total |")
    lines.append("|------|-----------|------------|--------------|-------|")

    for key in sorted(case_results.keys()):
        results, acc = case_results[key]
        total = len(results)
        passed = sum(1 for r in results if r.get("best_reward", r.get("reward", 0)) >= 1.0)
        avg_reward = sum(r.get("best_reward", r.get("reward", 0.0)) for r in results) / total if total else 0
        rate = f"{acc * 100:.1f}%" if acc is not None else f"{passed}/{total}"
        lines.append(f"| {key} | {rate} | {avg_reward:.3f} | {passed} | {total} |")

    report = "\n".join(lines) + "\n"
    report_path = output_dir / "skillsbench" / "all5_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logger.info("All5 summary saved to %s", report_path)


def _generate_comparison(
    traditional_results: dict[str, list[dict]],
    ontoskills_results: dict[str, list[dict]],
    traditional_accuracies: dict[str, float | None],
    ontoskills_accuracies: dict[str, float | None],
    output_dir: Path,
) -> None:
    from benchmark.reporting.metrics import compute_comparison
    from benchmark.reporting.comparison import generate_comparison_report, save_report

    report = compute_comparison(
        traditional_results, ontoskills_results,
        traditional_accuracies=traditional_accuracies,
        ontoskills_accuracies=ontoskills_accuracies,
    )
    md = generate_comparison_report(report)
    report_path = output_dir / "comparison.md"
    save_report(md, str(report_path))
    logger.info("Comparison report saved to %s", report_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_json(data, path: Path) -> None:
    def _default(obj):
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)
    path.write_text(json.dumps(data, indent=2, default=_default, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OntoSkills SkillsBench Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --mode all5 --max-tasks 15\n"
            "  python run.py --mode acp --max-tasks 25\n"
            "  python run.py --mode acp-mcp --max-tasks 25\n"
        ),
    )

    parser.add_argument(
        "--mode",
        choices=["acp", "acp-mcp", "baseline", "both", "all5", "taskwise"],
        default="both",
        help=(
            "Agent mode. 'acp' = Traditional, 'acp-mcp' = MCP, "
            "'baseline' = no skills, 'both' = acp + acp-mcp, "
            "'all5' = all 5 cases with task-first iteration."
        ),
    )
    parser.add_argument(
        "--model",
        default="glm-5.1",
        help="Model ID (default: glm-5.1 via API proxy)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=25,
        help="Max tasks per benchmark (default: 25)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=5,
        help="Clean retries per task (default: 5)",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        default=True,
        help="Shuffle tasks (default: True)",
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_false",
        dest="shuffle",
        help="Disable shuffling",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--skip-first",
        type=int,
        default=0,
        help="Skip first N tasks",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BENCHMARK_DIR / "results"),
        help="Output directory (default: benchmark/results/)",
    )
    parser.add_argument(
        "--skillsbench-repo",
        default=os.path.expanduser("~/.ontoskills/skillsbench"),
        help="Path to SkillsBench repo clone",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Parallel Docker workers (default: 2)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from previous state (default: True)",
    )
    parser.add_argument(
        "--force-restart",
        action="store_true",
        help="Ignore existing state, start fresh",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Custom state file path",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--no-skill-hints",
        action="store_true",
        help="Omit skill names from prompts",
    )
    parser.add_argument(
        "--only-tasks",
        default=None,
        help="Comma-separated task IDs to run",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        parser.error("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required.")

    traditional_results: dict[str, list[dict]] = {}
    ontoskills_results: dict[str, list[dict]] = {}
    traditional_accuracies: dict[str, float | None] = {}
    ontoskills_accuracies: dict[str, float | None] = {}

    logger.info("=" * 60)
    logger.info("SkillsBench — mode=%s, model=%s", args.mode, args.model)
    logger.info("=" * 60)

    if args.mode == "all5":
        t0 = time.perf_counter()
        case_results = _run_skillsbench_task_first(
            output_dir,
            model=args.model,
            max_tasks=args.max_tasks,
            shuffle=args.shuffle,
            seed=args.seed,
            skip_first=args.skip_first,
            max_attempts=args.attempts,
            skillsbench_repo=args.skillsbench_repo,
            only_tasks=args.only_tasks.split(",") if args.only_tasks else None,
            workers=args.workers,
            force_restart=args.force_restart,
        )
        elapsed = time.perf_counter() - t0
        logger.info("SkillsBench all5 completed in %.1fs", elapsed)

        for label, (results, accuracy) in case_results.items():
            mode = label.split("+")[0]
            key = f"skillsbench/{label}"
            if mode == "acp-mcp":
                ontoskills_results[key] = results
                ontoskills_accuracies[key] = accuracy
            else:
                traditional_results[key] = results
                traditional_accuracies[key] = accuracy

    elif args.mode == "taskwise":
        t0 = time.perf_counter()
        case_results = _run_skillsbench_taskwise(
            output_dir,
            model=args.model,
            max_tasks=args.max_tasks,
            shuffle=args.shuffle,
            seed=args.seed,
            skip_first=args.skip_first,
            max_attempts=args.attempts,
            skillsbench_repo=args.skillsbench_repo,
            only_tasks=args.only_tasks.split(",") if args.only_tasks else None,
            workers=args.workers,
            force_restart=args.force_restart,
        )
        elapsed = time.perf_counter() - t0
        logger.info("SkillsBench taskwise completed in %.1fs", elapsed)

        for label, (results, accuracy) in case_results.items():
            mode = label.split("+")[0]
            key = f"skillsbench/{label}"
            if mode == "acp-mcp":
                ontoskills_results[key] = results
                ontoskills_accuracies[key] = accuracy
            else:
                traditional_results[key] = results
                traditional_accuracies[key] = accuracy

    else:
        cases: list[tuple[str, bool]] = []
        if args.mode == "baseline":
            cases = [("baseline", False)]
        elif args.mode == "both":
            cases = [("acp", True), ("acp-mcp", True)]
        elif args.mode == "acp":
            cases = [("acp", not args.no_skill_hints)]
        elif args.mode == "acp-mcp":
            cases = [("acp-mcp", not args.no_skill_hints)]

        for run_mode, hints in cases:
            label = f"{run_mode}+{'hints' if hints else 'nohints'}"
            logger.info("Running SkillsBench %s (model=%s)...", label, args.model)
            t0 = time.perf_counter()
            results, accuracy = _run_skillsbench_acp(
                output_dir,
                mode=run_mode,
                label=label,
                model=args.model,
                max_tasks=args.max_tasks,
                shuffle=args.shuffle,
                seed=args.seed,
                skip_first=args.skip_first,
                max_attempts=args.attempts,
                skill_hints=hints,
                skillsbench_repo=args.skillsbench_repo,
                only_tasks=args.only_tasks.split(",") if args.only_tasks else None,
                workers=args.workers,
                resume=args.resume and not args.force_restart,
                force_restart=args.force_restart,
                state_file=args.state_file,
            )
            elapsed = time.perf_counter() - t0
            logger.info("SkillsBench %s completed in %.1fs", label, elapsed)
            if run_mode == "acp-mcp":
                ontoskills_results[f"skillsbench/{label}"] = results
                ontoskills_accuracies[f"skillsbench/{label}"] = accuracy
            else:
                traditional_results[f"skillsbench/{label}"] = results
                traditional_accuracies[f"skillsbench/{label}"] = accuracy

    # Generate comparison report if both modes ran.
    if args.mode == "both" and traditional_results and ontoskills_results:
        _generate_comparison(
            traditional_results, ontoskills_results,
            traditional_accuracies, ontoskills_accuracies,
            output_dir,
        )

    logger.info("All done. Results in %s", output_dir)


if __name__ == "__main__":
    main()
