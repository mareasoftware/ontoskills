"""Type definitions for OntoSkills client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillSearchResult:
    """A skill found via semantic/BM25 search."""

    skill_id: str
    name: str = ""
    description: str = ""
    intent: str = ""
    score: float = 0.0
    category: str = ""

    @classmethod
    def from_search(cls, data: dict) -> SkillSearchResult:
        return cls(
            skill_id=data.get("skill_id", data.get("skill", "")),
            name=data.get("name", data.get("skill", "")),
            description=data.get("description", ""),
            intent=data.get("intent", ""),
            score=float(data.get("score", data.get("relevance", 0.0))),
            category=data.get("category", ""),
        )


@dataclass
class KnowledgeNode:
    """A single knowledge node from a skill's ontology."""

    node_id: str
    content: str
    category: str = ""
    severity: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeNode:
        return cls(
            node_id=data.get("id", ""),
            content=data.get("content", data.get("text", "")),
            category=data.get("category", ""),
            severity=data.get("severity", ""),
        )


@dataclass
class SkillContext:
    """Full context for a skill, including knowledge nodes and dependencies."""

    skill_id: str
    name: str = ""
    description: str = ""
    intent: str = ""
    knowledge_nodes: list[KnowledgeNode] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    states_required: list[str] = field(default_factory=list)
    states_yielded: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(cls, data: dict) -> SkillContext:
        nodes = [
            KnowledgeNode.from_dict(n)
            for n in data.get("knowledge_nodes", data.get("knowledgeNodes", []))
        ]
        return cls(
            skill_id=data.get("skill_id", data.get("skillId", "")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            intent=data.get("intent", ""),
            knowledge_nodes=nodes,
            dependencies=data.get("dependencies", data.get("dependsOn", [])),
            extensions=data.get("extensions", data.get("extends", [])),
            states_required=data.get("states_required", data.get("requiresState", [])),
            states_yielded=data.get("states_yielded", data.get("yieldsState", [])),
            raw=data,
        )


@dataclass
class ExecutionPlan:
    """A plan showing which skills to execute and in what order."""

    skill_chain: list[str] = field(default_factory=list)
    total_steps: int = 0
    estimated_tokens: int = 0
    notes: str = ""

    @classmethod
    def from_response(cls, data: dict) -> ExecutionPlan:
        return cls(
            skill_chain=data.get("chain", data.get("skill_chain", [])),
            total_steps=data.get("total_steps", data.get("totalSteps", len(data.get("chain", [])))),
            estimated_tokens=data.get("estimated_tokens", data.get("estimatedTokens", 0)),
            notes=data.get("notes", ""),
        )
