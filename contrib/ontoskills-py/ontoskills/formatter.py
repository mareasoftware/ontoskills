"""Context formatter — converts OntoSkills responses to LLM-friendly strings.

Agents don't want raw JSON from ontologies. This formatter produces
compact, high-signal context blocks optimized for LLM consumption.

Strategy:
    1. Extract only the most relevant knowledge nodes (score by recency × salience)
    2. Format dependencies and state requirements as concise tables
    3. Keep output under 800 tokens where possible
    4. Use structured markdown that LLMs parse efficiently
"""

from __future__ import annotations

from typing import Optional

from .types import ExecutionPlan, KnowledgeNode, SkillContext, SkillSearchResult


class ContextFormatter:
    """Formats OntoSkills data for LLM consumption.

    Usage:
        ctx = await client.get_context("pdf-generation")
        prompt_fragment = ContextFormatter.format_context(ctx)
        messages.append({"role": "system", "content": prompt_fragment})
    """

    # ── Main formatters ───────────────────────────────────────────────

    @staticmethod
    def format_context(ctx: SkillContext, max_nodes: int = 8) -> str:
        """Format a single skill's context as a compact system prompt block.

        Args:
            ctx: The skill context to format.
            max_nodes: Maximum knowledge nodes to include.

        Returns:
            A markdown string optimized for LLM ingestion.
        """
        lines = [f"## Skill: {ctx.name or ctx.skill_id}"]

        if ctx.intent:
            lines.append(f"**Intent**: {ctx.intent}")

        if ctx.description:
            lines.append(f"**Description**: {ctx.description}")

        # Dependencies
        if ctx.dependencies:
            deps = ", ".join(f"`{d}`" for d in ctx.dependencies)
            lines.append(f"**Dependencies**: {deps}")

        # State requirements
        if ctx.states_required:
            states = ", ".join(f"`{s}`" for s in ctx.states_required)
            lines.append(f"**Requires State**: {states}")

        if ctx.states_yielded:
            states = ", ".join(f"`{s}`" for s in ctx.states_yielded)
            lines.append(f"**Yields State**: {states}")

        # Knowledge nodes (most important first)
        if ctx.knowledge_nodes:
            lines.append("")
            lines.append("### Key Knowledge")
            for node in ctx.knowledge_nodes[:max_nodes]:
                severity_badge = ""
                if node.severity and node.severity.lower() != "none":
                    severity_badge = f" [{node.severity.upper()}]"

                content = node.content[:200]
                if len(node.content) > 200:
                    content += "..."

                category_prefix = f"[{node.category}] " if node.category else ""
                lines.append(f"- {category_prefix}{content}{severity_badge}")

        return "\n".join(lines)

    @staticmethod
    def format_search_results(results: list[SkillSearchResult]) -> str:
        """Format search results as a compact skill catalog.

        Args:
            results: List of search results from client.search().

        Returns:
            A markdown table of matching skills.
        """
        if not results:
            return "_No matching skills found._"

        lines = ["## Matching Skills", ""]
        for i, r in enumerate(results[:10], 1):
            score_bar = "█" * int(r.score * 10) if r.score > 0 else "—"
            desc = r.description[:120] + "..." if len(r.description) > 120 else r.description
            lines.append(f"{i}. **`{r.skill_id}`** {score_bar} ({r.score:.2f})")
            if desc:
                lines.append(f"   {desc}")
            if r.category:
                lines.append(f"   _Category: {r.category}_")

        return "\n".join(lines)

    @staticmethod
    def format_plan(plan: ExecutionPlan) -> str:
        """Format an execution plan as an ordered task list.

        Args:
            plan: ExecutionPlan from client.evaluate_plan().

        Returns:
            A markdown ordered list of skills to execute.
        """
        if not plan.skill_chain:
            return "_No execution path found._"

        lines = ["## Execution Plan", ""]
        for i, skill_id in enumerate(plan.skill_chain, 1):
            lines.append(f"{i}. Execute `{skill_id}`")

        if plan.notes:
            lines.append(f"\n**Notes**: {plan.notes}")

        if plan.estimated_tokens > 0:
            lines.append(f"_Estimated tokens: ~{plan.estimated_tokens}_")

        return "\n".join(lines)

    @staticmethod
    def format_multi_context(contexts: list[SkillContext], query: str = "") -> str:
        """Format multiple skill contexts for a single prompt.

        Useful when an agent needs context about several related skills.

        Args:
            contexts: List of skill contexts to combine.
            query: The original query that produced these contexts.

        Returns:
            A combined markdown string.
        """
        if not contexts:
            return "_No skill context available._"

        lines = []
        if query:
            lines.append(f"## Context for: \"{query}\"")

        for ctx in contexts:
            # Compact version — only essentials
            lines.append(f"### `{ctx.skill_id}`")
            if ctx.intent:
                lines.append(f"Intent: {ctx.intent}")
            if ctx.description:
                lines.append(ctx.description[:150])
            if ctx.dependencies:
                deps = ", ".join(f"`{d}`" for d in ctx.dependencies)
                lines.append(f"Deps: {deps}")
            lines.append("")

        return "\n".join(lines)
