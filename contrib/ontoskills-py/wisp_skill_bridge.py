#!/usr/bin/env python3
"""
Wisp ↔ OntoSkills Bridge — deterministic skill resolution for wisp agents.

Instead of wisp agents reading raw SKILL.md files and hoping the LLM
interprets them correctly, this bridge:
1. Compiles wisp skills into OntoSkills ontologies (via ontocore)
2. Queries ontologies at runtime for exact skill selection
3. Formats results as wisp-compatible context blocks

Usage (in wisp agent code):
    from wisp_skill_bridge import OntologySkillProvider
    provider = OntologySkillProvider(skills_dir="./skills")
    context = await provider.resolve("create terraform VPC")
    # → Deterministic skill context, not probabilistic text parsing
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional


class OntologySkillProvider:
    """Deterministic skill resolution via OntoSkills ontologies.

    Replaces or augments wisp's SkillRegistry with ontology-backed queries.

    Flow:
        Agent query → SPARQL search → exact skill match → formatted context
    """

    def __init__(
        self,
        skills_dir: str = "./skills",
        ontology_dir: str = "./ontoskills-ontologies",
        ontomcp_binary: str = "ontomcp",
    ):
        self.skills_dir = Path(skills_dir)
        self.ontology_dir = Path(ontology_dir)
        self.ontomcp_binary = ontomcp_binary
        self._client = None

    async def _get_client(self):
        """Lazy-init the OntoSkills client."""
        if self._client is None:
            from ontoskills import OntoSkillsClient
            self._client = OntoSkillsClient(
                binary_path=self.ontomcp_binary,
                ontology_root=str(self.ontology_dir),
            )
            await self._client.start()
        return self._client

    # ── Compilation ───────────────────────────────────────────────────

    def compile_skills(self) -> subprocess.CompletedProcess:
        """Compile all wisp SKILL.md files into an OntoSkills ontology.

        Runs `ontocore compile` against the skills directory.
        Output goes to `ontology_dir/`.
        """
        self.ontology_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["ontocore", "compile", "--skills-dir", str(self.skills_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result

    # ── Runtime resolution ────────────────────────────────────────────

    async def resolve(self, query: str, top_k: int = 3) -> str:
        """Resolve a natural language query to a skill context block.

        This is the main entry point for wisp agents. Instead of:
            skill_registry.match_for_task(query)
        Use:
            provider.resolve(query)

        Args:
            query: Natural language task description.
            top_k: Max skills to include in context.

        Returns:
            Compact markdown context block ready for agent consumption.
        """
        from ontoskills.formatter import ContextFormatter

        client = await self._get_client()

        # Search for matching skills
        results = await client.search(query, top_k=top_k)

        if not results:
            return f"_No ontology skills matched: {query}_"

        # Get full contexts for top matches
        contexts = []
        for r in results[:top_k]:
            try:
                ctx = await client.get_context(r.skill_id, include_inherited=True)
                contexts.append(ctx)
            except Exception:
                continue

        if not contexts:
            return ContextFormatter.format_search_results(results)

        return ContextFormatter.format_multi_context(contexts, query)

    async def resolve_exact(self, skill_id: str) -> str:
        """Get the exact context for a known skill ID.

        Args:
            skill_id: The ontology skill identifier.

        Returns:
            Formatted context block or error message.
        """
        from ontoskills.formatter import ContextFormatter

        client = await self._get_client()
        try:
            ctx = await client.get_context(skill_id)
            return ContextFormatter.format_context(ctx)
        except Exception as e:
            return f"_Skill not found: {skill_id} ({e})_"

    async def get_execution_path(self, intent: str) -> str:
        """Get the ordered execution path to achieve an intent.

        Args:
            intent: The desired outcome (e.g. "deploy_to_aws").

        Returns:
            Formatted plan or "no path found" message.
        """
        from ontoskills.formatter import ContextFormatter

        client = await self._get_client()
        plan = await client.evaluate_plan(intent=intent)
        return ContextFormatter.format_plan(plan)

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def close(self):
        """Close the OntoSkills client connection."""
        if self._client:
            await self._client.stop()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Wisp integration function ─────────────────────────────────────────

async def enhance_wisp_with_ontology(wisp_skills_dir: str = "./skills") -> OntologySkillProvider:
    """One-call setup for enhancing a wisp agent with ontology-backed skills.

    Usage in wisp agent initialization:
        from wisp_skill_bridge import enhance_wisp_with_ontology
        provider = await enhance_wisp_with_ontology("./skills")
        # Now use provider.resolve() instead of skill_registry.match_for_task()
    """
    provider = OntologySkillProvider(skills_dir=wisp_skills_dir)

    # Compile if ontology doesn't exist yet
    if not provider.ontology_dir.exists() or not list(provider.ontology_dir.glob("*.ttl")):
        print("[OntoSkills] Compiling skills to ontology...")
        result = provider.compile_skills()
        if result.returncode != 0:
            print(f"[OntoSkills] Compilation warning: {result.stderr[:200]}")
        else:
            print(f"[OntoSkills] Compiled {len(list(provider.ontology_dir.glob('*.ttl')))} ontologies")

    return provider


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python wisp_skill_bridge.py <query>")
            print("  e.g.: python wisp_skill_bridge.py 'create terraform VPC'")
            sys.exit(1)

        query = " ".join(sys.argv[1:])
        provider = await enhance_wisp_with_ontology()

        print(f"\n🔍 Query: {query}\n")
        result = await provider.resolve(query)
        print(result)

        await provider.close()

    asyncio.run(main())
