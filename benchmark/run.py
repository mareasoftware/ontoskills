#!/usr/bin/env python3
"""Main orchestrator: run benchmarks and generate comparison report.

Usage:
    python run.py --benchmark {gaia,swebench,tau2bench,all} --mode {traditional,ontoskills,both}
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
) -> tuple[list[dict], float | None]:
    """Run the GAIA benchmark for one agent.

    Returns (results_list, accuracy_or_None).
    """
    from benchmark.wrappers.gaia import GAIAWrapper

    wrapper = GAIAWrapper(data_dir=str(BENCHMARK_DIR / "data" / "gaia"))
    results = wrapper.run_benchmark(
        agent,
        level=BENCHMARK_CONFIG["gaia"]["levels"][0],
        max_tasks=max_tasks,
    )

    # Score — GAIA gold answers may not be available (gated dataset).
    gold: dict[str, str] = {}
    for r in results:
        task = next(
            (t for t in wrapper.load_dataset(
                level=BENCHMARK_CONFIG["gaia"]["levels"][0],
            ) if t["task_id"] == r["task_id"]),
            None,
        )
        if task and task.get("gold_answer"):
            gold[task["task_id"]] = task["gold_answer"]

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
    )

    # Save predictions.
    raw_path = output_dir / "swebench" / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    pred_path = output_dir / "swebench" / mode / "predictions.json"
    SWEBenchWrapper.write_predictions(results, str(pred_path))

    logger.info("SWE-bench (%s): %d instances completed", mode, len(results))
    return results, None  # SWE-bench eval is external


def _run_tau2bench(
    agent,
    mode: str,
    max_tasks: int | None,
    output_dir: Path,
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
        )
        all_results.extend(results)

        # Score per domain.
        expected: dict[str, list[str]] = {}
        try:
            tasks = wrapper.load_dataset(domain=domain)
            for t in tasks:
                if t.get("expected_outputs"):
                    expected[t["task_id"]] = t["expected_outputs"]
        except ImportError:
            pass

        if expected:
            score = Tau2BenchWrapper.score(results, expected)
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
) -> tuple[list[dict], float | None]:
    """Run the per-package benchmark for one agent.

    Returns (results_list, keyword_coverage_or_None).
    """
    from benchmark.wrappers.perpackage import PerPackageWrapper

    wrapper = PerPackageWrapper(
        skills_dir=skills_dir or str(BENCHMARK_DIR / "skills"),
    )
    tasks = wrapper.load_tasks(package=package)
    results = wrapper.run_benchmark(agent, package=package, max_tasks=max_tasks)

    # Score.
    score = PerPackageWrapper.score(results, tasks)
    logger.info(
        "Per-package %s (%s): %.1f%% pass rate, %.1f%% keyword coverage (%d/%d)",
        package, mode, score["pass_rate"] * 100, score["keyword_coverage"] * 100,
        score["tasks_passed"], score["total_tasks"],
    )

    # Save results.
    raw_path = output_dir / "perpackage" / package / mode / "results.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(results, raw_path)

    # Save score.
    score_path = output_dir / "perpackage" / package / mode / "score.json"
    score_path.write_text(
        json.dumps(score, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    return results, score["keyword_coverage"]


# Map benchmark names to runner functions.
_BENCHMARK_RUNNERS = {
    "gaia": _run_gaia,
    "swebench": _run_swebench,
    "tau2bench": _run_tau2bench,
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
        choices=["gaia", "swebench", "tau2bench", "perpackage", "all"],
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
        choices=["traditional", "ontoskills", "both"],
        default="both",
        help="Which agent mode to run (default: both)",
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
        default=ANTHROPIC_MODELS[0] if ANTHROPIC_MODELS else "claude-sonnet-4-6",
        help="Anthropic model ID to use (default: first Anthropic model from config)",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Maximum number of tasks to run per benchmark (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(BENCHMARK_DIR / "results"),
        help="Directory to write results to (default: benchmark/results/)",
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
        benchmarks = list(_BENCHMARK_RUNNERS.keys())
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
                    package=package, skills_dir=args.skills_dir,
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
                    package=package,
                )
                elapsed = time.perf_counter() - t0
                logger.info("OntoSkills agent completed %s in %.1fs", bench_name, elapsed)
                ontoskills_results[bench_name] = results
                ontoskills_accuracies[bench_name] = accuracy

        else:
            runner = _BENCHMARK_RUNNERS[bench_name]

            if args.mode in ("traditional", "both"):
                logger.info("Creating traditional agent (model=%s)...", args.model)
                trad_agent = _make_traditional_agent(
                    model=args.model,
                    skills_dir=args.skills_dir,
                )
                t0 = time.perf_counter()
                results, accuracy = runner(trad_agent, "traditional", args.max_tasks, output_dir)
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
                results, accuracy = runner(os_agent, "ontoskills", args.max_tasks, output_dir)
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
