"""ontoskills — Python client for deterministic agent skill ontologies.

OntoSkills compiles human-written SKILL.md files into OWL 2 ontologies,
making skills queryable via SPARQL instead of readable by LLMs. This
client connects to the OntoMCP server and provides agent-friendly APIs.

Usage:
    from ontoskills import OntoSkillsClient

    client = OntoSkillsClient()
    skills = await client.search("pdf generation")
    context = await client.get_context("pdf-generation")
"""

from __future__ import annotations

from .client import OntoSkillsClient
from .types import SkillContext, SkillSearchResult, ExecutionPlan

__all__ = ["OntoSkillsClient", "SkillContext", "SkillSearchResult", "ExecutionPlan"]
__version__ = "0.1.0"
