---
title: What are OntoSkills?
description: OntoSkills architecture, store, and runtime overview
sidebar:
  order: 1
---

**OntoSkills** are a neuro-symbolic skill platform for deterministic agents. They turn `SKILL.md` sources into validated OWL 2 ontologies, serve compiled skills through a local MCP runtime, and distribute published packages through OntoStore.

---

## Why OntoSkills?

### The determinism problem

LLMs read skills probabilistically. Same query, different results. Long skill files are expensive for large models and confusing for small ones.

- **Non-deterministic reading** — LLMs interpret text differently each time
- **Token waste** — Large models burn tokens parsing long documentation
- **Small model limits** — Complex skills are unreadable by edge models
- **No verifiable structure** — Relationships between skills are implicit

### The ontological solution

OntoSkills transforms skills into formal ontologies with **Description Logics (OWL 2)**:

- **Deterministic queries** — SPARQL returns exact answers, every time
- **Entailment reasoning** — Infer dependencies, conflicts, capabilities
- **Democratized intelligence** — Small models query what large models read
- **Formal semantics** — No ambiguity in skill relationships

### Performance comparison

| Operation | Reading Files | Ontology Query |
|-----------|---------------|----------------|
| Find skill by intent | O(n) text scan | O(1) indexed lookup |
| Check dependencies | Parse each file | Follow `dependsOn` edges |
| Detect conflicts | Compare all pairs | Single SPARQL query |

**For 100 skills:** ~500KB text scan → ~1KB query

---

## How it works

<img src="/architecture.webp" alt="OntoCore Architecture" style="max-height: 500px; width: auto; max-width: 100%; display: block; margin: 0 auto;" />

### The compilation pipeline

1. **Extract** — Claude reads SKILL.md and extracts structured knowledge
2. **Validate** — Security pipeline checks for malicious content
3. **Serialize** — Pydantic models → RDF triples
4. **Verify** — SHACL gatekeeper ensures logical validity
5. **Write** — Compiled `.ttl` files to `ontoskills/`

### The runtime

- **OntoMCP** loads compiled `.ttl` files from `ontoskills/`
- Agents query via SPARQL through the MCP protocol
- OntoStore is built in by default
- Third-party stores can be added explicitly with `store add-source`

---

## Key capabilities

| Capability | Description |
|------------|-------------|
| **LLM Extraction** | Claude extracts structured knowledge from SKILL.md files |
| **Knowledge Architecture** | Follows the "A is a B that C" definition pattern (genus + differentia) |
| **Knowledge Nodes** | 10-dimensional epistemic taxonomy (Heuristic, AntiPattern, PreFlightCheck, etc.) |
| **OWL 2 Serialization** | Outputs valid OWL 2 ontologies in RDF/Turtle format |
| **SHACL Validation** | Constitutional gatekeeper ensures logical validity before write |
| **State Machines** | Skills can define preconditions, postconditions, and failure handlers |
| **Security Pipeline** | Defense-in-depth: regex patterns + LLM review for malicious content |
| **Static Linting** | Detects dead states, circular deps, duplicate intents |
| **Drift Detection** | Semantic diff between ontology versions |

---

## What gets compiled

Every skill is extracted with:

- **Identity**: `nature`, `genus`, `differentia` (Knowledge Architecture)
- **Intents**: What user intentions this skill resolves
- **Requirements**: Dependencies (EnvVar, Tool, Hardware, API, Knowledge)
- **Knowledge Nodes**: Epistemic knowledge (8-12 nodes per skill)
- **Execution Payload**: Optional code to execute
- **State Transitions**: `requiresState`, `yieldsState`, `handlesFailure`
- **Provenance**: `generatedBy` attestation (LLM model used)

---

## Components

| Component | Language | Description |
|-----------|----------|-------------|
| **ontoskills** | CLI | User-facing installer and manager |
| **OntoCore** | Python | Skill compiler for `SKILL.md` sources |
| **OntoMCP** | Rust | MCP server with 5 semantic tools (incl. search_intents) |
| **OntoStore** | GitHub repo | Official compiled skill store |
| `skills/` | Markdown | Human-authored source skills |
| `ontoskills/` | Turtle | Compiled ontology artifacts |
---

## Use cases

| Use Case | How OntoSkills Help |
|----------|---------------------|
| **Enterprise AI Agents** | Deterministic skill selection via SPARQL queries |
| **Edge Deployment** | Smaller models query large skill ecosystems |
| **Multi-Agent Systems** | Shared ontology as coordination layer |
| **Compliance & Audit** | Every skill carries attestation and content hash |
| **Skill Marketplaces** | OntoStore and third-party stores enable plug-and-play distribution |

---

## Next steps

- **[Getting Started](/getting-started/)** — Install and compile your first skill
- **[CLI](/cli/)** — Learn the managed command surface
- **[OntoStore](/ontostore/)** — Browse installable store skills
- **[OntoCore](/ontocore/)** — Install compiler for custom skills
- **[Store](/store/)** — Learn how official and third-party stores work
- **[Architecture](/architecture/)** — Deep dive into the system design
- **[Knowledge Extraction](/knowledge-extraction/)** — Understanding knowledge nodes
- **[Troubleshooting](/troubleshooting/)** — Fix common install and runtime issues
- **[Roadmap](/roadmap/)** — See what's coming next

---

## Links

- [GitHub Repository](https://github.com/mareasw/ontoskills)
- [OntoStore](https://github.com/mareasw/ontostore)
- [Philosophy](https://github.com/mareasw/ontoskills/blob/main/PHILOSOPHY.md)
