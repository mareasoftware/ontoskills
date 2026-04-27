"""Benchmark agents: base class, traditional, OntoSkills, and Claude Code."""

from .base import AgentResult, BaseAgent
from .claudecode import ClaudeCodeAgent
from .ontoskills import OntoSkillsAgent
from .traditional import TraditionalAgent

__all__ = [
    "AgentResult",
    "BaseAgent",
    "ClaudeCodeAgent",
    "OntoSkillsAgent",
    "TraditionalAgent",
]
