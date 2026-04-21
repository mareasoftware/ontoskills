# OntoMCP

Rust-based local MCP (Model Context Protocol) server for the OntoSkills ecosystem.

<p align="right">
  <b>🇬🇧 English</b> • <a href="README_zh.md">🇨🇳 中文</a>
</p>

---

## Overview

OntoMCP is the **runtime layer** of OntoSkills. It loads compiled ontologies (`.ttl` files) into an in-memory RDF graph and provides blazing-fast SPARQL queries to AI agents via the Model Context Protocol.

```mermaid
flowchart LR
    AGENT["AI Agent<br/>━━━━━━━━━━<br/>Claude Code<br/>Cursor<br/>Other MCP clients"] <-->|"SPARQL queries"| MCP["OntoMCP<br/>━━━━━━━━━━<br/>Rust runtime<br/>in-memory graph"]
    MCP <-->|"loads"| TTL[".ttl files<br/>━━━━━━━━━━<br/>ontoskills/<br/>compiled ontologies"]

    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style TTL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

**SKILL.md files DO NOT EXIST in the agent's context.** Only compiled `.ttl` artifacts are loaded.

---

## Scope

The MCP server is intentionally focused on:

- **Skill discovery** — Search skills by intent, state, and type
- **Skill context retrieval** — Return execution payload, transitions, dependencies, knowledge nodes, and section titles in one call
- **Skill content retrieval** — Return reconstructed markdown for skill sections (code, procedures, tables, etc.)
- **Planning** — Evaluate whether a skill or intent is executable from the current state set
- **Epistemic retrieval** — Query normalized `KnowledgeNode` rules by kind, dimension, severity, and context

The server does **not** execute skill payloads. Payload execution is delegated to the calling agent in its current runtime context.

---

## Architecture

```mermaid
flowchart LR
    CLIENT["MCP Client<br/>━━━━━━━━━━<br/>Claude Code<br/>stdio transport"] -->|"tools/call"| TOOLS["MCP Tools<br/>━━━━━━━━━━<br/>5 tools<br/>search, context, content, plan, rules"]
    TOOLS -->|"BM25 search"| BM25["BM25 Engine<br/>━━━━━━━━━━<br/>in-memory<br/>keyword search"]
    TOOLS -->|"SPARQL"| SPARQL["oxigraph<br/>━━━━━━━━━━<br/>SPARQL 1.1 engine<br/>in-memory store"]
    BM25 -->|"builds from"| GRAPH["RDF Graph<br/>━━━━━━━━━━<br/>Loaded .ttl files<br/>OntoSkills catalog"]
    SPARQL -->|"query"| GRAPH

    style CLIENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style TOOLS fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style BM25 fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style SPARQL fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style GRAPH fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

### Why Rust?

| Benefit | Description |
|---------|-------------|
| **Performance** | Sub-millisecond SPARQL queries for real-time agent interaction |
| **Memory efficiency** | Compact in-memory graph representation |
| **Safety** | Memory-safe by design, critical for production deployments |
| **Concurrency** | Parallel query execution without GIL limitations |

---

## Implemented Tools

| Tool | Purpose |
|------|---------|
| `search` | Search skills by keyword query, alias, or structured filters. Dispatches by parameter: `query` → BM25 keyword search (with optional semantic fallback), `alias` → alias resolution, otherwise → structured skill search |
| `get_skill_context` | Return the complete execution context for a skill, including payload, knowledge nodes, and section titles (table of contents) |
| `get_skill_content` | Retrieve skill section content as reconstructed markdown. If `section` is omitted, returns the table of contents |
| `evaluate_execution_plan` | Evaluate applicability and generate a plan for a target intent or skill |
| `query_epistemic_rules` | Query normalized knowledge nodes across the ontology with guided filters |

---

## Intent Discovery

OntoMCP provides two search engines for skill discovery:

### Default: BM25 Keyword Search

When embeddings are not available, BM25 keyword search is used. It builds an in-memory BM25 index from skill intents, aliases, and nature descriptions at startup.

