---
title: MCP With Claude Code
description: Register and verify OntoMCP in Claude Code
---

## Install

Install the runtime first:

```bash
npx ontoskills install mcp
```

This gives you the managed runtime binary:

```text
~/.ontoskills/bin/ontomcp
```

## Register The Server

Recommended command:

```bash
claude mcp add --scope local ontoskills \
  ~/.ontoskills/bin/ontomcp
```

If you want to force a specific ontology root:

```bash
claude mcp add --scope local ontoskills \
  ~/.ontoskills/bin/ontomcp \
  -- --ontology-root ~/.ontoskills/ontologies
```

## Verify

```bash
claude mcp get ontoskills
claude mcp list
```

Expected state:

```text
Status: ✓ Connected
```

## What Claude Code Can Use

Once connected, Claude Code can call:

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

## Troubleshooting

### Connection fails

Check:

- `~/.ontoskills/bin/ontomcp` exists
- `~/.ontoskills/ontologies/` exists
- `index.enabled.ttl` or compiled `.ttl` files exist

### Ontology not found

Run with an explicit root:

```bash
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

### Rebuilt binary but Claude still behaves strangely

Remove and re-add the MCP server, or restart Claude Code. A stale background process can keep the old binary alive.

