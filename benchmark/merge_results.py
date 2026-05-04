"""Merge benchmark results from separate runs into a combined dataset.

Use when you ran tasks in batches (e.g. 10 + 15 = 25 tasks) with the
same seed and want to produce a single results.json / score.json.

Usage:
    python benchmark/merge_results.py \\
        --benchmark skillsbench \\
        --mode claudecode \\
        --results-dir benchmark/results/skillsbench/claudecode \\
        --output-dir benchmark/results/skillsbench-merged/claudecode \\
        --seed 7 --max-tasks 25
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def merge_results(
    result_dirs: list[Path],
    output_dir: Path,
    benchmark: str = "skillsbench",
) -> dict:
    """Merge results.json from multiple directories.

    Deduplicates by task_id (first occurrence wins — earlier runs take
    priority over later ones).

    Returns the merged score dict.
    """
    all_results: list[dict] = []
    seen_ids: set[str] = set()

    for rdir in result_dirs:
        results_file = rdir / "results.json"
        if not results_file.exists():
            print(f"  Skipping {rdir}: no results.json")
            continue

        results = json.loads(results_file.read_text(encoding="utf-8"))
        added = 0
        for r in results:
            tid = r.get("task_id", r.get("instance_id", ""))
            if tid and tid not in seen_ids:
                all_results.append(r)
                seen_ids.add(tid)
                added += 1
        print(f"  {rdir}: {len(results)} tasks, {added} new (deduped)")

    print(f"  Total merged: {len(all_results)} tasks")

    # Save merged results.
    output_dir.mkdir(parents=True, exist_ok=True)
    merged_results_path = output_dir / "results.json"
    merged_results_path.write_text(
        json.dumps(all_results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    # Score the merged results using the appropriate wrapper.
    if benchmark == "skillsbench":
        from benchmark.wrappers.skillsbench import SkillsBenchWrapper

        wrapper = SkillsBenchWrapper(
            repo_path=os.path.expanduser("~/.ontoskills/skillsbench"),
        )
        # Load ALL tasks that appear in merged results (no filtering).
        tasks = []
        for r in all_results:
            tid = r.get("task_id", "")
            task_dir = Path(os.path.expanduser("~/.ontoskills/skillsbench")) / "tasks" / tid
            if task_dir.is_dir():
                tasks.append({"task_id": tid, "task_dir": str(task_dir)})

        score = SkillsBenchWrapper.score(all_results)
        score_path = output_dir / "score.json"
        score_path.write_text(
            json.dumps(score, indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Score: {score['tasks_passed']}/{score['total_tasks']} passed ({score['pass_rate']*100:.0f}%)")

        # Generate chart data.
        from benchmark.reporting.chart_data import generate_chart_data, save_chart_data
        chart = generate_chart_data(benchmark, "merged", all_results, score)
        save_chart_data(chart, str(output_dir / "chart_data.json"))

        return score

    return {"total_tasks": len(all_results)}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Merge benchmark results from separate runs")
    parser.add_argument("--benchmark", default="skillsbench")
    parser.add_argument(
        "--results-dirs", nargs="+",
        help="Directories containing results.json to merge (in priority order)",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    dirs = [Path(d) for d in args.results_dirs]
    output = Path(args.output_dir)

    print(f"Merging {len(dirs)} result directories into {output}")
    merge_results(dirs, output, benchmark=args.benchmark)


if __name__ == "__main__":
    main()
