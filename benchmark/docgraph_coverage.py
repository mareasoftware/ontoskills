#!/usr/bin/env python3
"""DocGraph coverage benchmark — line-level metric against real skills.

Measures how much of each SKILL.md is captured as typed RDF nodes.
Target: ≥95% line-level coverage.

Usage:
    python benchmark/docgraph_coverage.py --verbose
    python benchmark/docgraph_coverage.py --json results.json
    python benchmark/docgraph_coverage.py --target 95
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add core to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "src"))

from compiler.content_parser import extract_flat_blocks, extract_structural_content


def _env_path(name, fallback):
    value = os.environ.get(name)
    return Path(value).expanduser() if value else Path(fallback)


_SKILLS_DIR = _env_path("DOCGRAPH_SKILLS_DIR", str(
    Path(__file__).resolve().parent.parent / ".agents" / "skills"))


def collect_skill_paths():
    paths = []
    skills_dir = _SKILLS_DIR
    if not skills_dir.is_dir():
        return paths
    for p in sorted(skills_dir.rglob("SKILL.md")):
        vendor = p.parent.parent.parent.name if len(p.parts) > 5 else "local"
        paths.append((vendor, p))
    return paths


def calc_line_coverage(md, blocks):
    """Line-level coverage: what % of non-blank lines fall within a FlatBlock range."""
    lines = md.splitlines()
    covered = set()
    for b in blocks:
        for line_no in range(b.line_start - 1, b.line_end):
            if 0 <= line_no < len(lines):
                covered.add(line_no)
    total_content = sum(
        1 for i, l in enumerate(lines)
        if l.strip() and l.strip() not in ("---", "***", "___")
    )
    covered_content = sum(
        1 for i in covered
        if i < len(lines) and lines[i].strip() and lines[i].strip() not in ("---", "***", "___")
    )
    return covered_content / total_content * 100 if total_content else 100.0


def run_benchmark(target=95.0, verbose=False, json_output=None):
    paths = collect_skill_paths()
    if len(paths) < 10:
        print(f"Warning: only {len(paths)} skills found. Expected 30+.")

    results = []
    for source, path in paths:
        md = path.read_text()
        blocks = extract_flat_blocks(md)
        coverage = calc_line_coverage(md, blocks)
        results.append({"source": source, "name": path.parent.name, "coverage": round(coverage, 1)})

    avg = sum(r["coverage"] for r in results) / len(results) if results else 0
    below_target = [r for r in results if r["coverage"] < target]

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"DOCGRAPH COVERAGE — {len(results)} skills")
        print(f"{'=' * 70}")
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        print(f"  Skeleton LLM: {'ACTIVE' if has_api_key else 'INACTIVE (set ANTHROPIC_API_KEY)'}")
        print()
        for r in sorted(results, key=lambda x: x["coverage"]):
            marker = " <<<" if r["coverage"] < target else ""
            print(f"  {r['source']:>3} {r['name']:<38} {r['coverage']:>6.1f}%{marker}")
        print(f"\n  Average: {avg:.1f}%")
        if below_target:
            print(f"  Below {target}%: {len(below_target)} skills")
        print(f"{'=' * 70}")

    if json_output:
        with open(json_output, "w") as f:
            json.dump({"average": round(avg, 1), "target": target, "skills": results}, f, indent=2)
        if verbose:
            print(f"  Results written to {json_output}")

    # Exit code
    if avg < target:
        print(f"\nFAIL: Average coverage {avg:.1f}% below target {target}%")
        return 1

    print(f"\nPASS: Average coverage {avg:.1f}% >= {target}%")
    return 0


def main():
    parser = argparse.ArgumentParser(description="DocGraph coverage benchmark")
    parser.add_argument("--verbose", "-v", action="store_true", help="Per-skill report")
    parser.add_argument("--json", dest="json_output", help="Write results to JSON file")
    parser.add_argument("--target", type=float, default=95.0, help="Coverage target %% (default: 95)")
    args = parser.parse_args()

    if not _SKILLS_DIR.is_dir():
        print(f"Error: Skills directory not found: {_SKILLS_DIR}")
        print(f"Set DOCGRAPH_SKILLS_DIR to override.")
        sys.exit(1)

    sys.exit(run_benchmark(target=args.target, verbose=args.verbose, json_output=args.json_output))


if __name__ == "__main__":
    main()
