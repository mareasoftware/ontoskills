---
title: Roadmap
description: From core to autonomous agent — the OntoSkills ecosystem
sidebar:
  order: 15
---

> This roadmap evolves with the project.

## Phase 1: OntoCore

**Status:** Complete

The foundation. OntoCore is our neuro-symbolic core that transforms natural language skill definitions into validated OWL 2 DL ontologies.

- [x] Natural language parsing with Claude
- [x] OWL 2 DL serialization (RDF/Turtle)
- [x] SHACL validation gatekeeper
- [x] Security audit pipeline
- [x] 156+ tests

## Phase 2: OntoSkills

**Status:** Complete

The knowledge base. OntoSkills are the compiled, validated skills published from OntoCore — ready to be queried by agents.

- [x] Core skill library compilation
- [x] Public skill store
- [x] Skill versioning and updates
- [x] Dependency management

## Phase 3: OntoMCP

**Status:** Complete

The interface. OntoMCP exposes OntoSkills via the Model Context Protocol, giving any MCP-compatible agent instant access to structured knowledge with sub-millisecond SPARQL queries.

- [x] Rust MCP server with stdio transport
- [x] Oxigraph in-memory graph store
- [x] SPARQL 1.1 query interface
- [x] 5 semantic tools (search_skills, get_skill_context, evaluate_execution_plan, query_epistemic_rules, search_intents)
- [x] Claude Code integration

## Phase 4: OntoStore

**Status:** In Development

The marketplace. OntoStore is a centralized repository where teams can publish, discover, and share ontologies.

- [ ] Ontology store with search
- [ ] Version management
- [ ] Team collaboration features
- [ ] Community contributions

## Phase 5: OntoClaw

**Status:** Planned

The agent. An autonomous agent powered by structured knowledge — reasoning with precision, not hallucination.

- [ ] Agent architecture design
- [ ] Multi-agent collaboration
- [ ] Knowledge graph reasoning
- [ ] Production deployment

---

## Track progress

Follow development on [GitHub](https://github.com/mareasw/ontoskills).

Have ideas? [Open an issue](https://github.com/mareasw/ontoskills/issues).
