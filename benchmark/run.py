#!/usr/bin/env python3
"""Main orchestrator: run benchmarks and generate comparison report.

Usage:
    python run.py --benchmark {gaia,swebench,perpackage,skillsbench,all}
                  --mode {acp,acp-mcp,both} --model <model_id> --max-tasks <N>
                  --output-dir <path>

Examples:
    # Run SkillsBench with ACP (traditional via container)
    python run.py --benchmark skillsbench --mode acp --max-tasks 25

    # Run SkillsBench with ACP-MCP (ontomcp inside container)
    python run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25

    # Run SkillsBench both modes
    python run.py --benchmark skillsbench --mode both --max-tasks 25

    # Run GAIA with both agents (acp maps to traditional, acp-mcp to ontoskills)
    python run.py --benchmark gaia --mode both --max-tasks 10

    # Resume from previous state
    python run.py --benchmark skillsbench --mode acp --resume

    # Force fresh start (ignore existing state)
    python run.py --benchmark skillsbench --mode acp --force-restart
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so that ``benchmark.config`` etc.
# resolve correctly regardless of cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmark.config import (
    ANTHROPIC_MODELS,
    BENCHMARK_CONFIG,
    ONTOMCP_BIN_PATH,
    TTL_ROOT,
)
from benchmark.reporting.chart_data import generate_chart_data, save_chart_data

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------

def _make_traditional_agent(
    model: str,
    skills_dir: str,
) -> "TraditionalAgent":
    """Create a TraditionalAgent."""
    from benchmark.agents.traditional import TraditionalAgent

    return TraditionalAgent(model=model, skills_dir=skills_dir)


def _make_ontoskills_agent(
    model: str,
    ttl_dir: str,
    ontomcp_bin: str,
) -> "OntoSkillsAgent":
    """Create an OntoSkillsAgent."""
    from benchmark.agents.ontoskills import OntoSkillsAgent

    return OntoSkillsAgent(
        model=model,
        ontology_root=ttl_dir,
        ontomcp_bin=ontomcp_bin,
    )


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------

def _run_gaia(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    gaia_level: str | None = None,
    shuffle: bool = True,
    seed: int = 42,
) -> tuple[list[dict], float | None]:
    """Run the GAIA benchmark for one agent.

    Returns (results_list, accuracy_or_None).
    """
    from benchmark.wrappers.gaia import GAIAWrapper

    wrapper = GAIAWrapper(data_dir=str(BENCHMARK_DIR / "data" / "gaia"))

    level = gaia_level or BENCHMARK_CONFIG["gaia"]["levels"][0]

    results = wrapper.run_benchmark(
        agent,
        level=level,
        max_tasks=max_tasks,
        shuffle=shuffle,
        seed=seed,
    )

    # Score — try test split first, fall back to validation split.
    # Test split gold answers are "?" (withheld); validation has real answers.
    gold: dict[str, str] = {}

    for split in ("test", "validation"):
        try:
            scoring_tasks = wrapper.load_dataset(level=level, split=split)
        except Exception:
            continue
        # Build lookup once.
        task_gold = {
            t["task_id"]: t["gold_answer"]
            for t in scoring_tasks
            if t.get("gold_answer")
        }
        for r in results:
            tid = r.get("task_id", "")
            if tid in task_gold:
                gold[tid] = task_gold[tid]
        if gold:
            logger.info("GAIA scoring using %s split (%d gold answers)", split, len(gold))
            break

    accuracy = None
    if gold:
        score = GAIAWrapper.score(results, gold)
        accuracy = score["accuracy"]
        logger.info("GAIA accuracy (%s): %.2f%% (%d/%d)", mode, accuracy * 100, score["correct"], score["total"])

    # Save raw results.
    raw_path = output_dir / "gaia" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save submission file.
    sub_path = output_dir / "gaia" / mode / "submission.jsonl"
    wrapper.write_submission(results, str(sub_path))

    return results, accuracy


def _run_swebench(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    shuffle: bool = True,
    seed: int = 42,
) -> tuple[list[dict], float | None]:
    """Run the SWE-bench benchmark for one agent.

    Returns (results_list, accuracy_or_None).
    Accuracy is None because SWE-bench evaluation is external.
    """
    from benchmark.wrappers.swebench import SWEBenchWrapper

    wrapper = SWEBenchWrapper(data_dir=str(BENCHMARK_DIR / "data" / "swebench"))

    results = wrapper.run_benchmark(
        agent,
        dataset_name=BENCHMARK_CONFIG["swebench"]["dataset"],
        max_tasks=max_tasks,
        repo_base_dir=str(BENCHMARK_DIR / "data" / "repos"),
        shuffle=shuffle,
        seed=seed,
    )

    # Save predictions.
    raw_path = output_dir / "swebench" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    pred_path = output_dir / "swebench" / mode / "predictions.json"
    SWEBenchWrapper.write_predictions(results, str(pred_path))

    # Compute patch_applies rate as accuracy metric.
    patch_rate = (
        sum(1 for r in results if r.get("patch_applies")) / len(results)
        if results else None
    )
    resolved_rate = (
        sum(1 for r in results if r.get("resolved")) / len(results)
        if results else None
    )
    logger.info(
        "SWE-bench (%s): %d instances, patch_rate=%.1f%%, resolved=%.1f%%",
        mode, len(results),
        (patch_rate or 0) * 100, (resolved_rate or 0) * 100,
    )
    return results, patch_rate


def _run_tau2bench(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    shuffle: bool = True,
    seed: int = 42,
) -> tuple[list[dict], float | None]:
    """Run the Tau2-Bench benchmark for one agent.

    Returns (results_list, accuracy_or_None).
    """
    from benchmark.wrappers.tau2bench import Tau2BenchWrapper

    wrapper = Tau2BenchWrapper(data_dir=str(BENCHMARK_DIR / "data" / "tau2bench"))

    # Run across all configured environments.
    all_results: list[dict] = []
    total_correct = 0
    total_scored = 0

    for domain in BENCHMARK_CONFIG["tau2bench"]["environments"]:
        results = wrapper.run_benchmark(
            agent,
            domain=domain,
            max_tasks=max_tasks,
            shuffle=shuffle,
            seed=seed,
        )
        all_results.extend(results)

        # Score per domain.
        expected: dict[str, list[str]] = {}
        expected_actions: dict[str, list[dict]] = {}
        try:
            tasks_for_scoring = wrapper.load_dataset(domain=domain)
            for t in tasks_for_scoring:
                if t.get("expected_outputs"):
                    expected[t["task_id"]] = t["expected_outputs"]
                # Extract expected actions from raw evaluation_criteria.
                crit = t.get("metadata", {}).get("evaluation_criteria")
                if crit:
                    actions = Tau2BenchWrapper._flatten_expected_actions(crit)
                    if actions:
                        expected_actions[t["task_id"]] = actions
        except ImportError:
            pass

        if expected or expected_actions:
            score = Tau2BenchWrapper.score(
                results, expected,
                expected_actions_by_task=expected_actions,
            )
            total_correct += score["correct"]
            total_scored += score["total"]
            logger.info(
                "Tau2 %s (%s): %.2f%% (%d/%d)",
                domain, mode, score["accuracy"] * 100, score["correct"], score["total"],
            )

    accuracy = total_correct / total_scored if total_scored > 0 else None
    if accuracy is not None:
        logger.info(
            "Tau2 overall (%s): %.2f%% (%d/%d)",
            mode, accuracy * 100, total_correct, total_scored,
        )

    # Save results.
    raw_path = output_dir / "tau2bench" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(all_results, raw_path)

    Tau2BenchWrapper.write_results(all_results, str(raw_path).replace("results.json", "results_flat.json"))

    return all_results, accuracy


def _run_perpackage(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    package: str = "superpowers",
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    shuffle: bool = True,
    seed: int = 42,
) -> tuple[list[dict], float | None]:
    """Run the per-package benchmark for one agent.

    Returns (results_list, overall_avg_score_or_None).
    """
    from benchmark.wrappers.perpackage import PerPackageWrapper

    wrapper = PerPackageWrapper(
        skills_dir=skills_dir or str(BENCHMARK_DIR / "skills"),
    )
    tasks = wrapper.load_tasks(package=package)
    results = wrapper.run_benchmark(
        agent, package=package, max_tasks=max_tasks,
        shuffle=shuffle, seed=seed,
    )

    # Load skill content for judge context.
    skills_content: dict[str, str] = {}
    skills_root = Path(skills_dir or str(BENCHMARK_DIR / "skills"))
    for task in tasks:
        for sid in task.get("skill_ids", []):
            key = f"obra/superpowers/{sid}"
            if key not in skills_content:
                md = skills_root / "obra" / "superpowers" / sid / "SKILL.md"
                if md.exists():
                    skills_content[key] = md.read_text(encoding="utf-8")

    # Score with LLM-as-judge.
    judge_score = PerPackageWrapper.score_with_judge(
        results, tasks, model=model, skills_content=skills_content,
    )
    logger.info(
        "Per-package %s (%s): avg=%.1f/5 correct=%.1f complete=%.1f practical=%.1f interaction=%.1f",
        package, mode,
        judge_score["overall_avg"],
        judge_score["avg_by_dimension"]["correctness"],
        judge_score["avg_by_dimension"]["completeness"],
        judge_score["avg_by_dimension"]["practicality"],
        judge_score["avg_by_dimension"]["interaction_quality"],
    )

    # Also compute keyword score for comparison.
    kw_score = PerPackageWrapper.score(results, tasks)

    # Save results.
    raw_path = output_dir / "perpackage" / package / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save scores.
    score_path = output_dir / "perpackage" / package / mode / "score.json"
    combined = {"judge": judge_score, "keyword": kw_score}
    score_path.write_text(
        json.dumps(combined, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    return results, judge_score["overall_avg"]


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
    skillsbench_repo: str = "/tmp/skillsbench_full",
    only_tasks: list[str] | None = None,
    workers: int = 2,
    resume: bool = True,
    force_restart: bool = False,
    state_file: str | None = None,
) -> tuple[list[dict], float | None]:
    """Run SkillsBench via ACP with BenchmarkState resume and worker pool.

    Supports two trial modes:
      - ``acp``     : Traditional via ACP (SKILL.md files injected into Dockerfile)
      - ``acp-mcp`` : MCP via ACP (ontomcp inside container)

    Returns (results_list, pass_rate).
    """
    import asyncio
    import uuid

    from benchmark.state import BenchmarkState
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)

    # Load tasks.
    packages_root = os.path.expanduser("~/.ontoskills/packages")
    tasks = wrapper.load_tasks(
        max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        packages_root=packages_root, skip_first=skip_first,
        only_tasks=only_tasks,
    )
    if not tasks:
        logger.error("No tasks to run.")
        return [], None

    # Resolve state file path.
    effective_label = label or mode
    if state_file:
        state_path = Path(state_file)
    else:
        state_path = output_dir / "skillsbench" / effective_label / "benchmark_state.json"

    # Load or create state.
    run_id = str(uuid.uuid4())[:8]
    if force_restart:
        state = BenchmarkState.create(state_path, run_id, mode, skill_hints)
    elif resume:
        state = BenchmarkState.load_or_create(state_path, run_id, mode, skill_hints)
    else:
        state = BenchmarkState.create(state_path, run_id, mode, skill_hints)

    # Skip if already fully done.
    all_task_ids = [t["task_id"] for t in tasks]
    if state.is_fully_done(all_task_ids):
        logger.info("All tasks already completed in state file.")
        results = state.get_results()
    else:
        # Pick trial runner based on mode.
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

        # Run pooled with state-backed resume.
        results = asyncio.run(
            wrapper._run_pooled(
                tasks, state, trial_runner,
                max_attempts=max_attempts, workers=workers,
            )
        )

    # Score from Docker reward.txt (deterministic).
    score = SkillsBenchWrapper.score(results)
    logger.info(
        "SkillsBench %s: %d/%d passed (%.1f%%)",
        mode,
        score["tasks_passed"],
        score["total_tasks"],
        score["pass_rate"] * 100,
    )

    # Save results.
    raw_path = output_dir / "skillsbench" / effective_label / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save scores.
    score_path = output_dir / "skillsbench" / effective_label / "score.json"
    score_path.write_text(
        json.dumps(score, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save chart data.
    chart = generate_chart_data("skillsbench", mode, results, score, model=model)
    save_chart_data(chart, str(output_dir / "skillsbench" / effective_label / "chart_data.json"))

    return results, score["pass_rate"]


# Map benchmark names to runner functions.
_BENCHMARK_RUNNERS = {
    "gaia": _run_gaia,
    "swebench": _run_swebench,
}


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------

def _generate_comparison(
    traditional_results: dict[str, list[dict]],
    ontoskills_results: dict[str, list[dict]],
    traditional_accuracies: dict[str, float | None],
    ontoskills_accuracies: dict[str, float | None],
    output_dir: Path,
) -> None:
    """Generate and save the comparison report."""
    from benchmark.reporting.metrics import compute_comparison
    from benchmark.reporting.comparison import generate_comparison_report, save_report

    report = compute_comparison(
        traditional_results,
        ontoskills_results,
        traditional_accuracies=traditional_accuracies,
        ontoskills_accuracies=ontoskills_accuracies,
    )

    md = generate_comparison_report(report)
    report_path = output_dir / "comparison.md"
    save_report(md, str(report_path))
    logger.info("Comparison report saved to %s", report_path)


# ---------------------------------------------------------------------------
# All5 summary report
# ---------------------------------------------------------------------------

def _generate_all5_summary(
    traditional_results: dict[str, list[dict]],
    ontoskills_results: dict[str, list[dict]],
    traditional_accuracies: dict[str, float | None],
    ontoskills_accuracies: dict[str, float | None],
    output_dir: Path,
) -> None:
    """Generate a summary report for all 5 benchmark cases."""
    all_cases = {**traditional_results, **ontoskills_results}
    all_accs = {**traditional_accuracies, **ontoskills_accuracies}

    lines = ["# SkillsBench All5 Benchmark Summary\n"]
    lines.append("| Case | Pass Rate | Avg Reward | Tasks Passed | Total |")
    lines.append("|------|-----------|------------|--------------|-------|")

    for key in sorted(all_cases.keys()):
        results = all_cases[key]
        acc = all_accs.get(key)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_json(data, path: Path) -> None:
    """Save data as JSON, converting AgentResult objects to dicts."""
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
        description="OntoSkills Benchmark Runner — run benchmarks and generate comparison reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --benchmark skillsbench --mode acp --max-tasks 25\n"
            "  python run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25\n"
            "  python run.py --benchmark gaia --mode both --max-tasks 10\n"
            "  python run.py --benchmark all --mode both\n"
        ),
    )

    parser.add_argument(
        "--benchmark",
        choices=["gaia", "swebench", "perpackage", "skillsbench", "all"],
        default="all",
        help="Which benchmark to run (default: all)",
    )
    parser.add_argument(
        "--package",
        default="superpowers",
        help="Skill package for per-package benchmark (default: superpowers)",
    )
    parser.add_argument(
        "--mode",
        choices=["acp", "acp-mcp", "baseline", "both", "all5"],
        default="both",
        help=(
            "Which agent mode to run (default: both). "
            "'acp' = Traditional via ACP (SKILL.md files injected into container). "
            "'acp-mcp' = MCP via ACP (ontomcp inside container). "
            "'baseline' = No skills, no nudge — raw agent performance. "
            "'both' = Run acp + acp-mcp. "
            "'all5' = Run all 5 benchmark cases (baseline, acp+hints, acp-mcp+hints, acp+nohints, acp-mcp+nohints). "
            "For non-SkillsBench benchmarks: acp maps to traditional, acp-mcp to ontoskills."
        ),
    )
    parser.add_argument(
        "--skills-dir",
        default=str(BENCHMARK_DIR / "skills"),
        help="Directory of SKILL.md files for the traditional agent",
    )
    parser.add_argument(
        "--ttl-dir",
        default=TTL_ROOT,
        help="Directory of .ttl ontology packages for OntoSkills agent",
    )
    parser.add_argument(
        "--ontomcp-bin",
        default=ONTOMCP_BIN_PATH,
        help="Path to the ontomcp binary",
    )
    parser.add_argument(
        "--model",
        default="glm-5.1",
        help="Model ID to use (default: glm-5.1 via API proxy)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=25,
        help="Maximum number of tasks to run per benchmark (default: 25)",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=5,
        help="Attempts per task: clean retries, best reward wins (default: 5, matches SkillsBench)",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        default=True,
        help="Shuffle tasks before selection (default: True)",
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_false",
        dest="shuffle",
        help="Disable task shuffling (deterministic order)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for task shuffling (default: 42)",
    )
    parser.add_argument(
        "--skip-first",
        type=int,
        default=0,
        help="Skip the first N tasks (combine with previous results)",
    )
    parser.add_argument(
        "--gaia-level",
        default=None,
        help="GAIA level (default: first level from config)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BENCHMARK_DIR / "results"),
        help="Directory to write results to (default: benchmark/results/)",
    )
    parser.add_argument(
        "--skillsbench-repo",
        default="/tmp/skillsbench_full",
        help="Path to local clone of benchflow-ai/skillsbench (for Docker eval)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Parallel Docker workers (each needs its own container) (default: 2)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from previous state file (default: True)",
    )
    parser.add_argument(
        "--force-restart",
        action="store_true",
        help="Ignore existing state and start fresh",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Custom state file path (default: {output_dir}/skillsbench/{mode}/benchmark_state.json)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--no-skill-hints",
        action="store_true",
        help="Omit skill names from prompts (agents discover skills on their own)",
    )
    parser.add_argument(
        "--only-tasks",
        default=None,
        help="Comma-separated task IDs to run (skip all others)",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Logging setup.
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which benchmarks to run.
    if args.benchmark == "all":
        benchmarks = ["gaia", "swebench", "perpackage", "skillsbench"]
    else:
        benchmarks = [args.benchmark]

    # Validate prerequisites.
    modes_needing_api = ("acp", "acp-mcp", "baseline", "both", "all5")
    if args.mode in modes_needing_api:
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            parser.error(
                "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required. "
                "Export it before running the benchmark."
            )
        if not Path(args.skills_dir).exists():
            logger.warning(
                "Skills directory not found: %s — traditional agent will have no skills.",
                args.skills_dir,
            )

    if args.mode in ("acp-mcp", "both"):
        if not Path(args.ttl_dir).exists():
            logger.warning(
                "TTL directory not found: %s — OntoSkills agent may not find ontologies.",
                args.ttl_dir,
            )

    # Collect results for comparison.
    traditional_results: dict[str, list[dict]] = {}
    ontoskills_results: dict[str, list[dict]] = {}
    traditional_accuracies: dict[str, float | None] = {}
    ontoskills_accuracies: dict[str, float | None] = {}

    for bench_name in benchmarks:
        logger.info("=" * 60)
        logger.info("Benchmark: %s", bench_name)
        logger.info("=" * 60)

        if bench_name == "skillsbench":
            # SkillsBench: ACP-based evaluation with BenchmarkState + worker pool.
            # Build list of (mode, skill_hints) tuples to run.
            cases: list[tuple[str, bool]] = []
            if args.mode == "all5":
                cases = [
                    ("baseline", False),
                    ("acp", True),
                    ("acp-mcp", True),
                    ("acp", False),
                    ("acp-mcp", False),
                ]
            elif args.mode == "baseline":
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
                    ontoskills_results[f"{bench_name}/{label}"] = results
                    ontoskills_accuracies[f"{bench_name}/{label}"] = accuracy
                else:
                    traditional_results[f"{bench_name}/{label}"] = results
                    traditional_accuracies[f"{bench_name}/{label}"] = accuracy

        elif bench_name == "perpackage":
            # Per-package benchmark: wrapper handles skill scoping per task.
            # Map acp -> traditional, acp-mcp -> ontoskills.
            package = args.package

            if args.mode in ("acp", "both"):
                logger.info(
                    "Creating traditional agent (model=%s, per-task skill scoping)...",
                    args.model,
                )
                trad_agent = _make_traditional_agent(
                    model=args.model,
                    skills_dir=args.skills_dir,
                )
                t0 = time.perf_counter()
                results, accuracy = _run_perpackage(
                    trad_agent, "traditional", args.max_tasks, output_dir,
                    package=package, skills_dir=args.skills_dir, model=args.model,
                    shuffle=args.shuffle, seed=args.seed,
                )
                elapsed = time.perf_counter() - t0
                logger.info("Traditional agent completed %s in %.1fs", bench_name, elapsed)
                traditional_results[bench_name] = results
                traditional_accuracies[bench_name] = accuracy

            if args.mode in ("acp-mcp", "both"):
                logger.info("Creating OntoSkills agent (model=%s)...", args.model)
                os_agent = _make_ontoskills_agent(
                    model=args.model,
                    ttl_dir=args.ttl_dir,
                    ontomcp_bin=args.ontomcp_bin,
                )
                t0 = time.perf_counter()
                results, accuracy = _run_perpackage(
                    os_agent, "ontoskills", args.max_tasks, output_dir,
                    package=package, model=args.model,
                    shuffle=args.shuffle, seed=args.seed,
                )
                elapsed = time.perf_counter() - t0
                logger.info("OntoSkills agent completed %s in %.1fs", bench_name, elapsed)
                ontoskills_results[bench_name] = results
                ontoskills_accuracies[bench_name] = accuracy

        else:
            runner = _BENCHMARK_RUNNERS[bench_name]

            if args.mode in ("acp", "both"):
                # GAIA/SWE-bench: per-task scoped skill loading (2-3 relevant skills).
                # acp maps to traditional agent.
                logger.info(
                    "Creating traditional agent (model=%s, per-task skill scoping)...",
                    args.model,
                )
                trad_agent = _make_traditional_agent(
                    model=args.model,
                    skills_dir=args.skills_dir,
                )
                t0 = time.perf_counter()
                kwargs = dict(
                    skills_dir=args.skills_dir, model=args.model,
                    shuffle=args.shuffle, seed=args.seed,
                )
                if bench_name == "gaia":
                    kwargs["gaia_level"] = args.gaia_level
                results, accuracy = runner(
                    trad_agent, "traditional", args.max_tasks, output_dir,
                    **kwargs,
                )
                elapsed = time.perf_counter() - t0
                logger.info("Traditional agent completed %s in %.1fs", bench_name, elapsed)
                traditional_results[bench_name] = results
                traditional_accuracies[bench_name] = accuracy

            if args.mode in ("acp-mcp", "both"):
                # acp-mcp maps to ontoskills agent.
                logger.info("Creating OntoSkills agent (model=%s)...", args.model)
                os_agent = _make_ontoskills_agent(
                    model=args.model,
                    ttl_dir=args.ttl_dir,
                    ontomcp_bin=args.ontomcp_bin,
                )
                t0 = time.perf_counter()
                kwargs = dict(
                    shuffle=args.shuffle, seed=args.seed,
                )
                if bench_name == "gaia":
                    kwargs["gaia_level"] = args.gaia_level
                results, accuracy = runner(
                    os_agent, "ontoskills", args.max_tasks, output_dir,
                    **kwargs,
                )
                elapsed = time.perf_counter() - t0
                logger.info("OntoSkills agent completed %s in %.1fs", bench_name, elapsed)
                ontoskills_results[bench_name] = results
                ontoskills_accuracies[bench_name] = accuracy

    # Generate comparison report if both modes ran.
    if args.mode == "both" and traditional_results and ontoskills_results:
        logger.info("Generating comparison report...")
        _generate_comparison(
            traditional_results,
            ontoskills_results,
            traditional_accuracies,
            ontoskills_accuracies,
            output_dir,
        )
    elif args.mode == "all5" and (traditional_results or ontoskills_results):
        logger.info("Generating all5 summary report...")
        _generate_all5_summary(
            traditional_results, ontoskills_results,
            traditional_accuracies, ontoskills_accuracies,
            output_dir,
        )

    logger.info("All done. Results in %s", output_dir)


if __name__ == "__main__":
    main()
