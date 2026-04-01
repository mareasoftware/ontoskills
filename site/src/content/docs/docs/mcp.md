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

For one-command client bootstrap, see [MCP Bootstrap](/mcp-bootstrap/).

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

OntoMCP exposes **5 tools** for skill discovery and reasoning.

### `search_skills`

Discover skills with optional filters.

```json
{
  "intent": "create_pdf",
  "requires_state": "oc:DocumentCreated",
  "yields_state": "oc:PdfGenerated",
  "skill_type": "executable",
  "limit": 25
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `intent` | string | Filter by resolved intent |
| `requires_state` | string | Filter by required state (URI or `oc:StateName`) |
| `yields_state` | string | Filter by yielded state (URI or `oc:StateName`) |
| `skill_type` | string | `executable` or `declarative` |
| `limit` | integer | Max results (1-100, default 25) |

**Example response:**

```json
{
  "skills": [
    {
      "id": "pdf",
      "qualified_id": "mareasw/office/pdf",
      "nature": "A skill that creates PDF documents",
      "intents": ["create_pdf", "export_pdf"],
      "requires_state": ["oc:ContentReady"],
      "yields_state": ["oc:PdfGenerated"]
    }
  ],
  "total": 1
}
```

---

### `search_intents`

Search for intents semantically matching a natural language query. Requires embeddings to be exported first.

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

**Example response:**

```json
{
  "query": "create a pdf document",
  "matches": [
    {
      "intent": "create_pdf",
      "score": 0.92,
      "skills": ["mareasw/office/pdf", "mareasw/documents/pdf-generator"]
    },
    {
      "intent": "export_to_pdf",
      "score": 0.85,
      "skills": ["mareasw/office/export"]
    }
  ]
}
```

**Note:** Requires running `ontoskills export-embeddings` first. If embeddings are not available, the tool returns an error.

---

### `get_skill_context`

Fetch the full execution context for a skill, including requirements, transitions, payload, dependencies, and knowledge nodes.

```json
{
  "skill_id": "pdf",
  "include_inherited_knowledge": true
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `skill_id` | string | **Required.** Short id (`pdf`) or qualified (`mareasw/office/pdf`) |
| `include_inherited_knowledge` | boolean | Include knowledge from extended skills (default true) |

**Example response:**

```json
{
  "id": "pdf",
  "qualified_id": "mareasw/office/pdf",
  "nature": "A skill that creates PDF documents from content",
  "genus": "DocumentGenerator",
  "differentia": "outputs PDF format",
  "intents": ["create_pdf", "export_pdf"],
  "requires_state": ["oc:ContentReady"],
  "yields_state": ["oc:PdfGenerated"],
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
│  │   Catalog   │  │  Embeddings │  │   SPARQL Engine     │  │
│  │   (Rust)    │  │  (Optional) │  │   (Oxigraph)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼───────────────────┼─────────────┘
          │                │                   │
          ▼                ▼                   ▼
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

The `search_intents` tool requires pre-computed embeddings:

```bash
ontoskills export-embeddings
```

This creates `~/.ontoskills/ontologies/system/embeddings/`.

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
