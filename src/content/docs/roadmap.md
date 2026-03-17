---
title: Roadmap
description: OntoClaw development phases and future direction
---

# Roadmap

> **Note:** We ship fast. This roadmap is mutable and changes frequently.

## Phase 1: Compiler ✅

**Status:** Complete

Transform `SKILL.md` files into validated OWL 2 DL ontologies.

- [x] Natural language parsing
- [x] OWL 2 DL serialization (RDF/Turtle)
- [x] SHACL validation pipeline
- [x] Security audit layer

## Phase 2: MCP Server 🔨

**Status:** In Development

Expose ontoskills via the Model Context Protocol.

- [ ] Rust MCP server with stdio transport
- [ ] Oxigraph in-memory graph store
- [ ] SPARQL query interface
- [ ] ABox runtime updates
- [ ] Claude Desktop integration

## Phase 3: OntoStore 💡

**Status:** Planned

Centralized repository for ontoskills.

- [ ] Ontoskill registry
- [ ] Version management
- [ ] Dependency resolution
- [ ] Community contributions

## Phase 4+: Ecosystem 🔮

**Status:** Exploratory

Broader ecosystem integration.

- [ ] VSCode extension
- [ ] Multi-agent collaboration
- [ ] Shared ABox between agents
- [ ] Cross-platform ontoskill sharing
- [ ] ??? — We're still exploring

---

## Track Progress

Follow development on [GitHub](https://github.com/mareasoftware/ontoclaw).

Have ideas? [Open an issue](https://github.com/mareasoftware/ontoclaw/issues) or join the discussion.
