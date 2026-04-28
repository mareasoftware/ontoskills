"""Markdown comparison report generator.

Produces a 5-section report from an :class:`AggregateReport`:

1. **Quality** — accuracy / pass-rate per benchmark, delta
2. **Efficiency** — tokens, latency, turns, tool calls per benchmark
3. **Cost** — projection on 7 models using ``config.MODEL_PRICING``
4. **Aggregate** — weighted averages, % improvement
5. **Workflow** — tool usage patterns
"""

from __future__ import annotations

from pathlib import Path

from benchmark.config import MODEL_PRICING, get_cost_usd
from benchmark.reporting.metrics import AgentMetrics, AggregateReport


# ---------------------------------------------------------------------------
# Formatting helpers  (from the original compare.py)
# ---------------------------------------------------------------------------

def fmt_us(microseconds: float) -> str:
    """Format microseconds to a human-readable string."""
    if microseconds < 1_000:
        return f"{microseconds:.0f}μs"
    if microseconds < 1_000_000:
        return f"{microseconds / 1_000:.0f}ms"
    return f"{microseconds / 1_000_000:.1f}s"


def fmt_usd(cost: float) -> str:
    """Format a USD cost value."""
    if cost < 0.001:
        return f"${cost:.6f}"
    if cost < 1:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _pct(val: float | None) -> str:
    """Format a percentage or return ``n/a``."""
    if val is None:
        return "n/a"
    return f"{val:+.1f}%"


def _f(val: float, decimals: int = 1) -> str:
    """Format a float with commas and decimal places."""
    if val >= 1_000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_comparison_report(report: AggregateReport, config: dict | None = None) -> str:
    """Generate a Markdown comparison report.

    Parameters
    ----------
    report:
        The :class:`AggregateReport` with computed metrics and comparisons.
    config:
        Optional config dict (currently unused; reserved for future
        customisation).

    Returns
    -------
    str
        The full Markdown report.
    """
    lines: list[str] = []
    lines.append("# Benchmark Comparison Report")
    lines.append("")
    lines.append("> OntoSkills (MCP-powered) vs Traditional (no tools) agent")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 1: Quality
    # ------------------------------------------------------------------
    lines.append("## 1. Quality (Accuracy)")
    lines.append("")
    lines.append("| Benchmark | Traditional | OntoSkills | Delta |")
    lines.append("|-----------|------------|------------|-------|")

    for comp in report.comparisons:
        tr_acc = _fmt_accuracy(comp.traditional)
        os_acc = _fmt_accuracy(comp.ontoskills)
        delta = _pct(comp.accuracy_delta) if comp.accuracy_delta is not None else "n/a"
        lines.append(f"| {comp.benchmark} | {tr_acc} | {os_acc} | {delta} |")

    lines.append("")

    # ------------------------------------------------------------------
    # Section 2: Efficiency
    # ------------------------------------------------------------------
    lines.append("## 2. Efficiency")
    lines.append("")

    for comp in report.comparisons:
        lines.append(f"### {comp.benchmark}")
        lines.append("")
        lines.append("| Metric | Traditional | OntoSkills | Delta |")
        lines.append("|--------|------------|------------|-------|")

        _add_metric_row(lines, "Avg input tokens", comp.traditional, comp.ontoskills,
                        "avg_input_tokens", _token_fmt)
        _add_metric_row(lines, "Avg output tokens", comp.traditional, comp.ontoskills,
                        "avg_output_tokens", _token_fmt)
        _add_metric_row(lines, "Avg total tokens", comp.traditional, comp.ontoskills,
                        "avg_total_tokens", _token_fmt)
        _add_metric_row(lines, "Avg latency", comp.traditional, comp.ontoskills,
                        "avg_latency_ms", _latency_fmt)
        _add_metric_row(lines, "Avg tool calls", comp.traditional, comp.ontoskills,
                        "avg_tool_calls", _float_fmt)
        _add_metric_row(lines, "Avg turns", comp.traditional, comp.ontoskills,
                        "avg_turns", _float_fmt)
        lines.append("")

    # ------------------------------------------------------------------
    # Section 3: Cost Projection
    # ------------------------------------------------------------------
    lines.append("## 3. Cost Projection (per task, avg tokens)")
    lines.append("")
    lines.append("Token counts from actual Anthropic runs.  Costs for GPT and Gemini")
    lines.append("models are estimated by applying their published rates to the same")
    lines.append("token counts.")
    lines.append("")

    # Build cost tables per benchmark, for both agents.
    for comp in report.comparisons:
        for agent_label, metrics in [
            ("Traditional", comp.traditional),
            ("OntoSkills", comp.ontoskills),
        ]:
            if metrics is None:
                continue

            lines.append(f"### {comp.benchmark} — {agent_label}")
            lines.append("")
            lines.append("| Model | Cost/Task | Cost/100 Tasks |")
            lines.append("|-------|-----------|----------------|")

            avg_in = metrics.avg_input_tokens
            avg_out = metrics.avg_output_tokens

            for model_id in MODEL_PRICING:
                label = MODEL_PRICING[model_id]["label"]
                cost = get_cost_usd(model_id, int(avg_in), int(avg_out))
                per_100 = cost * 100
                lines.append(f"| {label} | {fmt_usd(cost)} | {fmt_usd(per_100)} |")

            lines.append("")

    # ------------------------------------------------------------------
    # Section 4: Aggregate
    # ------------------------------------------------------------------
    lines.append("## 4. Aggregate Summary")
    lines.append("")

    if report.overall_accuracy_delta is not None:
        direction = "improvement" if report.overall_accuracy_delta >= 0 else "degradation"
        lines.append(f"- **Overall accuracy delta:** {report.overall_accuracy_delta:+.2f} ({direction})")
    else:
        lines.append("- **Overall accuracy delta:** n/a")

    if report.overall_token_reduction_pct is not None:
        lines.append(f"- **Overall token reduction:** {report.overall_token_reduction_pct:+.1f}%")
    else:
        lines.append("- **Overall token reduction:** n/a")

    lines.append("")
    lines.append("| Benchmark | Token Reduction | Latency Delta | Accuracy Delta |")
    lines.append("|-----------|----------------|---------------|----------------|")

    for comp in report.comparisons:
        tok = _pct(comp.token_reduction_pct)
        lat = _pct(comp.latency_delta_pct)
        acc = _pct(comp.accuracy_delta) if comp.accuracy_delta is not None else "n/a"
        lines.append(f"| {comp.benchmark} | {tok} | {lat} | {acc} |")

    lines.append("")

    # ------------------------------------------------------------------
    # Section 5: Workflow / Tool Usage
    # ------------------------------------------------------------------
    lines.append("## 5. Workflow (Tool Usage)")
    lines.append("")

    if report.tool_usage_by_benchmark:
        for bench, tool_counts in report.tool_usage_by_benchmark.items():
            lines.append(f"### {bench}")
            lines.append("")
            lines.append("| Tool | Invocations |")
            lines.append("|------|-------------|")
            for tool_name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
                lines.append(f"| {tool_name} | {count} |")
            lines.append("")
    else:
        lines.append("_No tool usage data available. Populate ``tool_names`` in result dicts to enable this section._")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers for table rows
