"""Metric dataclasses and aggregation functions for benchmark results.

Computes per-agent, per-benchmark metrics from the raw task result dicts
produced by the wrapper ``run_benchmark`` methods, and assembles them into
head-to-head comparisons.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AgentMetrics:
    """Aggregated metrics for one agent on one benchmark."""

    agent_type: str          # "traditional" or "ontoskills"
    benchmark: str           # "gaia", "swebench", "tau2bench"
    num_tasks: int
    accuracy: float | None   # GAIA: exact match, SWE-bench: resolve rate, Tau2: pass rate
    avg_input_tokens: float
    avg_output_tokens: float
    avg_total_tokens: float
    avg_latency_ms: float
    avg_tool_calls: float
    avg_turns: float


@dataclass
class BenchmarkComparison:
    """Head-to-head comparison for one benchmark."""

    benchmark: str
    traditional: AgentMetrics | None
    ontoskills: AgentMetrics | None
    accuracy_delta: float | None        # ontoskills - traditional
    token_reduction_pct: float | None   # how many fewer tokens ontoskills uses
    latency_delta_pct: float | None     # (ontoskills - traditional) / traditional * 100


@dataclass
class AggregateReport:
    """Overall comparison across all benchmarks."""

    comparisons: list[BenchmarkComparison] = field(default_factory=list)
    overall_accuracy_delta: float | None = None
    overall_token_reduction_pct: float | None = None
    tool_usage_by_benchmark: dict[str, dict[str, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper: extract metric values from a single task result dict
# ---------------------------------------------------------------------------

def _extract_metrics(result: dict) -> dict | None:
    """Extract metric values from a task result dict.

    Each result has a ``"metrics"`` field that is either an ``AgentResult``
    instance (has named attributes) or ``None``.  Returns ``None`` when the
    metrics are absent.
    """
    m = result.get("metrics")
    if m is None:
        return None

    # Support both AgentResult objects and plain dicts (e.g. from JSON reload).
    def _get(key, default=0):
        if isinstance(m, dict):
            return m.get(key, default)
        return getattr(m, key, default)

    return {
        "input_tokens": _get("input_tokens"),
        "output_tokens": _get("output_tokens"),
        "total_latency_ms": _get("total_latency_ms", _get("latency_ms", 0.0)),
        "tool_calls": _get("tool_calls"),
        "turns": _get("turns"),
    }


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_agent_metrics(
    agent_type: str,
    benchmark: str,
    results: list[dict],
    accuracy: float | None = None,
) -> AgentMetrics:
    """Compute aggregated metrics from a list of task results.

    Parameters
    ----------
    agent_type:
        ``"traditional"`` or ``"ontoskills"``.
    benchmark:
        Benchmark identifier (``"gaia"``, ``"swebench"``, ``"tau2bench"``).
    results:
        List of result dicts as returned by the wrapper ``run_benchmark``
        methods.  Each dict has ``"task_id"``, ``"model_answer"``, and
        ``"metrics"`` (an ``AgentResult`` or ``None``).
    accuracy:
        Pre-computed accuracy / resolve rate / pass rate for the benchmark.
        When ``None`` the accuracy field is left as ``None``.

    Returns
    -------
    AgentMetrics
    """
    extracted = [_extract_metrics(r) for r in results]
    valid = [e for e in extracted if e is not None]
    num_tasks = len(results)

    if not valid:
        return AgentMetrics(
            agent_type=agent_type,
            benchmark=benchmark,
            num_tasks=num_tasks,
            accuracy=accuracy,
            avg_input_tokens=0.0,
            avg_output_tokens=0.0,
            avg_total_tokens=0.0,
            avg_latency_ms=0.0,
            avg_tool_calls=0.0,
            avg_turns=0.0,
        )

    input_tokens = [e["input_tokens"] for e in valid]
    output_tokens = [e["output_tokens"] for e in valid]
    latencies = [e["total_latency_ms"] for e in valid]
    tool_calls_list = [e["tool_calls"] for e in valid]
    turns_list = [e["turns"] for e in valid]

    total_tokens = [i + o for i, o in zip(input_tokens, output_tokens)]

    return AgentMetrics(
        agent_type=agent_type,
        benchmark=benchmark,
        num_tasks=num_tasks,
        accuracy=accuracy,
        avg_input_tokens=statistics.mean(input_tokens),
        avg_output_tokens=statistics.mean(output_tokens),
        avg_total_tokens=statistics.mean(total_tokens),
        avg_latency_ms=statistics.mean(latencies),
        avg_tool_calls=statistics.mean(tool_calls_list),
        avg_turns=statistics.mean(turns_list),
    )


def _pct_delta(new: float, old: float) -> float | None:
    """Compute percentage delta as ``(new - old) / old * 100``.
    Returns ``None`` when *old* is zero.
    """
    if old == 0:
        return None
    return (new - old) / old * 100


def _token_reduction_pct(os_metrics: AgentMetrics, tr_metrics: AgentMetrics) -> float | None:
    """How many fewer total tokens ontoskills uses vs traditional.

    Returns a negative value when ontoskills uses *more* tokens, or ``None``
    when traditional total is zero.
    """
    tr_total = tr_metrics.avg_total_tokens
    os_total = os_metrics.avg_total_tokens
    if tr_total == 0:
        return None
    return (tr_total - os_total) / tr_total * 100


def compute_comparison(
    traditional_results: dict[str, list[dict]],
    ontoskills_results: dict[str, list[dict]],
    *,
    traditional_accuracies: dict[str, float | None] | None = None,
    ontoskills_accuracies: dict[str, float | None] | None = None,
) -> AggregateReport:
    """Compute full comparison across all benchmarks.

    Parameters
    ----------
    traditional_results:
        Mapping of benchmark name to list of task result dicts, e.g.
        ``{"gaia": [...], "swebench": [...], "tau2bench": [...]}``.
    ontoskills_results:
        Same structure for OntoSkills agent results.
    traditional_accuracies:
        Optional mapping of benchmark name to pre-computed accuracy float.
    ontoskills_accuracies:
        Optional mapping of benchmark name to pre-computed accuracy float.

    Returns
    -------
    AggregateReport
    """
    trad_acc = traditional_accuracies or {}
    os_acc = ontoskills_accuracies or {}

    all_benchmarks = sorted(
        set(traditional_results.keys()) | set(ontoskills_results.keys())
    )

    comparisons: list[BenchmarkComparison] = []
    accuracy_deltas: list[float] = []
    token_reductions: list[float] = []
    tool_usage_by_benchmark: dict[str, dict[str, int]] = {}

    for bench in all_benchmarks:
        trad_list = traditional_results.get(bench, [])
        os_list = ontoskills_results.get(bench, [])

        trad_metrics = (
            compute_agent_metrics("traditional", bench, trad_list, trad_acc.get(bench))
            if trad_list
            else None
        )
        os_metrics = (
            compute_agent_metrics("ontoskills", bench, os_list, os_acc.get(bench))
            if os_list
            else None
        )

        # Accuracy delta
        acc_delta = None
        if trad_metrics and os_metrics:
            if trad_metrics.accuracy is not None and os_metrics.accuracy is not None:
                acc_delta = os_metrics.accuracy - trad_metrics.accuracy
                accuracy_deltas.append(acc_delta)

        # Token reduction
        tok_red = None
        if trad_metrics and os_metrics:
            tok_red = _token_reduction_pct(os_metrics, trad_metrics)
            if tok_red is not None:
                token_reductions.append(tok_red)

        # Latency delta
        lat_delta = None
        if trad_metrics and os_metrics:
            lat_delta = _pct_delta(os_metrics.avg_latency_ms, trad_metrics.avg_latency_ms)

        comparisons.append(BenchmarkComparison(
            benchmark=bench,
            traditional=trad_metrics,
            ontoskills=os_metrics,
            accuracy_delta=acc_delta,
            token_reduction_pct=tok_red,
            latency_delta_pct=lat_delta,
        ))

        # Tool usage extraction for ontoskills results
        bench_tool_usage: dict[str, int] = {}
        for r in os_list:
            m = r.get("metrics")
            if m is None:
                continue
            # Look for tool_name tracking in the raw result.
            # The wrappers store the tool names used during execution
            # in result["tool_names"] (if tracked by the wrapper/agent).
            for name in r.get("tool_names", []):
                bench_tool_usage[name] = bench_tool_usage.get(name, 0) + 1
        if bench_tool_usage:
            tool_usage_by_benchmark[bench] = bench_tool_usage

    # Aggregate across benchmarks (simple mean)
    overall_acc_delta = (
        statistics.mean(accuracy_deltas) if accuracy_deltas else None
    )
    overall_tok_red = (
        statistics.mean(token_reductions) if token_reductions else None
    )

    return AggregateReport(
        comparisons=comparisons,
        overall_accuracy_delta=overall_acc_delta,
        overall_token_reduction_pct=overall_tok_red,
        tool_usage_by_benchmark=tool_usage_by_benchmark,
    )