```json
{
  "name": "search",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

Returns matching skills with BM25 scores:
```json
{
  "mode": "bm25",
  "query": "create a pdf document",
  "results": [
    {
      "skill_id": "pdf",
      "qualified_id": "marea/office/pdf",
      "score": 0.87,
      "matched_by": "keyword",
      "intents": ["create pdf document", "export to pdf"],
      "aliases": ["pdf-generator"],
      "trust_tier": "official"
    }
  ]
}
```

### Semantic Search (ONNX Embeddings) — preferred when available

When compiled with `--features embeddings` and embedding files are present, semantic search is preferred over BM25 — it provides more accurate results for nuanced queries, especially with large skill catalogs.

```bash
# Build with embedding support
cargo build --features embeddings
```

The response includes `"mode": "semantic"` with intent-level matches. If embeddings fail or return no results, BM25 is used as fallback.

### Trust-Tier Scoring

Both BM25 and semantic results use **quality multipliers** based on trust tier:

| Trust Tier | Multiplier | Effect |
|------------|------------|--------|
| `official` | 1.2 | Boosts official author skills (anthropics, coinbase, obra, etc.) |
| `local` | 1.0 | Locally compiled skills (same as verified) |
| `verified` | 1.0 | Neutral (baseline) |
| `community` | 0.8 | Dampens community contributions |

This ensures that an official skill with score 0.80 (hybrid: 0.96) outranks a community skill with score 0.90 (hybrid: 0.72).

### MCP Resource: `ontology://schema`

A compact (~2KB) JSON schema describing available classes, properties, and example queries.

```
1. Agent reads ontology://schema → Knows all properties and conventions
2. User: "I need to create a PDF"
3. Agent calls: search(query: "create a pdf", top_k: 3)
4. Agent queries: SELECT ?skill WHERE { ?skill oc:resolvesIntent "create_pdf" }
5. Agent calls: get_skill_context("pdf")
```

### Performance Targets

| Metric | Target |
|--------|--------|
| Schema resource size | < 4KB |
| search latency (BM25) | < 5ms |
| search latency (semantic, optional) | < 50ms |
| Memory footprint (without embeddings) | < 50MB |

`skill_id` fields accept:
- short ids like `xlsx`
- qualified ids like `marea/office/xlsx`

When a short id is ambiguous, runtime resolution follows:
- `official > local > verified > community`

Responses include package metadata such as:
- `qualified_id`
- `package_id`
- `trust_tier`
- `version`
- `source`

---

## Ontology Source

The server loads compiled `.ttl` files from a directory.

Preferred runtime source:

- `~/.ontoskills/ontologies/system/index.enabled.ttl` — enabled-only manifest generated by the product CLI

Fallbacks:

- `core.ttl` — Core TBox ontology with states
- `index.ttl` — Manifest with `owl:imports`
- `*/ontoskill.ttl` — Individual skill modules

**Auto-discovery**: Looks for `ontoskills/` from current directory upward.

If nothing is found locally, OntoMCP falls back to:

- `~/.ontoskills/ontologies`

**Override**:
```bash
--ontology-root /path/to/ontology-root
# or
ONTOMCP_ONTOLOGY_ROOT=/path/to/ontology-root
# alternative env var (same effect)
ONTOSKILLS_MCP_ONTOLOGY_ROOT=/path/to/ontology-root
```

**ONNX Runtime** (optional, for large skill catalogs):
```bash
ORT_DYLIB_PATH=/path/to/directory-containing-libonnxruntime
```

---

## Run

From repository root:

```bash
cargo run --manifest-path mcp/Cargo.toml
```

With explicit ontology path:

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

---

## One-Command Bootstrap

With the product CLI:

```bash
npx ontoskills install mcp --claude
npx ontoskills install mcp --codex --cursor
npx ontoskills install mcp --cursor --project
```

The CLI installs `ontomcp` first and then configures the selected client globally or for the current project where supported.

## Claude Code Integration

Register the MCP server:

```bash
claude mcp add ontomcp -- \
  ~/.ontoskills/bin/ontomcp
```

After registration, Claude Code can call:

```mermaid
flowchart LR
    CLAUDE["Claude Code"] -->|"search"| TOOLS["OntoMCP"]
    CLAUDE -->|"get_skill_context"| TOOLS
    CLAUDE -->|"get_skill_content"| TOOLS
    CLAUDE -->|"evaluate_execution_plan"| TOOLS
    CLAUDE -->|"query_epistemic_rules"| TOOLS

    style CLAUDE fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style TOOLS fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
```

For full setup steps, see the [Claude Code MCP guide](https://ontoskills.sh/docs/claude-code-mcp/).

---

## Testing

```bash
cd mcp
cargo test
```

**Rust test coverage**:
- Skill search
- Skill context retrieval with knowledge nodes
- Guided epistemic rule filtering
- Planner preference for direct skills over setup-heavy alternatives

---

## Related Components

| Component | Language | Description |
|-----------|----------|-------------|
| **OntoCore** | Python | Neuro-symbolic skill compiler |
| **OntoMCP** | Rust | Runtime server (this) |
| **OntoStore** | GitHub | Versioned skill registry |
| **CLI** | Node.js | One-command installer (`npx ontoskills`) |

---

*Part of the [OntoSkills ecosystem](../README.md).*
