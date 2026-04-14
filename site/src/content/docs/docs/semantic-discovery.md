---
title: Semantic Intent Discovery
description: Find skills by natural language intent with pre-computed per-skill embeddings
sidebar:
  order: 8
---

## Overview

Semantic Intent Discovery enables LLM agents to find skills by natural language intent without knowing exact intent strings. This breaks the O(1) query promise — agents can now discover how to query the ontology.

**Solution:** Convention (C) + Schema Summary (A) + Semantic Discovery

| Component | Purpose |
|-----------|---------|
| **Convention** | Predictable naming (`verb_noun` for intents, `camelCase` for properties) |
| **Schema Summary** | MCP Resource `ontology://schema` — 2KB compact schema |
| **search** (semantic mode) | MCP Tool — semantic matching via pre-computed embeddings |

---

## Architecture

Embeddings are **pre-computed per-skill at compile time** and merged at install time. The MCP server performs ONNX inference only for the query, matching it against pre-loaded intent vectors.

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPILE-TIME (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontocore compile                                                │
│       │                                                          │
│       ├──► ontoskill.ttl (existing)                             │
│       │                                                          │
│       └──► intents.json          # MANDATORY per-skill file     │
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
│                   INSTALL-TIME (JS CLI)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills install <package>                                    │
│       │                                                          │
│       ├──► Download model.onnx + tokenizer.json (once, cached)  │
│       ├──► Download per-skill intents.json                       │
│       └──► mergeEmbeddings() → system/embeddings/intents.json   │
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

Every skill **must** declare at least one intent. During compilation, `ontocore compile` generates an `intents.json` next to each `ontoskill.ttl`:

```text
ontoskills/
└── <skill>/
    ├── ontoskill.ttl
    └── intents.json     # MANDATORY — compilation fails without intents
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

If a skill has zero declared intents, compilation **fails** with:

```text
Skill 'my-skill' has no declared intents. Every skill must declare at
least one intent for semantic search.
```

---

## Usage

### Compile (mandatory)

```bash
ontocore compile -i skills/ -o ontoskills/
```

This produces both `ontoskill.ttl` and `intents.json` per skill. Requires `sentence-transformers`:

```bash
pip install sentence-transformers
```

### Export ONNX model (one-time)

```bash
ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./embeddings
```

This creates the global model artifacts (`model.onnx` + `tokenizer.json`) that the MCP server uses for query inference. Published once to the registry by the maintainer.

### Install + merge (JS CLI)

```bash
ontoskills install mareasw/office/xlsx
```

The CLI:
1. Downloads `model.onnx` + `tokenizer.json` (once, cached)
2. Downloads per-skill `intents.json` files
3. Merges all installed intents into `system/embeddings/intents.json`

Opt out of embeddings with `--no-embeddings`:

```bash
ontoskills install mareasw/office/xlsx --no-embeddings
```

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
| `local` | 1.2 | Boosts locally compiled skills |
| `trusted` | 1.2 | Boosts official/trusted vendor skills |
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
| search latency (semantic) | < 50ms | Manual benchmark |
| ONNX model size | ~90MB | Check file size |
| Memory footprint | < 200MB | Monitor with `top` |

---

## File structure

```text
~/.ontoskills/
├── ontologies/
│   ├── system/
│   │   ├── index.enabled.ttl
│   │   └── embeddings/
│   │       ├── model.onnx           # Global ONNX model (~90MB)
│   │       ├── tokenizer.json       # HuggingFace tokenizer
│   │       └── intents.json         # MERGED from all installed skills
│   └── vendor/
│       └── <vendor>/<pkg>/<skill>/
│           ├── ontoskill.ttl
│           └── intents.json         # Per-skill pre-computed embeddings
```

**Source code:**

```text
core/
├── src/embeddings/
│   └── exporter.py              # Per-skill export + ONNX model export

mcp/
├── src/
│   ├── embeddings.rs            # Rust embedding engine (ONNX inference)
│   ├── schema.rs                # Schema resource
│   └── main.rs                  # MCP tool handlers

cli/
├── lib/
│   └── registry.js              # mergeEmbeddings() at install time
```

---

## Dependencies

### Python (core/) — mandatory for compile

```toml
# pyproject.toml — required dependency
sentence-transformers>=2.2.0

# pyproject.toml — optional (for export-embeddings only)
optimum>=1.12.0
onnx>=1.15.0
onnxruntime>=1.16.0
```

### Rust (mcp/)

```toml
ort = { version = "2.0.0-rc.12", features = ["load-dynamic"] }
tokenizers = "0.19"
ndarray = "0.17"
anyhow = "1.0"
```

### Runtime requirement

The ONNX Runtime shared library must be available. The MCP server uses `ort` with `load-dynamic`, which looks for `libonnxruntime.so` at runtime. Set `ORT_DYLIB_PATH` if needed:

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
