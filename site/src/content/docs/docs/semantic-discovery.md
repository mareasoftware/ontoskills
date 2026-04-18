---
title: Intent Discovery
description: Find skills by natural language intent using BM25 keyword search, with optional semantic embeddings for large catalogs
sidebar:
  order: 8
---

## Overview

Intent Discovery enables LLM agents to find skills by natural language intent without knowing exact intent strings. BM25 keyword search is the default and is always available. Semantic embeddings are optional and recommended only for large skill catalogs where keyword matching may miss relevant results.

**Solution:** Convention (C) + Schema Summary (A) + Intent Discovery

| Component | Purpose |
|-----------|---------|
| **Convention** | Predictable naming (`verb_noun` for intents, `camelCase` for properties) |
| **Schema Summary** | MCP Resource `ontology://schema` — 2KB compact schema |
| **search** (BM25 mode) | MCP Tool — fast keyword matching via in-memory BM25 index |
| **search** (semantic mode) | MCP Tool — optional semantic matching via pre-computed embeddings |

---

## BM25 Keyword Search

BM25 is the default search method and is always available. It requires no external dependencies or model downloads — the index is built in-memory from Catalog data at MCP server startup.

- **Always available**: no extra dependencies, no model downloads, no compile-time changes
- **Built at startup**: the BM25 index is constructed from the Catalog data loaded into memory
- **Search fields**: skill intents, aliases, and nature descriptions
- **Tokenization**: English stemming and stop words via the `bm25` crate
- **Response shape**: results include `"mode": "bm25"` to identify the search method

```json
{
  "query": "create a pdf document",
  "mode": "bm25",
  "matches": [
    {"intent": "create_pdf", "score": 12.4, "skills": ["pdf"]},
    {"intent": "export_document", "score": 8.1, "skills": ["pdf", "document-export"]}
  ]
}
```

---

## Semantic Search (Optional)

Semantic search is only needed for **large skill catalogs** where keyword matching may not capture the user's intent. It uses pre-computed embeddings and ONNX inference for semantic similarity matching.

**Requirements:**

- Compile time: `ontocore[embeddings]` (Python extra)
- Rust MCP build: `--features embeddings`
- Falls back from BM25 when semantic confidence is low

