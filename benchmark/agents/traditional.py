"""Traditional (no-tools) agent for the OntoSkills benchmark.

Loads all ``SKILL.md`` files from a skills directory, concatenates them into
the system prompt, and makes a single Anthropic API call per task.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from benchmark.config import MODEL_PRICING

from .base import AgentResult, BaseAgent


def _load_skill_files(skills_dir: str) -> dict[str, str]:
    """Load all ``SKILL.md`` files under *skills_dir*.

    Expected directory layout::

        <skills_dir>/<vendor>/<package>/<skill>/SKILL.md

    Returns a mapping of ``"<vendor>/<package>/<skill>"`` -> file contents.
    """
    skills: dict[str, str] = {}
    root = Path(skills_dir)
    if not root.exists():
        return skills

    for skill_file in sorted(root.rglob("SKILL.md")):
        # Derive a readable key from the relative path, e.g.
        #   n8n-io/n8n/create-skill
        rel = skill_file.relative_to(root)
        key = str(rel.parent).replace(os.sep, "/")
        skills[key] = skill_file.read_text(encoding="utf-8")

    return skills


class TraditionalAgent(BaseAgent):
    """Agent that stuffs all skill docs into the system prompt (no tools)."""

    _CHARS_PER_TOKEN: int = 4  # rough heuristic

    def __init__(
        self,
        model: str,
        skills_dir: str,
        api_key: str | None = None,
    ) -> None:
        super().__init__(model=model, api_key=api_key)
        self.skills = _load_skill_files(skills_dir)
        self._context_overflow = False
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Concatenate all skill contents into one system prompt."""
        parts = ["You are an AI agent with access to the following skills:\n"]
        for name, content in self.skills.items():
            parts.append(f"--- {name} ---\n{content}\n")
        parts.append(
            "\nAnswer concisely based only on the skills documented above."
        )
        return "\n".join(parts)

    def get_system_prompt(self) -> str:
        """Return the (possibly truncated) system prompt."""
        return self._system_prompt

    # ------------------------------------------------------------------
    # Tools — none for the traditional agent
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict] | None:
        return None

    # ------------------------------------------------------------------
    # Context overflow detection / truncation
    # ------------------------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using the Anthropic SDK, with heuristic fallback."""
        try:
            return self.client.count_tokens(text)
        except Exception:
            # Fall back to the 4-char heuristic if the SDK call fails.
            return len(text) // self._CHARS_PER_TOKEN

    def _context_limit(self) -> int:
        """Return the context limit for the current model."""
        cfg = MODEL_PRICING.get(self.model)
        if cfg:
            return cfg["context_limit"]
        # Sensible default
        return 200_000

    def _check_and_truncate(self, messages: list[dict]) -> None:
        """Check if the conversation fits the context window.

        If not, set ``self._context_overflow = True`` and truncate the system
        prompt so the most recent conversation content is preserved.
        """
        limit = self._context_limit()
        reserved = self._RESERVED_OUTPUT_TOKENS

        system_tokens = self._estimate_tokens(self._system_prompt)
        msg_tokens = sum(
            self._estimate_tokens(
                m["content"]
                if isinstance(m.get("content"), str)
                else str(m.get("content", ""))
            )
            for m in messages
        )

        if system_tokens + msg_tokens + reserved <= limit:
            return

        self._context_overflow = True
        available = limit - msg_tokens - reserved
        if available <= 0:
            # Even with no system prompt the messages don't fit.
            self._system_prompt = "[System prompt truncated — context limit exceeded]"
            return

        # Truncate system prompt to fit, preserving the prefix (header).
        max_chars = available * self._CHARS_PER_TOKEN
        header_end = self._system_prompt.find("\n---")
        header = (
            self._system_prompt[:header_end]
            if header_end > 0
            else "You are an AI agent.\n"
        )
        budget = max_chars - len(header)
        if budget > 0:
            truncated_body = self._system_prompt[-budget:]
            self._system_prompt = (
                header
                + "\n[...truncated...]\n"
                + truncated_body
            )
        else:
            self._system_prompt = header + "\n[...truncated...]"

    # ------------------------------------------------------------------
    # Single-turn execution
    # ------------------------------------------------------------------

    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        """Make a single API call (no tool loop).

        Returns ``(assistant_message_dict, usage_metrics)``.
        """
        # Reset per-run state
        self._context_overflow = False
        self._system_prompt = self._build_system_prompt()

        # Check context limits before calling the API
        self._check_and_truncate(messages)

        start = time.perf_counter()
        response = self._call_api(messages)
        latency_ms = (time.perf_counter() - start) * 1000

        # Extract text content from the response
        text_parts = [
            block.text
            for block in response.content
            if block.type == "text"
        ]
        answer = "\n".join(text_parts)

        assistant_msg: dict = {
            "role": "assistant",
            "content": answer,
        }

        metrics: dict = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_ms": latency_ms,
            "tool_calls": 0,
        }

        return assistant_msg, metrics

    # ------------------------------------------------------------------
    # Override run() — single call, no tool-use loop
    # ------------------------------------------------------------------

    def run(self, task_prompt: str, max_turns: int = 10) -> AgentResult:
        """Execute a single API call. Ignores any tool_use blocks in response."""
        messages: list[dict] = [{"role": "user", "content": task_prompt}]
        assistant_msg, metrics = self.run_turn(messages)

        # Extract text content, ignoring any tool_use blocks the model
        # might have generated (TraditionalAgent cannot dispatch tools).
        content = assistant_msg.get("content", "")
        if isinstance(content, list):
            answer = "\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            answer = str(content)

        return AgentResult(
            answer=answer,
            input_tokens=metrics["input_tokens"],
            output_tokens=metrics["output_tokens"],
            total_latency_ms=metrics["latency_ms"],
            tool_calls=0,
            turns=1,
            context_overflow=self._context_overflow,
        )
