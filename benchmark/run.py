#!/usr/bin/env python3
"""Main orchestrator: run benchmarks and generate comparison report.

Usage:
    python run.py --benchmark {gaia,swebench,perpackage,skillsbench,all} --mode {traditional,ontoskills,both}
                  --skills-dir <path> --ttl-dir <path> --ontomcp-bin <path>
                  --model <model_id> --max-tasks <N> --output-dir <path>

Examples:
    # Run GAIA with both agents (traditional + ontoskills)
    python run.py --benchmark gaia --mode both --max-tasks 10

    # Run SWE-bench with only the OntoSkills agent
    python run.py --benchmark swebench --mode ontoskills --ttl-dir /path/to/ttls

    # Run all benchmarks, both modes
    python run.py --benchmark all --mode both

    # Only traditional agent (needs ANTHROPIC_API_KEY)
    python run.py --benchmark gaia --mode traditional --skills-dir /path/to/skills
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


def _run_skillsbench(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    shuffle: bool = True,
    seed: int = 42,
    skillsbench_repo: str = "/tmp/skillsbench_full",
    workers: int = 3,
    skip_first: int = 0,
) -> tuple[list[dict], float | None]:
    """Run the SkillsBench benchmark with deterministic Docker-based evaluation.

    Returns (results_list, pass_rate).
    """
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)
    results = wrapper.run_benchmark(
        agent, max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        workers=workers, skip_first=skip_first,
    )

    # Score from Docker reward.txt (deterministic).
    tasks = wrapper.load_tasks(max_tasks=max_tasks, shuffle=shuffle, seed=seed, skip_first=skip_first)
    score = SkillsBenchWrapper.score(results, tasks)
    logger.info(
        "SkillsBench (%s): %d/%d passed (%.1f%%)",
        mode,
        score["tasks_passed"],
        score["total_tasks"],
        score["pass_rate"] * 100,
    )

    # Save results.
    raw_path = output_dir / "skillsbench" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save scores.
    score_path = output_dir / "skillsbench" / mode / "score.json"
    score_path.write_text(
        json.dumps(score, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save chart data.
    chart = generate_chart_data("skillsbench", mode, results, score, model=getattr(agent, "model", ""))
    save_chart_data(chart, str(output_dir / "skillsbench" / mode / "chart_data.json"))

    return results, score["pass_rate"]


def _run_skillsbench_claudecode(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
    *,
    skills_dir: str | None = None,
    model: str = "glm-5.1",
    shuffle: bool = True,
    seed: int = 42,
    skillsbench_repo: str = "/tmp/skillsbench_full",
    workers: int = 3,
    skip_first: int = 0,
) -> tuple[list[dict], float | None]:
    """Run SkillsBench using the Claude Code CLI for realistic evaluation.

    Returns (results_list, pass_rate).
    """
    from benchmark.wrappers.skillsbench import SkillsBenchWrapper

    wrapper = SkillsBenchWrapper(repo_path=skillsbench_repo)
    results = wrapper.run_benchmark_claudecode(
        agent, max_tasks=max_tasks, shuffle=shuffle, seed=seed,
        workers=workers, skip_first=skip_first,
    )

    # Score from Docker reward.txt (deterministic).
    tasks = wrapper.load_tasks(max_tasks=max_tasks, shuffle=shuffle, seed=seed, skip_first=skip_first)
    score = SkillsBenchWrapper.score(results, tasks)
    logger.info(
        "SkillsBench ClaudeCode (%s): %d/%d passed (%.1f%%)",
        mode,
        score["tasks_passed"],
        score["total_tasks"],
        score["pass_rate"] * 100,
    )

    # Save results.
    raw_path = output_dir / "skillsbench" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save scores.
    score_path = output_dir / "skillsbench" / mode / "score.json"
    score_path.write_text(
        json.dumps(score, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save chart data.
    chart = generate_chart_data("skillsbench", mode, results, score, model=getattr(agent, "model", ""))
    save_chart_data(chart, str(output_dir / "skillsbench" / mode / "chart_data.json"))

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
            "  python run.py --benchmark gaia --mode both --max-tasks 10\n"
            "  python run.py --benchmark swebench --mode ontoskills\n"
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
        choices=["traditional", "ontoskills", "both", "claudecode", "claudecode-mcp"],
        default="both",
        help=(
            "Which agent mode to run (default: both). "
            "'claudecode' = Claude Code CLI with skills in .claude/skills/. "
            "'claudecode-mcp' = Claude Code CLI with OntoSkills MCP tools."
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
        default=3,
        help="Parallel Docker verification workers (default: 3)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
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
    if args.mode in ("traditional", "both"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error(
                "ANTHROPIC_API_KEY is required for the traditional agent. "
                "Set it or use --mode ontoskills."
            )
        if not Path(args.skills_dir).exists():
            logger.warning(
                "Skills directory not found: %s — traditional agent will have no skills.",
                args.skills_dir,
            )

    if args.mode in ("ontoskills", "both"):
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

        if bench_name == "perpackage":
            # Per-package benchmark: wrapper handles skill scoping per task.
            package = args.package

            if args.mode in ("traditional", "both"):
                logger.info(
                    "Creating traditional agent (model=%s, per-task skill scoping)...",
                    args.model,
                )
                # Pass skills_dir so the wrapper can find SKILL.md files.
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

            if args.mode in ("ontoskills", "both"):
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

        elif bench_name == "skillsbench":
            # SkillsBench: wrapper fetches tasks from GitHub, scopes skills per task.
            if args.mode in ("claudecode", "claudecode-mcp"):
                # Claude Code CLI mode — realistic agent evaluation.
                from benchmark.agents.claudecode import ClaudeCodeAgent
                cc_mode = "traditional" if args.mode == "claudecode" else "ontoskills"
                cc_tag = args.mode  # for output directory naming
                logger.info(
                    "Creating Claude Code agent (mode=%s, model=%s, SkillsBench)...",
                    cc_mode, args.model,
                )
                cc_agent = ClaudeCodeAgent(
                    model=args.model,
                    mode=cc_mode,
                    skills_dir=args.skills_dir,
                    ontomcp_bin=args.ontomcp_bin,
                )
                t0 = time.perf_counter()
                results, accuracy = _run_skillsbench_claudecode(
                    cc_agent, cc_tag, args.max_tasks, output_dir,
                    skills_dir=args.skills_dir, model=args.model,
                    shuffle=args.shuffle, seed=args.seed,
                    skillsbench_repo=args.skillsbench_repo,
                    workers=args.workers, skip_first=args.skip_first,
                )
                elapsed = time.perf_counter() - t0
                logger.info("Claude Code (%s) completed %s in %.1fs", cc_tag, bench_name, elapsed)
                results_dict = ontoskills_results if cc_mode == "ontoskills" else traditional_results
                accuracy_dict = ontoskills_accuracies if cc_mode == "ontoskills" else traditional_accuracies
                results_dict[bench_name] = results
                accuracy_dict[bench_name] = accuracy

            else:
                if args.mode in ("traditional", "both"):
                    logger.info(
                        "Creating traditional agent (model=%s, SkillsBench)...",
                        args.model,
                    )
                    trad_agent = _make_traditional_agent(
                        model=args.model,
                        skills_dir=args.skills_dir,
                    )
                    t0 = time.perf_counter()
                    results, accuracy = _run_skillsbench(
                        trad_agent, "traditional", args.max_tasks, output_dir,
                        skills_dir=args.skills_dir, model=args.model,
                        shuffle=args.shuffle, seed=args.seed,
                        skillsbench_repo=args.skillsbench_repo,
                        workers=args.workers, skip_first=args.skip_first,
                    )
                    elapsed = time.perf_counter() - t0
                    logger.info("Traditional agent completed %s in %.1fs", bench_name, elapsed)
                    traditional_results[bench_name] = results
                    traditional_accuracies[bench_name] = accuracy

                if args.mode in ("ontoskills", "both"):
                    logger.info("Creating OntoSkills agent (model=%s)...", args.model)
                    os_agent = _make_ontoskills_agent(
                        model=args.model,
                        ttl_dir=args.ttl_dir,
                        ontomcp_bin=args.ontomcp_bin,
                    )
                    t0 = time.perf_counter()
                    results, accuracy = _run_skillsbench(
                        os_agent, "ontoskills", args.max_tasks, output_dir,
                        model=args.model,
                        shuffle=args.shuffle, seed=args.seed,
                        skillsbench_repo=args.skillsbench_repo,
                        workers=args.workers, skip_first=args.skip_first,
                    )
                    elapsed = time.perf_counter() - t0
                    logger.info("OntoSkills agent completed %s in %.1fs", bench_name, elapsed)
                    ontoskills_results[bench_name] = results
                    ontoskills_accuracies[bench_name] = accuracy

        else:
            runner = _BENCHMARK_RUNNERS[bench_name]

            if args.mode in ("traditional", "both"):
                # GAIA/SWE-bench: per-task scoped skill loading (2-3 relevant skills).
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

            if args.mode in ("ontoskills", "both"):
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

    logger.info("All done. Results in %s", output_dir)


if __name__ == "__main__":
    main()
