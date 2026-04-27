"""Abstract base agent for the OntoSkills benchmark.

Provides the shared run-loop, Anthropic API helper, and result dataclass.
Subclasses implement ``get_system_prompt``, ``get_tools``, and ``run_turn``.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Aggregate result returned by ``BaseAgent.run``."""

    answer: str
    input_tokens: int
    output_tokens: int
    total_latency_ms: float
    tool_calls: int
    turns: int
    context_overflow: bool


class BaseAgent(ABC):
    """Abstract base for all benchmark agents.

    Subclasses must implement:
    - ``get_system_prompt()`` — return the system prompt string
    - ``get_tools()``        — return tool schemas (or ``None``)
    - ``run_turn()``         — execute one turn and return (message, metrics)
    """

    # Anthropic reserves tokens for the response; keep a safety margin.
    _RESERVED_OUTPUT_TOKENS: int = 8192

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "An Anthropic API key is required. "
                "Pass api_key= or set ANTHROPIC_API_KEY."
            )
        import httpx
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            timeout=httpx.Timeout(300.0, connect=30.0),
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""

    @abstractmethod
    def get_tools(self) -> list[dict] | None:
        """Return tool schemas for this agent (``None`` if no tools)."""

    @abstractmethod
    def run_turn(self, messages: list[dict]) -> tuple[dict, dict]:
        """Execute a single turn.

        Parameters
        ----------
        messages:
            Conversation history so far (list of role/content dicts).

        Returns
        -------
        tuple[dict, dict]
            ``(assistant_message, usage_metrics)`` where *usage_metrics* is::

                {
                    "input_tokens": int,
                    "output_tokens": int,
                    "latency_ms": float,
                    "tool_calls": int,
                }
        """

    # ------------------------------------------------------------------
    # Shared API helper
    # ------------------------------------------------------------------

    def _call_api(self, messages: list[dict]) -> anthropic.types.Message:
        """Call the Anthropic Messages API with system prompt + tools.

        Retries on ``RateLimitError`` and server errors (5xx) with
        exponential back-off (up to 5 attempts).
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self._RESERVED_OUTPUT_TOKENS,
            "system": self.get_system_prompt(),
            "messages": messages,
            "temperature": 0.0,
        }
        tools = self.get_tools()
        if tools is not None and len(tools) > 0:
            kwargs["tools"] = tools

        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(**kwargs)
                if getattr(response, "stop_reason", None) == "max_tokens":
                    logger.warning(
                        "API response truncated (stop_reason='max_tokens'). "
                        "Consider increasing _RESERVED_OUTPUT_TOKENS."
                    )
                return response
            except anthropic.RateLimitError:
                wait = 2**attempt
                logger.warning(
                    "Rate limited (attempt %d/%d), waiting %ds...",
                    attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500 and attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        "Server error %d (attempt %d/%d), retrying in %ds...",
                        exc.status_code, attempt + 1, max_retries, wait,
                    )
                    time.sleep(wait)
                else:
                    raise
            except anthropic.APIConnectionError:
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        "Connection error (attempt %d/%d), retrying in %ds...",
                        attempt + 1, max_retries, wait,
                    )
                    time.sleep(wait)
                else:
                    raise

        raise anthropic.RateLimitError("Exceeded max retries on rate limit")

    # ------------------------------------------------------------------
    # Main run-loop
    # ------------------------------------------------------------------

    def run(self, task_prompt: str, max_turns: int = 10) -> AgentResult:
        """Execute the full agent loop for a single task.

        Starts with the user message, calls ``run_turn`` until there are no
        more tool-use blocks or ``max_turns`` is reached, then returns an
        ``AgentResult`` with aggregated metrics.
        """
        messages: list[dict] = [{"role": "user", "content": task_prompt}]

        total_input = 0
        total_output = 0
        total_latency_ms = 0.0
        total_tool_calls = 0
        context_overflow = False
        turns = 0

        for _ in range(max_turns):
            assistant_msg, metrics = self.run_turn(messages)
            turns += 1

            total_input += metrics["input_tokens"]
            total_output += metrics["output_tokens"]
            total_latency_ms += metrics["latency_ms"]
            total_tool_calls += metrics["tool_calls"]

            messages.append(assistant_msg)

            # Check for tool-use blocks that require another turn.
            tool_use_blocks = [
                b for b in (assistant_msg.get("content") or [])
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]

            if not tool_use_blocks:
                break

            # Validate that the subclass has appended corresponding
            # tool_result messages during ``run_turn``.
            tool_ids = {b["id"] for b in tool_use_blocks}
            last_msg = messages[-1] if messages else {}
            result_ids: set[str] = set()
            if isinstance(last_msg.get("content"), list):
                result_ids = {
                    b.get("tool_use_id", "")
                    for b in last_msg["content"]
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                }
            missing = tool_ids - result_ids
            if missing:
                raise RuntimeError(
                    f"run_turn() returned tool_use blocks but the last message "
                    f"in *messages* does not contain matching tool_result blocks. "
                    f"Missing tool_result for ids: {missing}. "
                    f"Subclasses must append tool_result messages during run_turn()."
                )

            # If there are tool calls, subclasses are expected to have already
            # appended tool_result messages during their ``run_turn``.  The
            # base implementation does not handle tool execution — that is the
            # responsibility of tool-capable agents.

        # Extract the final text answer from the last assistant message.
        answer = ""
        for block in reversed(messages):
            if isinstance(block, dict) and block.get("role") == "assistant":
                content = block.get("content", "")
                if isinstance(content, str):
                    answer = content
                elif isinstance(content, list):
                    # Collect text blocks
                    texts = [
                        b["text"]
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    answer = "\n".join(texts)
                break

        return AgentResult(
            answer=answer,
            input_tokens=total_input,
            output_tokens=total_output,
            total_latency_ms=total_latency_ms,
            tool_calls=total_tool_calls,
            turns=turns,
            context_overflow=context_overflow,
        )
