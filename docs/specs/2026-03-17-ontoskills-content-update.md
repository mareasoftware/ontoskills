# OntoClaw Site Content Update — Ontoskills & Roadmap

> **Goal:** Reframe the site from "compiler-focused" to "MCP server + ontoskills platform" with a public, mutable roadmap.

## Background

OntoClaw is not just a compiler. The compiler is Phase 1 — it serves the MCP server, which is the core product. The paradigm shift:

```
TRADITIONAL: LLM reads skill → interprets → executes → forgets
ONTOCLAW:    LLM queries MCP → graph responds → executes → updates ABox
```

## Key Terminology

- **Ontoskills** — Skills represented as formal ontologies (NOT "semantic skills")
- **MCP Server** — Exposes ontoskills via Model Context Protocol
- **TBox** — Terminology box: stable concepts/classes (e.g., "can install Python lib if Python installed")
- **RBox** — Role box: stable relations/properties
- **ABox** — Assertion box: mutable facts (e.g., "Python is installed" → true/false)

## Changes

### 1. Landing Page Hero

**Current:** "Graph-aware AI validation framework"
**New:** Focus on MCP + deterministic reasoning

Suggested tagline: "Ontoskills: when the LLM doesn't guess, it asks"

### 2. Features Section (revised)

| Current | New |
|---------|-----|
| LLM Extraction | **Ontoskill Query** — SPARQL O(1) lookup vs O(n) text scan |
| Knowledge Architecture | **Deterministic Reasoning** — Graph responds, LLM executes |
| OWL 2 Serialization | **Evolving Knowledge** — ABox updates on success/failure |
| SHACL Validation | **Stable Foundations** — TBox/RBox for consistent rules |
| State Machines | **MCP Protocol Native** — Direct integration with Claude, etc. |
| Security Pipeline | Keep as-is |

### 3. Problem/Solution Section

Update messaging to contrast:
- **Problem:** LLM reads 50+ skill files, context rot, hallucinations
- **Solution:** LLM queries graph, gets precise answer, updates state

### 4. New Section: Roadmap

Create a dedicated roadmap section/page with:

```
✅ Phase 1: Compiler
   SKILL.md → RDF/Turtle transformation

🔨 Phase 2: MCP Server
   Query interface + ABox runtime updates

💡 Phase 3: OntoStore
   Centralized repository for ontoskills

🔮 Phase 4+: Ecosystem & Beyond
   - Ecosystem integrations (Claude Desktop, VSCode, etc.)
   - Multi-agent collaboration
   - ???

⚠️ Roadmap is mutable — we develop fast.
```

### 5. Documentation Updates

#### `overview.md`
- Rewrite intro centered on MCP + ontoskills
- Explain TBox/RBox/ABox architecture
- Link to roadmap

#### `getting-started.md`
- Currently generic, needs rewrite
- Focus on: install → configure ontology → query via MCP

#### New: `roadmap.md`
- Dedicated page with full roadmap
- Mutable disclaimer
- Links to GitHub for progress tracking

### 6. Terminology Audit

Replace all instances of:
- "semantic skills" → "ontoskills"
- "semantic-skills" → "ontoskills"

## Files to Modify

1. `src/components/landing/Hero.astro` — tagline + CTA
2. `src/components/landing/Features.astro` — feature list
3. `src/components/landing/ProblemSolution.astro` — messaging
4. `src/components/landing/HowItWorks.astro` — new flow
5. `src/components/landing/Roadmap.astro` — NEW component
6. `src/content/docs/overview.md` — rewrite
7. `src/content/docs/getting-started.md` — rewrite
8. `src/content/docs/roadmap.md` — NEW page
9. `astro.config.mjs` — add roadmap to sidebar
