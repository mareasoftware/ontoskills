"""Generate chart-ready JSON from benchmark results.

Produces structured JSON that can be consumed by Chart.js, D3, or any
charting library for the OntoSkills website.  Includes statistical
analysis: binomial confidence intervals and Fisher's exact test.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path


# ------------------------------------------------------------------
# Statistical helpers
# ------------------------------------------------------------------

def _binomial_ci(successes: int, trials: int, alpha: float = 0.05) -> dict:
    """Wilson score interval for a binomial proportion."""
    if trials == 0:
        return {"estimate": 0.0, "lower": 0.0, "upper": 0.0, "n": 0}
    p_hat = successes / trials
    z = 1.96
    denom = 1 + z ** 2 / trials
    centre = (p_hat + z ** 2 / (2 * trials)) / denom
    spread = z * math.sqrt(p_hat * (1 - p_hat) / trials + z ** 2 / (4 * trials ** 2)) / denom
    return {
        "estimate": round(p_hat, 4),
        "lower": round(max(0, centre - spread), 4),
        "upper": round(min(1, centre + spread), 4),
        "n": trials,
    }


def _fisher_exact(successes_a: int, trials_a: int, successes_b: int, trials_b: int) -> dict:
    """Fisher's exact test for comparing two binomial proportions."""
    try:
        from scipy.stats import fisher_exact as _fisher
        table = [
            [successes_a, trials_a - successes_a],
            [successes_b, trials_b - successes_b],
        ]
        _, p_value = _fisher(table)
        return {"test": "fisher_exact", "p_value": round(p_value, 6)}
    except ImportError:
        pass

    # Chi-squared approximation with Yates' correction.
    a, b = successes_a, successes_b
    c, d = trials_a - successes_a, trials_b - successes_b
    n = a + b + c + d
    if n == 0:
        return {"test": "none", "p_value": None}
    expected_a = (a + c) * (a + b) / n
    chi2 = (abs(a - expected_a) - 0.5) ** 2 / max(expected_a, 0.01)
    return {"test": "chi_squared_approx", "chi2": round(chi2, 4), "p_value": None}


# ------------------------------------------------------------------
# Chart data generation
# ------------------------------------------------------------------

def generate_chart_data(
    benchmark: str,
    mode: str,
    results: list[dict],
    score: dict | None = None,
    model: str = "",
) -> dict:
    """Generate chart-ready JSON from benchmark results."""
    now = datetime.now(timezone.utc).isoformat()

    # Build score lookup for per-task passed/reward data.
    score_by_task: dict[str, dict] = {}
    if score and "per_task" in score:
        for s in score["per_task"]:
            score_by_task[s.get("task_id", "")] = s

    per_task = []
    for r in results:
        m = r.get("metrics", {}) or {}
        tid = r.get("task_id", "")
        sc = score_by_task.get(tid, {})
        per_task.append({
            "task_id": tid,
            "reward": sc.get("reward", r.get("reward", 0)),
            "passed": sc.get("passed", r.get("passed", False)),
            "input_tokens": m.get("input_tokens", 0),
            "output_tokens": m.get("output_tokens", 0),
            "latency_ms": m.get("latency_ms") if m.get("latency_ms") is not None else m.get("total_latency_ms", 0),
            "tool_calls": m.get("tool_calls", 0),
            "cost_usd": m.get("cost_usd", 0),
            "num_turns": m.get("num_turns", 0) or m.get("turns", 0),
        })

    valid_tokens = [(r["input_tokens"], r["output_tokens"]) for r in per_task if r["input_tokens"] > 0]

    summary = {
        "pass_rate": score.get("pass_rate", 0) if score else 0,
        "avg_reward": score.get("avg_reward", 0) if score else 0,
        "tasks_passed": score.get("tasks_passed", 0) if score else 0,
        "tasks_partial": score.get("tasks_partial", 0) if score else 0,
        "tasks_failed": score.get("tasks_failed", 0) if score else 0,
        "total_tasks": score.get("total_tasks", len(results)) if score else len(results),
        "avg_input_tokens": sum(t[0] for t in valid_tokens) / len(valid_tokens) if valid_tokens else 0,
        "avg_output_tokens": sum(t[1] for t in valid_tokens) / len(valid_tokens) if valid_tokens else 0,
        "total_cost_usd": sum(r["cost_usd"] for r in per_task),
    }

    return {
        "benchmark": benchmark,
        "mode": mode,
        "model": model,
        "date": now,
        "per_task": per_task,
        "summary": summary,
    }


