from __future__ import annotations

from .base import AgentEngine, EngineOutput
from .claude import ClaudeEngine
from .opencode import OpencodeEngine


def create_engine(name: str = "claude") -> AgentEngine:
    engines = {
        "claude": ClaudeEngine(),
        "opencode": OpencodeEngine(),
    }
    engine = engines.get(name)
    if engine is None:
        raise ValueError(f"Unknown engine: {name}. Choose from: {', '.join(engines)}")
    return engine


__all__ = ["AgentEngine", "EngineOutput", "ClaudeEngine", "OpencodeEngine", "create_engine"]
