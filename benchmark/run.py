#!/usr/bin/env python3
"""Run both benchmarks and produce a comparison report.

Usage:
    # Run with real skill directories
    python run.py --skills-dir /path/to/skills --ttl-dir /path/to/ttls

    # Only OntoMCP (no API key needed)
    python run.py --ttl-dir /path/to/ttls --ontomcp-only

    # Only traditional (needs ANTHROPIC_API_KEY)
    python run.py --skills-dir /path/to/skills --traditional-only

    # Custom iterations and runs
    python run.py --skills-dir /path/to/skills --ttl-dir /path/to/ttls --iterations 100 --runs 3
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).parent
RESULTS_DIR = BENCHMARK_DIR / "results"


def run_ontomcp_bench(ttl_dir: str, iterations: int, output: str):
    """Build and run the OntoMCP Rust benchmark."""
    print(f"\n{'='*60}")
    print("Running OntoMCP benchmark...")
    print(f"{'='*60}")

    bench_dir = BENCHMARK_DIR / "ontomcp-bench"

    # Use cargo run for cross-platform binary path handling
    subprocess.run(
        [
            "cargo", "run", "--release",
            "--manifest-path", str(bench_dir / "Cargo.toml"),
            "--", ttl_dir, str(iterations), output,
        ],
        check=True,
    )


def run_traditional_bench(skills_dir: str, runs: int, output: str):
    """Run the traditional LLM benchmark."""
    print(f"\n{'='*60}")
    print("Running Traditional benchmark...")
    print(f"{'='*60}")

    bench_script = BENCHMARK_DIR / "traditional-bench" / "bench.py"
    subprocess.run(
        [sys.executable, str(bench_script), skills_dir, str(runs), output],
        check=True,
    )


def generate_comparison():
    """Generate the Markdown comparison report."""
    print(f"\n{'='*60}")
    print("Generating comparison report...")
    print(f"{'='*60}")

    subprocess.run(
        [sys.executable, str(BENCHMARK_DIR / "compare.py")],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description="OntoSkills Benchmark Runner")
    parser.add_argument(
        "--skills-dir",
        default=str(BENCHMARK_DIR / "skills"),
        help="Directory of .md skill files (for traditional bench)",
    )
    parser.add_argument(
        "--ttl-dir",
        help="Directory of .ttl ontology files (for OntoMCP bench). Required unless --traditional-only.",
    )
    parser.add_argument(
        "--iterations", type=int, default=1000, help="Iterations for OntoMCP bench"
    )
    parser.add_argument(
        "--runs", type=int, default=5, help="Runs per task for traditional bench"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--ontomcp-only", action="store_true", help="Only run OntoMCP benchmark"
    )
    mode_group.add_argument(
        "--traditional-only", action="store_true", help="Only run traditional benchmark"
    )

    args = parser.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    ontomcp_output = str(RESULTS_DIR / "ontomcp-bench.json")
    traditional_output = str(RESULTS_DIR / "traditional-bench.json")

    # Check API key early
    if not args.ontomcp_only and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Set it or use --ontomcp-only.")
        sys.exit(1)

    # Validate --ttl-dir when OntoMCP runs
    if not args.traditional_only and not args.ttl_dir:
        print("Error: --ttl-dir is required when running the OntoMCP benchmark.")
        print("  Use --traditional-only to skip it, or provide --ttl-dir /path/to/ttls.")
        sys.exit(1)

    # Run benchmarks
    if not args.traditional_only:
        run_ontomcp_bench(args.ttl_dir, args.iterations, ontomcp_output)

    if not args.ontomcp_only:
        run_traditional_bench(args.skills_dir, args.runs, traditional_output)

    # Generate comparison report
    generate_comparison()


if __name__ == "__main__":
    main()
