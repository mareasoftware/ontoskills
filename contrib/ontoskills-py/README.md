# ontoskills-py

**Python client for OntoSkills — deterministic skill ontologies for AI agents.**

```
pip install ontoskills-py
```

## Why?

LLMs read skills probabilistically — same query, different results. Skill files burn tokens and confuse smaller models.

OntoSkills compiles SKILL.md → OWL 2 ontologies. This client queries those ontologies with SPARQL. Exact answers, every time.

## Quick Start

```python
import asyncio
from ontoskills import OntoSkillsClient
from ontoskills.formatter import ContextFormatter

async def main():
    client = OntoSkillsClient()
    await client.start()

    # Search for skills
    results = await client.search("how to parse PDF files")
    print(ContextFormatter.format_search_results(results))

    # Get full context for a specific skill
    ctx = await client.get_context("pdf-generation")
    system_prompt = ContextFormatter.format_context(ctx)
    # Inject system_prompt into your agent's context

    await client.stop()

asyncio.run(main())
```

## Integration with Agent Frameworks

### Wisp

```python
# In your wisp skill loader
from ontoskills import OntoSkillsClient
from ontoskills.formatter import ContextFormatter

class OntologySkillLoader:
    def __init__(self):
        self.client = OntoSkillsClient()

    async def load(self, query: str) -> str:
        await self.client.start()
        results = await self.client.search(query)
        if results:
            ctx = await self.client.get_context(results[0].skill_id)
            return ContextFormatter.format_context(ctx)
        return ""
```

### Claude Code / Hermes / Custom Agents

```python
# As an MCP server bridge
# Query ontologies, get deterministic results, feed to agent
client = OntoSkillsClient()
plan = await client.evaluate_plan(intent="deploy_to_production")
prompt = ContextFormatter.format_plan(plan)
```

## API Reference

### `OntoSkillsClient`

| Method | Returns | Description |
|--------|---------|-------------|
| `search(query, top_k=5)` | `list[SkillSearchResult]` | Search skills by query or skill ID |
| `get_context(skill_id)` | `SkillContext` | Full ontology context for a skill |
| `evaluate_plan(intent, ...)` | `ExecutionPlan` | Ordered chain of skills to execute |
| `prefetch_knowledge(query, ...)` | `list[SkillContext]` | Batch fetch + compact context |

### `ContextFormatter`

| Method | Description |
|--------|-------------|
| `format_context(ctx)` | Single skill → LLM system prompt block |
| `format_search_results(results)` | Search results → markdown catalog |
| `format_plan(plan)` | Execution plan → ordered task list |
| `format_multi_context(ctxs)` | Multiple skills → combined context |

## Requirements

- Python 3.10+
- `ontomcp` binary (build with `cd mcp && cargo build --release`)
- Compiled ontology directory (from `ontocore compile`)

## Building ontomcp

```bash
git clone https://github.com/mareasw/ontoskills.git
cd ontoskills/mcp
cargo build --release
# Binary at: target/release/ontomcp
```

## License

MIT
