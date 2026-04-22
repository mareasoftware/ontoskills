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

OntoMCP exposes **4 tools** for skill discovery, context retrieval, and reasoning.

### `search`

Search skills by semantic query, alias, or structured filters. The tool dispatches based on the parameters provided:

- **`query`** provided → BM25 keyword search (with optional semantic fallback for large catalogs)
- **`alias`** provided → alias resolution
- Otherwise → structured skill search with filters

#### Structured skill search

```json
{
  "intent": "create_pdf",
  "requires_state": "oc:DocumentCreated",
  "yields_state": "oc:PdfGenerated",
  "skill_type": "executable",
  "category": "document",
  "is_user_invocable": true,
  "limit": 25
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `intent` | string | Filter by resolved intent |
| `requires_state` | string | Filter by required state (URI or `oc:StateName`) |
| `yields_state` | string | Filter by yielded state (URI or `oc:StateName`) |
| `skill_type` | string | `executable` or `declarative` |
| `category` | string | Filter by skill category (e.g., `automation`, `document`, `marketing`) |
| `is_user_invocable` | boolean | Filter by whether the skill is directly invocable by users |
| `limit` | integer | Max results (1-100, default 25) |

**Example response:**

```json
{
  "skills": [
    {
      "id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "nature": "A skill for test-driven development",
      "intents": ["write tests first", "practice TDD"],
      "requires_state": ["oc:CodeReady"],
      "yields_state": ["oc:TestsPassing"]
    }
  ],
  "total": 1
}
```

#### Semantic intent search

When the `query` parameter is provided, the search tool uses **BM25** as the default search engine. BM25 is an in-memory keyword ranking algorithm that operates directly on Catalog data — it is always available and requires no additional dependencies.

```json
{
  "query": "create a pdf document",
  "top_k": 5
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | **Required.** Natural language query |
| `top_k` | integer | Number of results (default 5) |

**BM25 response example** (default mode):

```json
{
  "query": "create a pdf document",
  "mode": "bm25",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "score": 0.92,
      "matched_by": "intent",
      "intents": ["create_pdf", "export_to_pdf"],
      "aliases": ["pdf"],
      "trust_tier": "core"
    }
  ]
}
```

**Semantic fallback** (optional, for large catalogs):

Semantic search is an optional enhancement for large skill catalogs where keyword matching alone may not capture nuanced queries. It requires compiling with `--features embeddings` and having embedding files present (`ontoskills export-embeddings`).

When BM25 confidence is below the fallback threshold (0.4) and embeddings are available, the server automatically falls back to semantic search:

```json
{
  "query": "generate a report with charts and export it",
  "mode": "semantic",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "obra/superpowers/test-driven-development",
      "score": 0.88,
      "matched_by": "embedding_similarity",
      "intents": ["create_pdf", "export_to_pdf"],
      "aliases": ["pdf"],
      "trust_tier": "core"
    }
  ]
}
```

Semantic results use **hybrid scoring** (cosine similarity x trust-tier quality multiplier) so higher-trust skills rank above community contributions even with slightly lower raw similarity.

#### Alias resolution

```json
{
  "alias": "pdf"
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `alias` | string | **Required.** Alias to resolve (case-insensitive) |

**Example response:**

```json
{
  "alias": "pdf",
  "skills": [
    {
      "id": "test-driven-development",
      "qualified_id": "obra/superpowers/test-driven-development",
      "nature": "A skill for test-driven development",
      "intents": ["write tests first", "practice TDD"]
    }
  ]
}
```

---

### `get_skill_context`

Fetch the full execution context for a skill, including requirements, transitions, payload, dependencies, knowledge nodes, and section titles (table of contents).

```json
{
  "skill_id": "pdf",
  "include_inherited_knowledge": true
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `skill_id` | string | **Required.** Short id (`test-driven-development`) or qualified (`obra/superpowers/test-driven-development`) |
| `include_inherited_knowledge` | boolean | Include knowledge from extended skills (default true) |

**Example response:**

```json
{
  "id": "test-driven-development",
  "qualified_id": "obra/superpowers/test-driven-development",
  "nature": "A skill for test-driven development",
  "genus": "Development",
  "differentia": "writes tests first",
  "intents": ["write tests first", "practice TDD"],
  "requires_state": ["oc:CodeReady"],
  "yields_state": ["oc:TestsPassing"],
  "handles_failure": ["oc:PdfGenerationFailed"],
  "requirements": [
    {"type": "Tool", "value": "wkhtmltopdf", "optional": false}
  ],
  "depends_on": ["content-processor"],
  "extends": ["document-base"],
  "execution_payload": {
    "executor": "shell",
    "code": "wkhtmltopdf $INPUT $OUTPUT.pdf",
    "timeout": 30000
  },
  "knowledge_nodes": [
    {
      "node_type": "PreFlightCheck",
      "directive_content": "Verify wkhtmltopdf is installed",
      "applies_to_context": "Before PDF generation",
      "has_rationale": "Avoids runtime failures",
      "severity_level": "HIGH"
    }
  ]
}
```

---

### Agent workflow

The 4 tools form a complete workflow that replaces reading raw SKILL.md files:

```
search → get_skill_context → evaluate_execution_plan → query_epistemic_rules
discovery   understanding     plan validation          compliance
```

1. **`search`** — Find the right skill by intent, keyword, or alias
2. **`get_skill_context`** — Get the full context including knowledge nodes, requirements, dependencies, and execution payload
3. **`evaluate_execution_plan`** — Validate that the plan is feasible (states, dependencies)
4. **`query_epistemic_rules`** — Check specific rules and constraints during execution

Each tool loads only the data it needs. The agent never reads the full SKILL.md — it queries the ontology store via SPARQL and gets deterministic, structured results in sub-millisecond time.

---

### `evaluate_execution_plan`

Evaluate whether an intent or skill can be executed from the current states. Returns the full execution plan plus warnings.

```json
{
  "intent": "create_pdf",
  "current_states": ["oc:ContentReady", "oc:UserAuthenticated"],
  "max_depth": 10
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `intent` | string | Target intent (use either `intent` or `skill_id`) |
| `skill_id` | string | Target skill (use either `intent` or `skill_id`) |
| `current_states` | array | Current state URIs or compact values |
| `max_depth` | integer | Max plan depth (1-10, default 10) |

**Example response:**

```json
{
  "executable": true,
  "plan": [
    {
      "skill_id": "content-processor",
      "step": 1,
      "satisfies": ["oc:ContentReady"]
    },
    {
      "skill_id": "pdf",
      "step": 2,
      "requires": ["oc:ContentReady"],
      "yields": ["oc:PdfGenerated"]
    }
  ],
  "missing_states": [],
  "warnings": [
    "Skill 'pdf' has optional dependency 'fonts-installer' not in plan"
  ]
}
```

**When `executable: false`:**

```json
{
  "executable": false,
  "plan": [],
  "missing_states": ["oc:ApiKeyConfigured"],
  "warnings": ["Cannot proceed without API key configuration"]
}
```

---

### `query_epistemic_rules`

Query normalized knowledge nodes with guided filters.

```json
{
  "skill_id": "pdf",
  "kind": "AntiPattern",
  "dimension": "SecurityGuardrail",
  "severity_level": "CRITICAL",
  "applies_to_context": "file handling",
  "include_inherited": true,
  "limit": 25
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `skill_id` | string | Filter by skill |
| `kind` | string | Node type (Heuristic, AntiPattern, PreFlightCheck, etc.) |
| `dimension` | string | Epistemic dimension (NormativeRule, ResilienceTactic, etc.) |
| `severity_level` | string | CRITICAL, HIGH, MEDIUM, LOW |
| `applies_to_context` | string | Context filter |
| `include_inherited` | boolean | Include extended skills (default true) |
| `limit` | integer | Max results (1-100, default 25) |

**Example response:**

```json
{
  "rules": [
    {
      "skill_id": "pdf",
      "node_type": "AntiPattern",
      "dimension": "SecurityGuardrail",
      "directive_content": "Do not accept file paths from untrusted input",
      "applies_to_context": "When processing user-provided filenames",
      "has_rationale": "Prevents path traversal attacks",
      "severity_level": "CRITICAL"
    }
  ],
  "total": 1
}
```

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
