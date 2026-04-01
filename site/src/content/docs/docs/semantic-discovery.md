---
title: Semantic Intent Discovery
description: Find skills by natural language intent without knowing exact intent strings
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
| **search_intents** | MCP Tool — semantic matching via embeddings |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     COMPILE-TIME (Python)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ontoskills export-embeddings                                   │
│       │                                                          │
│       ├──► ontoskill.ttl (existing)                             │
│       │                                                          │
│       └──► ontoskills/system/embeddings/                        │
│                ├── model.onnx          # Exported model (~45MB)  │
│                ├── tokenizer.json      # HuggingFace tokenizer   │
│                └── intents.json         # Pre-computed embeddings│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RUNTIME (Rust MCP)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Resources:                                                      │
│    ontology://schema → JSON schema (classes, properties)        │
│                                                                  │
│  Tools:                                                          │
│    search_intents(query: str, top_k: int) → Vec<IntentMatch>    │
│       │                                                          │
│       ├── 1. Load tokenizer.json                                 │
│       ├── 2. Tokenize query → input_ids, attention_mask         │
│       ├── 3. ONNX inference → embedding (384 dim)               │
│       ├── 4. Cosine similarity vs intents.json                  │
│       └── 5. Return top_k matches                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Usage

### Export embeddings

```bash
ontoskills export-embeddings --ontology-root ./ontoskills
```

This creates `ontoskills/system/embeddings/` with:
- `model.onnx` - ONNX embedding model (~45MB)
- `tokenizer.json` - HuggingFace tokenizer
- `intents.json` - Pre-computed intent embeddings

### MCP Tool: search_intents

Once embeddings are exported, the MCP server provides:

```json
{
  "name": "search_intents",
  "arguments": {
    "query": "create a pdf document",
    "top_k": 5
  }
}
```

Returns matching intents with similarity scores:
```json
{
  "query": "create a pdf document",
  "matches": [
    {"intent": "create_pdf", "score": 0.92, "skills": ["pdf"]},
    {"intent": "export_document", "score": 0.78, "skills": ["pdf", "document-export"]}
  ]
}
```

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
   → Agent calls: search_intents("create a pdf", top_k: 3)
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
| search_intents latency | < 50ms | Manual benchmark |
| ONNX model size | < 50MB | Check file size |
| Memory footprint | < 100MB | Monitor with `top` |

---

## File structure

```
ontoskills/
└── system/
    └── embeddings/
        ├── model.onnx           # ~45MB
        ├── tokenizer.json       # ~500KB
        ├── tokenizer_config.json
        ├── special_tokens_map.json
        └── intents.json         # Variable

core/
├── embeddings/
│   ├── __init__.py
│   └── exporter.py              # Python export script

mcp/
├── src/
│   ├── embeddings.rs            # Rust embedding engine
│   ├── schema.rs                # Schema resource
│   └── main.rs                  # MCP tool handlers
```

---

## Dependencies

### Python (core/)

```txt
sentence-transformers>=2.2.0
transformers>=4.30.0
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

### CLI verification

```bash
ontoskills export-embeddings --help
```

---

## Related

- [MCP Server README](../mcp/README.md)
