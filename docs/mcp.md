---
title: MCP Runtime
description: General OntoMCP runtime guide and installation flow
---

# OntoMCP

`OntoMCP` is the runtime layer of OntoSkills. It loads compiled ontologies from your managed local home and exposes them through the Model Context Protocol over `stdio`.

The standard product install is:

```bash
npx ontoskills install mcp
```

This installs the runtime binary at:

```text
~/.ontoskills/bin/ontomcp
```

## What OntoMCP Loads

Preferred runtime source:

- `~/.ontoskills/ontoskills/index.enabled.ttl`

Fallbacks:

- `~/.ontoskills/ontoskills/ontoskills-core.ttl`
- `index.ttl`
- `*/ontoskill.ttl`

You can override the ontology root with:

```bash
ONTOSKILLS_MCP_ONTOLOGY_ROOT=/path/to/ontoskills
```

or:

```bash
~/.ontoskills/bin/ontomcp --ontology-root /path/to/ontoskills
```

## Tool Surface

The current public MCP tools are:

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

The server does not execute payloads. It returns structured context, planning output, and epistemic rules. Execution remains the responsibility of the calling client or agent.

## Local Development

From the repository root:

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

Run tests:

```bash
cargo test --manifest-path mcp/Cargo.toml
```

## Client Guides

- [Claude Code](./mcp-claude-code.md)
- [Codex](./mcp-codex.md)

