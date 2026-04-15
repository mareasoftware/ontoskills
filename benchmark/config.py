"""Benchmark configuration: model pricing, context limits, task definitions."""

# Model pricing ($/MTok). Only Anthropic models are called.
# GPT and Gemini are price-comparison only — same token counts, different rates.
MODEL_PRICING = {
    "claude-opus-4-20250514": {
        "label": "Claude Opus 4.6",
        "provider": "anthropic",
        "input_per_mtok": 5.00,
        "output_per_mtok": 25.00,
        "context_limit": 200_000,
    },
    "claude-sonnet-4-20250514": {
        "label": "Claude Sonnet 4.6",
        "provider": "anthropic",
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "context_limit": 200_000,
    },
    "gpt-5.4": {
        "label": "GPT-5.4",
        "provider": "price_only",
        "input_per_mtok": 2.50,
        "output_per_mtok": 15.00,
        "context_limit": 128_000,
    },
    "gpt-5.4-mini": {
        "label": "GPT-5.4 mini",
        "provider": "price_only",
        "input_per_mtok": 0.75,
        "output_per_mtok": 4.50,
        "context_limit": 128_000,
    },
    "gemini-3.1-pro": {
        "label": "Gemini 3.1 Pro",
        "provider": "price_only",
        # Tiered: ≤200K tokens = lower price, >200K = higher price
        "input_per_mtok_le200k": 2.00,
        "output_per_mtok_le200k": 12.00,
        "input_per_mtok_gt200k": 4.00,
        "output_per_mtok_gt200k": 18.00,
        "context_limit": 1_000_000,
    },
    "gemini-3.1-flash": {
        "label": "Gemini 3.1 Flash",
        "provider": "price_only",
        "input_per_mtok": 0.75,
        "output_per_mtok": 4.50,
        "context_limit": 1_000_000,
    },
}


def get_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD for a given model and token usage."""
    pricing = MODEL_PRICING[model_id]

    if "input_per_mtok_le200k" in pricing:
        # Gemini 3.1 Pro tiered pricing
        if input_tokens <= 200_000:
            in_price = pricing["input_per_mtok_le200k"]
            out_price = pricing["output_per_mtok_le200k"]
        else:
            in_price = pricing["input_per_mtok_gt200k"]
            out_price = pricing["output_per_mtok_gt200k"]
    else:
        in_price = pricing["input_per_mtok"]
        out_price = pricing["output_per_mtok"]

    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


# Anthropic models to actually call (others are price comparison only)
ANTHROPIC_MODELS = [
    mid for mid, cfg in MODEL_PRICING.items() if cfg["provider"] == "anthropic"
]

# Traditional benchmark tasks — each maps to an OntoMCP query
TASKS = [
    {
        "name": "skill_discovery",
        "question": "Which skills can create a PDF document? List only the skill names.",
        "ontomcp_query": "search (by intent)",
    },
    {
        "name": "context_retrieval",
        "question": "What are the preconditions and steps for the pdf-generator skill?",
        "ontomcp_query": "get_skill_context",
    },
    {
        "name": "execution_planning",
        "question": "I need to create a PDF. My current state is: template_loaded. Which skill should I use and what are the steps?",
        "ontomcp_query": "evaluate_execution_plan",
    },
    {
        "name": "dependency_check",
        "question": "Does any skill depend on the output of another skill? List all dependencies you find.",
        "ontomcp_query": "search (all — scan)",
    },
]
