---
title: Roadmap
description: From compiler to autonomous agent — the OntoClaw ecosystem
---

> **We ship fast.** This roadmap evolves with the project.

## Phase 1: OntoCore ✅

**Status:** Complete

The foundation. OntoCore is our neuro-symbolic compiler that transforms natural language skill definitions into validated OWL 2 DL ontologies.

- [x] Natural language parsing with Claude
- [x] OWL 2 DL serialization (RDF/Turtle)
- [x] SHACL validation gatekeeper
- [x] Security audit pipeline
- [x] 150+ tests

## Phase 2: OntoSkills ✅

**Status:** Complete

The knowledge base. OntoSkills are the compiled, validated skills published from OntoCore — ready to be queried by agents.

- [x] Core skill library compilation
- [x] Public skill registry
- [x] Skill versioning and updates
- [x] Dependency management

## Phase 3: OntoMCP ✅

**Status:** Complete

The interface. OntoMCP exposes OntoSkills via the Model Context Protocol, giving any MCP-compatible agent instant access to structured knowledge.

- [x] Rust MCP server with stdio transport
- [x] Oxigraph in-memory graph store
- [x] SPARQL query interface
- [x] Runtime ABox updates
- [x] Claude Desktop integration

## Phase 4: OntoStore 🔨

**Status:** In Development

The marketplace. OntoStore is a centralized repository where teams can publish, discover, and share ontologies.

- [ ] Ontology registry with search
- [ ] Version management
- [ ] Team collaboration features
- [ ] Community contributions

## Phase 5: OntoClaw 💡

**Status:** Planned

The agent. OntoClaw joins the Claw family (OpenClaw, NanoClaw, ZeroClaw) as an autonomous agent powered by structured knowledge — reasoning with precision, not hallucination.

- [ ] Agent architecture design
- [ ] Multi-agent collaboration
- [ ] Knowledge graph reasoning
- [ ] Production deployment

---

## Track Progress

Follow development on [GitHub](https://github.com/mareasoftware/ontoclaw).

Have ideas? [Open an issue](https://github.com/mareasoftware/ontoclaw/issues).
