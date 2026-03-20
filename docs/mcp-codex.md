---
title: MCP With Codex
description: Configure OntoMCP for Codex-based local workflows
---

# OntoMCP With Codex

## Install

Install the runtime first:

```bash
npx ontoskills install mcp
```

This installs:

```text
~/.ontoskills/bin/ontomcp
```

## Integration Model

Codex-based workflows use the same MCP contract as other local clients:

- launch `ontomcp` as a local `stdio` subprocess
- point it at the managed ontology home in `~/.ontoskills/ontoskills`
- let the client call the four public tools

The stable executable to register is:

```text
~/.ontoskills/bin/ontomcp
```

## Recommended Runtime Command

```bash
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontoskills
```

If your Codex client supports environment-based configuration, the equivalent setting is:

```bash
ONTOSKILLS_MCP_ONTOLOGY_ROOT=~/.ontoskills/ontoskills
```

## Tools Exposed

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

## Notes

- The MCP server reads compiled `.ttl` ontologies, not raw `SKILL.md`
- If you want custom skills, install the compiler too:

```bash
npx ontoskills install core
```

- Then compile or import source skills and enable them before expecting Codex to see them through OntoMCP

## Practical Rule

Treat Codex integration as a standard local `stdio` MCP registration whose command points at:

```text
~/.ontoskills/bin/ontomcp
```

The exact UI or config file shape may vary across Codex builds, but the server command and ontology root remain the same.

