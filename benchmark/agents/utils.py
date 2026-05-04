"""Shared utilities for benchmark agents."""

from __future__ import annotations

import re


def extract_python_code(response: str) -> str:
    """Extract the largest Python code block from response text.

    Handles both closed and unclosed (truncated) code blocks.
    Returns empty string when no code block is found.
    """
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", response, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip()

    # Fallback: unclosed code block (truncated response).
    m = re.search(r"```(?:python)?\s*\n(.*)", response, re.DOTALL)
    if m:
        return m.group(1).strip()

    return ""