# ---------------------------------------------------------------------------

def _fmt_accuracy(metrics: AgentMetrics | None) -> str:
    """Format accuracy as a percentage string."""
    if metrics is None or metrics.accuracy is None:
        return "n/a"
    return f"{metrics.accuracy * 100:.1f}%"


def _add_metric_row(
    lines: list[str],
    label: str,
    trad: AgentMetrics | None,
    os: AgentMetrics | None,
    attr: str,
    fmt_fn,
) -> None:
    """Append a comparison row for a numeric metric."""
    tr_val = getattr(trad, attr, None) if trad else None
    os_val = getattr(os, attr, None) if os else None
    tr_str = fmt_fn(tr_val) if tr_val is not None else "n/a"
    os_str = fmt_fn(os_val) if os_val is not None else "n/a"
    delta_str = "n/a"
    if tr_val is not None and os_val is not None and tr_val != 0:
        delta = (os_val - tr_val) / tr_val * 100
        delta_str = f"{delta:+.1f}%"
    lines.append(f"| {label} | {tr_str} | {os_str} | {delta_str} |")


def _token_fmt(val: float) -> str:
    return f"{val:,.0f}"


def _latency_fmt(val: float) -> str:
    if val >= 1_000:
        return f"{val / 1_000:.2f}s"
    return f"{val:.0f}ms"


def _float_fmt(val: float) -> str:
    return f"{val:.1f}"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_report(report_text: str, output_path: str) -> None:
    """Save a Markdown report string to a file.

    Creates parent directories if they do not exist.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_text, encoding="utf-8")
