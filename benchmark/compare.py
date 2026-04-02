"""Generate a Markdown comparison report from benchmark JSON results."""

import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).parent
RESULTS_DIR = BENCHMARK_DIR / "results"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def fmt_us(us: int) -> str:
    if us < 1_000:
        return f"{us}μs"
    if us < 1_000_000:
        return f"{us / 1_000:.0f}ms"
    return f"{us / 1_000_000:.1f}s"


def fmt_usd(cost: float) -> str:
    if cost < 0.001:
        return f"${cost:.6f}"
    if cost < 1:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def generate_comparison(ontomcp: dict | None, traditional: dict | None) -> str:
    lines = ["# OntoSkills vs Traditional LLM: Benchmark Results\n"]

    # --- OntoMCP section ---
    if ontomcp:
        lines.append("## OntoSkills (SPARQL)\n")
        lines.append(f"- **Skills loaded:** {ontomcp['total_skills']}")
        lines.append(f"- **Total triples:** {ontomcp['total_triples']:,}")
        lines.append(f"- **Load time:** {ontomcp['load_time_ms']}ms\n")
        lines.append("| Query | p50 | p99 | avg | min | max |")
        lines.append("|-------|-----|-----|-----|-----|-----|")
        for r in ontomcp["results"]:
            is_unavailable = r.get("iterations", 0) == 0 or all(
                r.get(field, 0) == 0 for field in ("p50_us", "p99_us", "avg_us", "min_us", "max_us")
            )
            if is_unavailable:
                lines.append(f"| {r['query_name']} | n/a | n/a | n/a | n/a | n/a |")
            else:
                lines.append(
                    f"| {r['query_name']} | {fmt_us(r['p50_us'])} | {fmt_us(r['p99_us'])} "
                    f"| {fmt_us(r['avg_us'])} | {fmt_us(r['min_us'])} | {fmt_us(r['max_us'])} |"
                )
        lines.append("")

    # --- Traditional section ---
    if traditional:
        lines.append("## Traditional (LLM reads files)\n")
        for model in traditional["models"]:
            label = model["label"]
            lines.append(f"### {label}\n")
            lines.append("| Task | Status | Avg Latency | Tokens (in+out) | Determinism |")
            lines.append("|------|--------|-------------|----------------|-------------|")
            for t in model["tasks"]:
                if t["status"] != "ok":
                    status_label = "FAIL — Out of Context" if t["status"] == "context_overflow" else f"FAIL — {t['status']}"
                    lines.append(
                        f"| {t['task_name']} | {status_label} | — | — | — |"
                    )
                else:
                    lat = t["latency"]["avg_s"]
                    tok_in = t["tokens"]["input_avg"]
                    tok_out = t["tokens"]["output_avg"]
                    det = t["determinism"]["consistency_pct"]
                    lines.append(
                        f"| {t['task_name']} | ok | {lat:.2f}s | "
                        f"{tok_in:,}+{tok_out:,} | {det}% |"
                    )
            lines.append("")

    # --- Head-to-head ---
    if ontomcp and traditional:
        lines.append("## Head-to-Head\n")

        # Find comparable: skill discovery (by intent) vs ontomcp search
        ontomcp_search = next(
            (r for r in ontomcp["results"] if "by intent" in r["query_name"]), None
        )

        if ontomcp_search and traditional["models"]:
            # Use first Anthropic model's skill_discovery task that succeeded
            trad_task = None
            for m in traditional["models"]:
                trad_task = next(
                    (t for t in m["tasks"] if t["task_name"] == "skill_discovery" and t["status"] == "ok"),
                    None,
                )
                if trad_task:
                    break

            if trad_task:
                ontomcp_p50_us = ontomcp_search["p50_us"]
                trad_ms = trad_task["latency"]["p50_s"] * 1_000

                # If the OntoMCP query failed, p50_us is 0 — avoid misleading speedup
                if ontomcp_p50_us > 0:
                    ontomcp_ms = ontomcp_p50_us / 1_000
                    speedup = trad_ms / max(0.001, ontomcp_ms)
                    ontomcp_latency_str = fmt_us(ontomcp_p50_us)
                    speedup_str = f"**{speedup:,.0f}x faster**"
                else:
                    ontomcp_latency_str = "n/a (query unavailable)"
                    speedup_str = "**n/a**"

                lines.append("### Skill Discovery (find skill by intent)\n")
                lines.append("| Metric | OntoSkills | Traditional |")
                lines.append("|--------|-----------|-------------|")
                lines.append(f"| Latency (p50) | {ontomcp_latency_str} | {trad_task['latency']['p50_s']*1000:.0f}ms |")
                lines.append(f"| Tokens per query | 0 | {trad_task['tokens']['input_avg']:,}+{trad_task['tokens']['output_avg']:,} |")
                lines.append(f"| Determinism | 100% | {trad_task['determinism']['consistency_pct']}% |")
                lines.append(f"| **Speedup** | {speedup_str} | |")
                lines.append("")

                # --- Cost comparison across all models ---
                lines.append("### Cost per Query (Skill Discovery)\n")
                lines.append("| Model | Cost/Query | Cost/100 Queries |")
                lines.append("|-------|-----------|------------------|")

                # Import here to avoid circular import at module level
                sys.path.insert(0, str(BENCHMARK_DIR))
                from config import MODEL_PRICING

                for model_id, cost_data in trad_task["cost"].items():
                    label = MODEL_PRICING[model_id]["label"]
                    per_q = cost_data["per_run_usd"]
                    per_100 = per_q * 100
                    lines.append(f"| {label} | {fmt_usd(per_q)} | {fmt_usd(per_100)} |")

                lines.append("")
                lines.append("> OntoSkills cost per query: **$0.00** — no tokens consumed.")

    return "\n".join(lines)


def main():
    ontomcp = load_json(RESULTS_DIR / "ontomcp-bench.json")
    traditional = load_json(RESULTS_DIR / "traditional-bench.json")

    if not ontomcp and not traditional:
        print("No result files found. Run the benchmarks first.")
        sys.exit(1)

    md = generate_comparison(ontomcp, traditional)

    output_path = RESULTS_DIR / "comparison.md"
    with open(output_path, "w") as f:
        f.write(md)

    print(f"Comparison report written to {output_path}")
    print(f"\n{'='*60}")
    print(md)
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
