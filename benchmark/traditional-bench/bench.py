"""Benchmark the traditional LLM approach to skill discovery.

Calls only the Anthropic API. GPT/Gemini models are price-comparison only
(computed from the same token counts using their pricing).
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import anthropic

# Add parent dir to path so we can import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    ANTHROPIC_MODELS,
    MODEL_PRICING,
    TASKS,
    get_cost_usd,
)


def load_skill_files(skills_dir: str) -> dict[str, str]:
    """Load all .md skill files from directory."""
    skills = {}
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        print(f"Skills directory not found: {skills_dir}")
        sys.exit(1)

    for f in sorted(skills_path.glob("*.md")):
        skills[f.stem] = f.read_text(encoding="utf-8")

    return skills


def build_prompt(skills: dict[str, str], question: str) -> str:
    """Build the prompt that simulates an agent reading skill files."""
    parts = ["You are an AI agent with access to the following skills:\n"]
    for name, content in skills.items():
        parts.append(f"--- {name} ---\n{content}\n")
    parts.append(f"\nQuestion: {question}")
    parts.append("\nAnswer concisely based only on the skills above.")
    return "\n".join(parts)


def run_task(
    client: anthropic.Anthropic,
    model_id: str,
    skills: dict[str, str],
    task: dict,
    runs: int,
) -> dict:
    """Run a single benchmark task multiple times on one Anthropic model."""
    question = task["question"]
    prompt = build_prompt(skills, question)
    pricing = MODEL_PRICING[model_id]
    context_limit = pricing["context_limit"]
    prompt_chars = len(prompt)

    # Use the Anthropic SDK's exact token counter — not an estimate
    token_count_response = client.count_tokens(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
    )
    prompt_tokens = token_count_response.input_tokens

    print(f"\n  Task: {task['name']} | Model: {model_id}")
    print(f"  Prompt: {prompt_chars:,} chars | {prompt_tokens:,} tokens (exact)")
    print(f"  Context limit: {context_limit:,} tokens")

    # Check for context overflow before making any API calls.
    # Must account for reserved output tokens (matches max_tokens in the API call).
    reserved_output_tokens = 1024
    if prompt_tokens + reserved_output_tokens > context_limit:
        print(
            f"  STATUS: OVERFLOW — prompt ({prompt_tokens:,}) + "
            f"output ({reserved_output_tokens:,}) > limit ({context_limit:,})"
        )
        return {
            "task_name": task["name"],
            "question": question,
            "ontomcp_query": task["ontomcp_query"],
            "status": "context_overflow",
            "prompt_chars": prompt_chars,
            "prompt_tokens": prompt_tokens,
            "context_limit": context_limit,
            "skill_count": len(skills),
            "runs": 0,
            "latency": None,
            "tokens": None,
            "cost": None,
            "determinism": None,
        }

    latencies = []
    input_tokens_list = []
    output_tokens_list = []
    answers = []

    for i in range(runs):
        # Retry with exponential backoff on rate limits
        max_retries = 5
        response = None
        for attempt in range(max_retries):
            try:
                start = time.perf_counter()
                response = client.messages.create(
                    model=model_id,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                elapsed = time.perf_counter() - start
                break
            except anthropic.RateLimitError:
                wait = 2 ** attempt
                print(f"    Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
        else:
            print(f"    FAILED: rate limit exceeded after {max_retries} retries")
            continue

        if response is None:
            continue

        answer = response.content[0].text
        usage = response.usage

        latencies.append(elapsed)
        input_tokens_list.append(usage.input_tokens)
        output_tokens_list.append(usage.output_tokens)
        answers.append(answer.lower().strip())

        if (i + 1) % 5 == 0 or i == 0:
            print(
                f"    run {i+1:3d}/{runs}: "
                f"{elapsed:.2f}s, "
                f"{usage.input_tokens:,} in + {usage.output_tokens:,} out tokens"
            )

    if not latencies:
        return {
            "task_name": task["name"],
            "question": question,
            "ontomcp_query": task["ontomcp_query"],
            "status": "all_rate_limited",
            "prompt_chars": prompt_chars,
            "prompt_tokens": prompt_tokens,
            "context_limit": context_limit,
            "skill_count": len(skills),
            "runs": 0,
            "latency": None,
            "tokens": None,
            "cost": None,
            "determinism": None,
        }

    # Stats
    successful_runs = len(latencies)
    avg_input = round(sum(input_tokens_list) / successful_runs)
    avg_output = round(sum(output_tokens_list) / successful_runs)
    total_input = sum(input_tokens_list)
    total_output = sum(output_tokens_list)

    # Determinism
    unique_answers = len(set(answers))
    most_common_count = Counter(answers).most_common(1)[0][1]

    # Cost for ALL models (not just this one)
    costs = {}
    for mid in MODEL_PRICING:
        per_run = get_cost_usd(mid, avg_input, avg_output)
        costs[mid] = {
            "per_run_usd": per_run,
            "total_usd": per_run * successful_runs,
        }

    result = {
        "task_name": task["name"],
        "question": question,
        "ontomcp_query": task["ontomcp_query"],
        "status": "ok",
        "prompt_chars": prompt_chars,
        "prompt_tokens": prompt_tokens,
        "skill_count": len(skills),
        "runs": successful_runs,
        "latency": {
            "avg_s": round(sum(latencies) / successful_runs, 4),
            "min_s": round(min(latencies), 4),
            "max_s": round(max(latencies), 4),
            "p50_s": round(sorted(latencies)[successful_runs // 2], 4),
            "p99_s": round(sorted(latencies)[int(successful_runs * 0.99)], 4),
        },
        "tokens": {
            "input_avg": avg_input,
            "output_avg": avg_output,
            "input_total": total_input,
            "output_total": total_output,
        },
        "cost": costs,
        "determinism": {
            "unique_answers": unique_answers,
            "total_runs": successful_runs,
            "consistency_pct": round(most_common_count / successful_runs * 100, 1),
        },
    }

    print(f"\n  Summary:")
    print(f"    Avg latency: {result['latency']['avg_s']:.2f}s")
    print(f"    Tokens: {avg_input:,} in + {avg_output:,} out")
    print(f"    Cost (this model): ${costs[model_id]['per_run_usd']:.4f}/run")
    print(f"    Determinism: {result['determinism']['consistency_pct']}% ({unique_answers} unique)")

    return result


def main():
    skills_dir = sys.argv[1] if len(sys.argv) > 1 else "../skills"
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    output_path = sys.argv[3] if len(sys.argv) > 3 else "../results/traditional-bench.json"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: Set ANTHROPIC_API_KEY to run the traditional benchmark")
        print("  Or run via benchmark/run.py with --ontomcp-only to skip this benchmark.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    skills = load_skill_files(skills_dir)
    if not skills:
        print("No skill files found in", skills_dir)
        sys.exit(1)

    print("=== Traditional LLM Skill Benchmark ===")
    print(f"Skills: {len(skills)}")
    print(f"Runs per task: {runs}")
    print(f"Anthropic models: {', '.join(ANTHROPIC_MODELS)}")

    models_results = []
    for model_id in ANTHROPIC_MODELS:
        print(f"\n{'='*60}")
        print(f"Model: {MODEL_PRICING[model_id]['label']} ({model_id})")
        print(f"{'='*60}")

        tasks_results = []
        for task in TASKS:
            result = run_task(client, model_id, skills, task, runs)
            tasks_results.append(result)

        models_results.append({
            "model": model_id,
            "label": MODEL_PRICING[model_id]["label"],
            "skill_count": len(skills),
            "runs_per_task": runs,
            "tasks": tasks_results,
        })

    report = {"models": models_results}

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