def generate_comparison_chart_data(
    traditional_chart: dict,
    ontoskills_chart: dict,
) -> dict:
    """Generate head-to-head comparison chart data with statistics."""
    t_summary = traditional_chart.get("summary", {})
    o_summary = ontoskills_chart.get("summary", {})

    per_task_comparison = []
    t_tasks = {r["task_id"]: r for r in traditional_chart.get("per_task", [])}
    o_tasks = {r["task_id"]: r for r in ontoskills_chart.get("per_task", [])}

    all_ids = sorted(set(t_tasks.keys()) | set(o_tasks.keys()))
    for tid in all_ids:
        t = t_tasks.get(tid, {})
        o = o_tasks.get(tid, {})
        per_task_comparison.append({
            "task_id": tid,
            "traditional_reward": t.get("reward", 0),
            "ontoskills_reward": o.get("reward", 0),
            "traditional_passed": t.get("passed", False),
            "ontoskills_passed": o.get("passed", False),
        })

    stats = _compute_statistics(t_summary, o_summary, per_task_comparison)

    return {
        "benchmark": traditional_chart.get("benchmark", ""),
        "model": traditional_chart.get("model", ""),
        "date": traditional_chart.get("date", ""),
        "traditional": t_summary,
        "ontoskills": o_summary,
        "statistics": stats,
        "delta": {
            "pass_rate": (o_summary.get("pass_rate", 0) - t_summary.get("pass_rate", 0)),
            "avg_reward": (o_summary.get("avg_reward", 0) - t_summary.get("avg_reward", 0)),
            "token_efficiency_pct": (
                ((t_summary.get("avg_input_tokens", 0) - o_summary.get("avg_input_tokens", 0))
                 / t_summary.get("avg_input_tokens", 1) * 100)
                if t_summary.get("avg_input_tokens", 0) > 0 else None
            ),
        },
        "per_task": per_task_comparison,
    }


def _compute_statistics(
    t_summary: dict,
    o_summary: dict,
    per_task: list[dict],
) -> dict:
    """Compute statistical measures for the comparison."""
    t_total = t_summary.get("total_tasks", 0)
    o_total = o_summary.get("total_tasks", 0)
    t_passed = t_summary.get("tasks_passed", 0)
    o_passed = o_summary.get("tasks_passed", 0)

    t_ci = _binomial_ci(t_passed, t_total)
    o_ci = _binomial_ci(o_passed, o_total)
    sig = _fisher_exact(t_passed, t_total, o_passed, o_total)

    # Classify: infra failure = both modes get reward 0
    skill_tasks = []
    infra_tasks = []
    for task in per_task:
        t_r = task.get("traditional_reward", 0)
        o_r = task.get("ontoskills_reward", 0)
        if t_r == 0 and o_r == 0:
            infra_tasks.append(task["task_id"])
        else:
            skill_tasks.append(task["task_id"])

    n_skill = len(skill_tasks)
    t_skill_passed = sum(
        1 for t in per_task
        if t["task_id"] in skill_tasks and t.get("traditional_passed", False)
    )
    o_skill_passed = sum(
        1 for t in per_task
        if t["task_id"] in skill_tasks and t.get("ontoskills_passed", False)
    )

    return {
        "traditional_ci": t_ci,
        "ontoskills_ci": o_ci,
        "significance": sig,
        "task_classification": {
            "skill_knowledge": skill_tasks,
            "infrastructure_failure": infra_tasks,
            "skill_only": {
                "n_tasks": n_skill,
                "traditional_pass_rate": round(t_skill_passed / n_skill, 4) if n_skill else 0,
                "ontoskills_pass_rate": round(o_skill_passed / n_skill, 4) if n_skill else 0,
                "traditional_ci": _binomial_ci(t_skill_passed, n_skill),
                "ontoskills_ci": _binomial_ci(o_skill_passed, n_skill),
                "significance": _fisher_exact(t_skill_passed, n_skill, o_skill_passed, n_skill),
            },
        },
    }


def save_chart_data(chart_data: dict, output_path: str) -> None:
    """Save chart data JSON to file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chart_data, indent=2, ensure_ascii=False), encoding="utf-8")
