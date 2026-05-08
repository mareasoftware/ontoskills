#!/usr/bin/env python3
"""SkillsBench benchmark runner: OntoSkills MCP vs Traditional skill delivery.

Usage:
    python run.py --mode {acp,acp-mcp,baseline,both,all5,taskwise} [options]

Examples:
    # Taskwise: 3 cases per task (baseline -> acp -> acp-mcp)
    python run.py --mode taskwise

    # Single mode
    python run.py --mode acp
    python run.py --mode acp-mcp

    # Dry run (see how many tasks, estimated duration)
    python run.py --mode taskwise --dry-run

    # Skip specific tasks
    python run.py --mode taskwise --skip-tasks paper-anonymizer,jpg-ocr-stat
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.state import BenchmarkState
from benchmark.wrappers.skillsbench import SkillsBenchWrapper
from benchmark.reporting.chart_data import generate_chart_data, save_chart_data

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Runner factories (shared by all modes)
# ---------------------------------------------------------------------------

def _baseline_runner(w: SkillsBenchWrapper, nudge: str):
    async def _run(task: dict) -> dict:
        return await w._run_acp_trial(task, skills_dir=None, skill_nudge=nudge)
    return _run

def _acp_runner(w: SkillsBenchWrapper, nudge: str):
    async def _run(task: dict) -> dict:
        skills_dir = str(Path(task["task_dir"]) / "environment" / "skills")
        return await w._run_acp_trial(task, skills_dir=skills_dir, skill_nudge=nudge)
    return _run

def _mcp_runner(w: SkillsBenchWrapper, nudge: str):
    async def _run(task: dict) -> dict:
        return await w._run_acp_mcp_trial(task, skill_nudge=nudge)
    return _run

_CASE_RUNNERS = {
    "baseline": _baseline_runner,
    "acp": _acp_runner,
    "acp-mcp": _mcp_runner,
}

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _prepare_states(
    output_dir: Path, cases: list[tuple[str, bool]], force_restart: bool,
) -> tuple[list[BenchmarkState], list[str]]:
    """Create or load BenchmarkState for each case."""
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
    return states, labels


def _save_case_results(
    states: list[BenchmarkState], labels: list[str],
    cases: list[tuple[str, bool]], output_dir: Path, model: str,
) -> dict[str, tuple[list[dict], float | None]]:
    """Save results.json, score.json, chart_data.json per case."""
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


def _build_runners(
    wrapper: SkillsBenchWrapper, cases: list[tuple[str, bool]],
) -> list:
    """Build trial runner coroutines for each case using _CASE_RUNNERS dict."""
    runners: list = []
    for mode, hints in cases:
        nudge = "name" if hints else ""
        factory = _CASE_RUNNERS.get(mode)
        if factory is None:
            raise ValueError(f"Unknown mode: {mode}")
        runners.append(factory(wrapper, nudge))
    return runners

# ---------------------------------------------------------------------------
# Unified runner
# ---------------------------------------------------------------------------

def _run_skillsbench(
    output_dir: Path,
    *,
    cases: list[tuple[str, bool]],
    model: str = "glm-5.1",
    max_tasks: int | None = None,
    shuffle: bool = True,
    seed: int = 42,
    skip_first: int = 0,
    max_attempts: int = 5,
    skip_tasks: set[str] | None = None,
    only_tasks: list[str] | None = None,
    workers: int = 2,
    force_restart: bool = False,
    dry_run: bool = False,
) -> dict[str, tuple[list[dict], float | None]] | None:
    """Run SkillsBench with the given cases.
    
    Single case -> uses _run_pooled (per-task state).
    Multiple cases -> uses _run_pooled_task_first (per-case states, taskwise iteration).
    """
    wrapper = SkillsBenchWrapper()

    packages_root = os.path.expanduser("~/.ontoskills/packages")
    tasks = wrapper.load_tasks(
        max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        packages_root=packages_root, skip_first=skip_first,
        only_tasks=only_tasks, skip_tasks=skip_tasks,
    )
    if not tasks:
        logger.error("No tasks to run.")
        return {}

    # Dry run.
    if dry_run:
        _print_dry_run(tasks, cases, workers, max_attempts)
        return None

    states, labels = _prepare_states(output_dir, cases, force_restart)

    if len(cases) == 1:
        # Single case: use _run_pooled.
        state = states[0]
        mode, hints = cases[0]
        all_task_ids = [t["task_id"] for t in tasks]
        if state.is_fully_done(all_task_ids):
            logger.info("All tasks already completed in state file.")
        else:
            runner = _build_runners(wrapper, cases)[0]
            asyncio.run(wrapper._run_pooled(
                tasks, state, runner,
                max_attempts=max_attempts, workers=workers,
            ))
    else:
        # Multiple cases: use _run_pooled_task_first.
        runners = _build_runners(wrapper, cases)
        asyncio.run(wrapper._run_pooled_task_first(
            tasks, states, runners, cases,
            max_attempts=max_attempts, workers=workers,
        ))

    case_results = _save_case_results(states, labels, cases, output_dir, model)

    if len(cases) > 3:
        _generate_all5_summary(case_results, output_dir)

    return case_results

# ---------------------------------------------------------------------------
# Thin wrappers (backward-compatible signatures)
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
    skip_tasks: set[str] | None = None,
    dry_run: bool = False,
) -> tuple[list[dict], float | None]:
    """Single-case runner (backward-compatible)."""
    _ = skillsbench_repo, resume, state_file  # unused (wrapper uses defaults)
    result = _run_skillsbench(
        output_dir,
        cases=[(mode, skill_hints)],
        model=model, max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        skip_first=skip_first, max_attempts=max_attempts,
        skip_tasks=skip_tasks, only_tasks=only_tasks,
        workers=workers, force_restart=force_restart, dry_run=dry_run,
    )
    if result is None:
        return [], None
    for label_key, (results, acc) in result.items():
        return results, acc
    return [], None


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
    skip_tasks: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, tuple[list[dict], float | None]]:
    """3-case taskwise runner (backward-compatible)."""
    _ = skillsbench_repo
    return _run_skillsbench(
        output_dir,
        cases=[("baseline", False), ("acp", True), ("acp-mcp", True)],
        model=model, max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        skip_first=skip_first, max_attempts=max_attempts,
        skip_tasks=skip_tasks, only_tasks=only_tasks,
        workers=workers, force_restart=force_restart, dry_run=dry_run,
    )


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
    skip_tasks: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, tuple[list[dict], float | None]]:
    """5-case all5 runner (backward-compatible)."""
    _ = skillsbench_repo
    return _run_skillsbench(
        output_dir,
        cases=[
            ("baseline", False), ("acp", True), ("acp-mcp", True),
            ("acp", False), ("acp-mcp", False),
        ],
        model=model, max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        skip_first=skip_first, max_attempts=max_attempts,
        skip_tasks=skip_tasks, only_tasks=only_tasks,
        workers=workers, force_restart=force_restart, dry_run=dry_run,
    )

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


def _print_dry_run(tasks: list[dict], cases: list[tuple[str, bool]], workers: int, attempts: int) -> None:
    """Print a summary of what would run, then exit."""
    case_labels = [f"{m}+{'hints' if h else 'nohints'}" for m, h in cases]
    total_runs = len(tasks) * len(cases) * attempts
    avg_task_s = 300  # rough estimate: 5 min per attempt
    est_hours = total_runs * avg_task_s / 3600 / workers

    print(f"SkillsBench Dry Run")
    print(f"{'='*50}")
    print(f"  Tasks:       {len(tasks)}")
    print(f"  Cases:       {len(cases)} ({', '.join(case_labels)})")
    print(f"  Attempts:    {attempts} per task/case")
    print(f"  Workers:     {workers}")
    print(f"  Total runs:  {total_runs}")
    print(f"  Est. time:   {est_hours:.1f}h (at ~5min/attempt)")
    print(f"{'='*50}")
    print(f"\nTasks ({len(tasks)}):")
    for t in tasks:
        print(f"  - {t['task_id']}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OntoSkills SkillsBench Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --mode taskwise\n"
            "  python run.py --mode taskwise --dry-run\n"
            "  python run.py --mode acp\n"
            "  python run.py --mode acp-mcp --skip-tasks paper-anonymizer\n"
        ),
    )

    parser.add_argument(
        "--mode",
        choices=["acp", "acp-mcp", "baseline", "both", "all5", "taskwise"],
        default="both",
        help=(
            "'acp' = Traditional, 'acp-mcp' = MCP, "
            "'baseline' = no skills, 'both' = acp + acp-mcp, "
            "'all5' = all 5 cases, 'taskwise' = 3 cases per task"
        ),
    )
    parser.add_argument("--model", default="glm-5.1")
    parser.add_argument(
        "--max-tasks", type=int, default=None,
        help="Max tasks (default: all available)",
    )
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--shuffle", action="store_true", default=True)
    parser.add_argument("--no-shuffle", action="store_false", dest="shuffle")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-first", type=int, default=0)
    parser.add_argument(
        "--output-dir", default=str(BENCHMARK_DIR / "results"),
    )
    parser.add_argument(
        "--skillsbench-repo", default=os.path.expanduser("~/.ontoskills/skillsbench"),
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--force-restart", action="store_true")
    parser.add_argument("--state-file", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--no-skill-hints", action="store_true")
    parser.add_argument("--only-tasks", default=None)
    parser.add_argument(
        "--skip-tasks", default=None,
        help="Comma-separated task IDs to skip",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print task summary and estimated duration, then exit",
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
        if args.dry_run:
            # Dry-run doesn't call the API, so skip auth check.
            pass
        else:
            parser.error("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required.")

    traditional_results: dict[str, list[dict]] = {}
    ontoskills_results: dict[str, list[dict]] = {}
    traditional_accuracies: dict[str, float | None] = {}
    ontoskills_accuracies: dict[str, float | None] = {}

    logger.info("=" * 60)
    logger.info("SkillsBench — mode=%s, model=%s", args.mode, args.model)
    logger.info("=" * 60)

    common = dict(
        model=args.model, max_tasks=args.max_tasks,
        shuffle=args.shuffle, seed=args.seed,
        skip_first=args.skip_first, max_attempts=args.attempts,
        only_tasks=args.only_tasks.split(",") if args.only_tasks else None,
        skip_tasks=set(args.skip_tasks.split(",")) if args.skip_tasks else None,
        workers=args.workers, force_restart=args.force_restart,
        dry_run=args.dry_run,
    )

    if args.mode == "all5":
        t0 = time.perf_counter()
        case_results = _run_skillsbench_task_first(output_dir, **common)
        elapsed = time.perf_counter() - t0
        if case_results:
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
        case_results = _run_skillsbench_taskwise(output_dir, **common)
        elapsed = time.perf_counter() - t0
        if case_results:
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
        cases_map = {
            "baseline": [("baseline", False)],
            "both": [("acp", True), ("acp-mcp", True)],
            "acp": [("acp", not args.no_skill_hints)],
            "acp-mcp": [("acp-mcp", not args.no_skill_hints)],
        }
        cases = cases_map[args.mode]

        for run_mode, hints in cases:
            label = f"{run_mode}+{'hints' if hints else 'nohints'}"
            logger.info("Running SkillsBench %s (model=%s)...", label, args.model)
            t0 = time.perf_counter()
            results, accuracy = _run_skillsbench_acp(
                output_dir, mode=run_mode, label=label, skill_hints=hints,
                **common,
            )
            elapsed = time.perf_counter() - t0
            logger.info("SkillsBench %s completed in %.1fs", label, elapsed)
            if run_mode == "acp-mcp":
                ontoskills_results[f"skillsbench/{label}"] = results
                ontoskills_accuracies[f"skillsbench/{label}"] = accuracy
            else:
                traditional_results[f"skillsbench/{label}"] = results
                traditional_accuracies[f"skillsbench/{label}"] = accuracy

    if args.mode == "both" and traditional_results and ontoskills_results:
        _generate_comparison(
            traditional_results, ontoskills_results,
            traditional_accuracies, ontoskills_accuracies,
            output_dir,
        )

    logger.info("All done. Results in %s", output_dir)


if __name__ == "__main__":
    main()