Embeddings are **pre-computed per-skill at compile time** and downloaded optionally at install time. The MCP server scans per-skill `intents.json` files across the ontology tree at startup, performing ONNX inference only for the query.

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPILE-TIME (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontocore compile                                                │
│       │                                                          │
│       ├──► ontoskill.ttl (existing)                             │
│       │                                                          │
│       └──► intents.json          # Optional per-skill file      │
│            Pre-computed 384-dim embeddings (L2-normalized)      │
│                                                                  │
│  ontocore export-embeddings      # ONE-TIME: global ONNX model  │
│       │                                                          │
│       └──► model.onnx + tokenizer.json                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   INSTALL-TIME (CLI)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills install <package>                                    │
│       │                                                          │
│       └──► Installs ontoskill.ttl + package.json                │
│                                                                  │
│  ontoskills install <package> --with-embeddings                  │
│       │                                                          │
│       ├──► Download model.onnx + tokenizer.json (once, cached)  │
│       └──► Download per-skill intents.json                       │
│                                                                  │
│  MCP server scans per-skill intents.json at startup              │
│  (no centralized merge step needed)                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RUNTIME (Rust MCP)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Tools:                                                          │
│    search(query: str, top_k: int) → Vec<IntentMatch>    │
│       │                                                          │
│       ├── 1. Load tokenizer.json + model.onnx                   │
│       ├── 2. Safety-truncate query (max 512 chars)              │
│       ├── 3. Tokenize query → input_ids, attention_mask         │
│       ├── 4. ONNX inference → query embedding (384 dim)         │
│       ├── 5. Cosine similarity vs pre-computed intents.json     │
│       └── 6. Adaptive cutoff (min 0.4, gap 0.15) → top_k       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Per-skill embeddings

When embeddings are enabled, every skill that declares intents gets an `intents.json` generated next to its `ontoskill.ttl` during compilation. Skills without declared intents simply skip embedding generation — compilation does not fail.

```text
ontoskills/
└── <skill>/
    ├── ontoskill.ttl
    └── intents.json     # Optional (when embeddings enabled) — skipped if no intents
```

**intents.json format:**

```json
{
  "model": "sentence-transformers/all-MiniLM-L6-v2",
  "dimension": 384,
  "intents": [
    {
      "intent": "edit spreadsheet",
      "embedding": [0.12, -0.05, ...],
      "skills": ["calc-skill"]
    }
  ]
}
```

If a skill has zero declared intents and embeddings are enabled, the compiler skips embedding generation for that skill and logs a warning.

---

## Usage

### Compile (mandatory)

```bash
ontocore compile -i skills/ -o ontoskills/
```

This produces `ontoskill.ttl` per skill. By default, no embedding dependencies are required. To generate per-skill embeddings, install the embeddings extra:

```bash
pip install ontocore[embeddings]
```

### Export ONNX model (one-time)

```bash
ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./embeddings
```

This creates the global model artifacts (`model.onnx` + `tokenizer.json`) that the MCP server uses for query inference. Published once to the registry by the maintainer.

### Install + optional embeddings

```bash
ontoskills install obra/superpowers
```

By default, installs only `ontoskill.ttl` + `package.json` (no embeddings). To include per-skill embedding files for semantic search:

```bash
ontoskills install obra/superpowers --with-embeddings
```

The CLI downloads per-skill `intents.json` files alongside the skill TTLs. The MCP server discovers them automatically at startup by scanning the ontology tree — no centralized merge step needed.

### MCP Tool: search (semantic mode)

```json
{
  "name": "search",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

Returns matching intents with hybrid scores (cosine similarity × trust-tier quality multiplier):

```json
{
  "query": "create a pdf document",
  "matches": [
    {"intent": "create_pdf", "score": 0.92, "skills": ["pdf"]},
    {"intent": "export_document", "score": 0.78, "skills": ["pdf", "document-export"]}
  ]
}
```

### Hybrid Scoring

Results are ranked by **hybrid score** — cosine similarity multiplied by a trust-tier quality multiplier. This ensures higher-trust skills rank above community skills even when their raw similarity is slightly lower.

| Trust Tier | Multiplier | Effect |
|------------|------------|--------|
| `local` | 1.0 | Neutral for locally compiled skills |
| `official` | 1.2 | Boosts official/trusted author skills |
| `verified` | 1.0 | Neutral (baseline) |
| `community` | 0.8 | Dampens community contributions |

Example: a verified skill with cosine 0.80 (hybrid: 0.80) outranks a community skill with cosine 0.90 (hybrid: 0.72).

### MCP resource: ontology://schema

A compact JSON schema describing available classes and properties:

```json
{
  "version": "0.1.0",
  "base_uri": "https://ontoskills.sh/ontology#",
  "prefix": "oc",
  "classes": { ... },
  "properties": { ... },
  "example_queries": [ ... ]
}
```

---

## Agent workflow

```
1. Agent starts → reads ontology://schema (2KB)
   → Knows all properties and conventions

2. User: "I need to create a PDF"
   → Agent calls: search(query: "create a pdf", top_k: 3)
   → Returns: [{intent: "create_pdf", score: 0.92, skills: ["pdf"]}]

3. Agent now knows intent = "create_pdf"
   → Agent queries: SELECT ?skill WHERE { ?skill oc:resolvesIntent "create_pdf" }
   → Returns: oc:pdf

4. Agent calls: get_skill_context("pdf")
   → Returns: full skill context with payload, dependencies, and knowledge nodes
```

---

## Performance targets

| Metric | Target | Verification |
|--------|--------|--------------|
| Schema resource size | < 4KB | `test_schema_size` |
| search latency (BM25) | < 5ms | Manual benchmark |
| search latency (semantic) | < 50ms | Manual benchmark |
| ONNX model size | ~90MB | Check file size |
| Memory footprint (without embeddings) | < 50MB | Monitor with `top` |

---

## File structure

```text
~/.ontoskills/
├── ontologies/
│   ├── system/
│   │   ├── index.enabled.ttl
│   │   └── embeddings/
│   │       ├── model.onnx           # Global ONNX model (~90MB)
│   │       └── tokenizer.json       # HuggingFace tokenizer
│   └── author/
│       └── <author>/<pkg>/<skill>/
│           ├── ontoskill.ttl
│           └── intents.json         # Per-skill pre-computed embeddings (optional)
```

**Source code:**

```text
core/
├── src/embeddings/
│   └── exporter.py              # Per-skill export + ONNX model export

mcp/
├── src/
│   ├── embeddings.rs            # Rust embedding engine (ONNX inference + per-skill scan)
│   ├── bm25_engine.rs           # BM25 keyword search (always available)
│   ├── catalog.rs               # Catalog with trust tier quality multiplier
│   ├── schema.rs                # Schema resource
│   └── main.rs                  # MCP tool handlers
```

---

## Dependencies

### Python (core/) — compile

```toml
# pyproject.toml — optional dependency (embedding generation)
[project.optional-dependencies]
embeddings = ["sentence-transformers>=2.2.0"]

# pyproject.toml — optional (for export-embeddings only)
optimum>=1.12.0
onnx>=1.15.0
onnxruntime>=1.16.0
```

### Rust (mcp/)

```toml
# Mandatory — always included
bm25 = "1"
anyhow = "1.0"

# Optional — behind [features] embeddings
[features]
embeddings = ["ort", "tokenizers", "ndarray"]

[dependencies]
ort = { version = "2.0.0-rc.12", features = ["load-dynamic"], optional = true }
tokenizers = { version = "0.19", optional = true }
ndarray = { version = "0.17", optional = true }
```

### Runtime requirement (optional)

When semantic search is enabled (`--features embeddings`), the ONNX Runtime shared library must be available. The MCP server uses `ort` with `load-dynamic`, which looks for `libonnxruntime.so` at runtime. Set `ORT_DYLIB_PATH` if needed:

```bash
export ORT_DYLIB_PATH=/path/to/libonnxruntime.so
```

---

## Testing

### Python tests

```bash
cd core && python -m pytest tests/test_embeddings.py -v
```

### Rust tests

```bash
cd mcp && cargo test
```

### E2E test

```bash
bash mcp/tests/e2e_search.sh
```

---

## Related

- [OntoCore Compiler](./ontocore/) — Compilation reference
- [MCP Runtime](./mcp/) — Tool reference
- [CLI Reference](./cli/) — Install and merge commands
