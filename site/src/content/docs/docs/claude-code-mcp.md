---
title: MCP with Claude Code
description: Register and verify OntoMCP in Claude Code
sidebar:
  order: 11
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

## Register the server

Fastest bootstrap:

```bash
npx ontoskills install mcp --claude
```

Manual equivalent:

```bash
claude mcp add --scope user ontomcp -- \
  ~/.ontoskills/bin/ontomcp
```

Project-local instead:

```bash
npx ontoskills install mcp --claude --project
```

If you want to force a specific ontology root manually:

```bash
claude mcp add --scope user ontomcp -- \
  ~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

## Verify

```bash
claude mcp get ontomcp
claude mcp list
```

Expected state:

```text
Status: ✓ Connected
```

## What Claude Code can use

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

