---
title: MCP Runtime
description: OntoMCP runtime guide and tool reference
sidebar:
  order: 6
---

`OntoMCP` is the runtime layer of OntoSkills. It loads compiled ontologies from your managed local home and exposes them through the Model Context Protocol over `stdio`.

---

## Installation

```bash
npx ontoskills install mcp
npx ontoskills install mcp --claude
npx ontoskills install mcp --cursor --project
```

This installs the runtime binary at:

```text
~/.ontoskills/bin/ontomcp
```

For one-command client bootstrap, see [MCP Bootstrap](/docs/mcp-bootstrap/).

---

## What OntoMCP loads

**Primary source:**

```text
~/.ontoskills/ontologies/system/index.enabled.ttl
```

**Fallbacks (in order):**

1. `~/.ontoskills/ontologies/index.ttl`
2. `index.ttl` in current directory
3. `*/ontoskill.ttl` patterns

**Override the ontology root:**

```bash
# Environment variable
ONTOMCP_ONTOLOGY_ROOT=~/.ontoskills/ontologies

# Or command-line flag
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

---

## Tool reference

OntoMCP exposes **1 unified tool** `mcp__onto__skill` that combines skill discovery, context retrieval, and knowledge querying.

> **Sparse serialization**: null values and empty arrays are omitted from responses. Only fields with actual values are included. This keeps responses compact and avoids cluttering the context window with empty data.

### `mcp__onto__skill`

Find skills by name or natural language query, then load their full context — all in a single call.

```json
{
  "q": "create a pdf document",
  "top_k": 5
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | **Required.** Skill ID (e.g. `pdf`) or natural language query (e.g. `create a pdf document`) |
| `top_k` | integer | Max search results when the query doesn't match a skill ID (default 5) |

**When `q` matches a known skill ID** → returns the full skill context: payload, dependencies, knowledge nodes, code examples, and reference tables.

**When `q` doesn't match a skill ID** → falls back to search mode using **BM25** keyword ranking (always available). For large catalogs compiled with `--features embeddings`, semantic fallback is used when BM25 confidence is low:

```json
{
  "mode": "bm25",
  "query": "create a pdf document",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "trust_tier": "core",
      "score": 0.92,
      "matched_by": "intent",
      "intents": ["create_pdf", "export_to_pdf"]
    }
  ]
}
```

### Agent workflow

The `mcp__onto__skill` tool replaces the old multi-step workflow:

```
Before (4 tools):
  search → get_skill_context → evaluate_execution_plan → query_epistemic_rules

After (1 tool):
  mcp__onto__skill(q) → returns context or search results
```

1. Agent receives a user request
2. Calls `mcp__onto__skill(q: user request)` — if the query is a skill ID, returns full context immediately; otherwise returns BM20-ranked search results
3. Agent now has everything needed — payload, dependencies, knowledge nodes, code examples — in a single response

No round-trips between search and context retrieval. No separate tools for plan validation or epistemic queries — all knowledge is embedded in the skill context.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AI Client                             │
│                   (Claude Code, Codex)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │ MCP Protocol (stdio)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       OntoMCP                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Catalog   │  │ BM25 Engine │  │   SPARQL Engine     │  │
│  │   (Rust)    │  │  (in-memory)│  │   (Oxigraph)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         └─────────┐      │                    │             │
│                   ▼      │                    │             │
│          ┌─────────────┐ │                    │             │
│          │  Embeddings │ │                    │             │
│          │(ONNX/Intents│ │                    │             │
│          │  optional,  │ │                    │             │
│          │large catalogs│ │                   │             │
│          └─────────────┘ │                    │             │
└─────────────────────────┼────────────────────┼─────────────┘
                          │                    │
                          ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    ontologies/                               │
│  ├── index.ttl                                              │
│  ├── system/                                                │
│  │   ├── index.enabled.ttl                                  │
│  │   └── embeddings/                                        │
│  └── */ontoskill.ttl                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Local development

From the repository root:

```bash
# Run with local ontologies
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills

# Run tests
cargo test --manifest-path mcp/Cargo.toml

# Build release binary
cargo build --release --manifest-path mcp/Cargo.toml
```

---

## Client guides

- [Claude Code](./claude-code-mcp.md) — Setup for Claude Code CLI
- [Codex](./codex-mcp.md) — Setup for Codex-based workflows

---

## Troubleshooting

### "Ontology root not found"

Ensure compiled `.ttl` files exist:

```bash
ls ~/.ontoskills/ontologies/
# Should show: index.ttl, system/, etc.

ls ~/.ontoskills/ontologies/system/
# Should show: index.enabled.ttl, embeddings/, etc.
```

If missing, compile skills first:

```bash
ontoskills compile
```

### "Embeddings not available"

Search always works with **BM25** (keyword search). Semantic search is optional and only available when compiled with `--features embeddings` and embedding files are present.

If you want semantic search for large catalogs and the ONNX Runtime shared library is missing, set `ORT_DYLIB_PATH`:

```bash
export ORT_DYLIB_PATH=/path/to/libonnxruntime.so
```

To generate embedding files:

```bash
ontoskills export-embeddings
```

### "Server not initialized"

The MCP client must send `initialize` before calling tools. This is handled automatically by compliant clients.

### Connection drops silently

Check logs for errors:

```bash
# Run manually to see stderr
~/.ontoskills/bin/ontomcp --ontology-root ~/.ontoskills/ontologies
```

---

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ONTOMCP_ONTOLOGY_ROOT` | Ontology directory | `~/.ontoskills/ontologies` |
| `ORT_DYLIB_PATH` | Path to ONNX Runtime shared library (optional — only for semantic search on large catalogs) | Auto-detected |
