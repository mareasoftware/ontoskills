---
title: Roadmap
description: Current roadmap for OntoSkills, OntoMCP, OntoCore, and registry distribution
---

> This roadmap reflects the current product direction, not the old phase labels.

## Platform Base ✅

**Status:** Complete

The compiler and runtime foundation is in place.

- [x] Natural language parsing with Claude
- [x] OWL 2 DL serialization (RDF/Turtle)
- [x] SHACL validation gatekeeper
- [x] Security audit pipeline
- [x] 156+ tests

## Product Distribution ✅

**Status:** In place

The user-facing `ontoskills` CLI now manages installation of `ontomcp`, `ontocore`, registry sources, source imports, and skill activation.

- [x] Managed home under `~/.ontoskills/`
- [x] Install/update flows for MCP and compiler
- [x] Enable/disable and index rebuild
- [x] Raw source import and local compilation
- [x] Official registry built in by default

## Official Registry ✅

**Status:** Live

The official compiled registry is published as a GitHub repository and is installable from the CLI without manual setup.

- [x] Registry index and package manifests
- [x] Remote install and enable flow
- [x] Demo package published
- [x] Third-party registry support via `registry add-source`

## Release Packaging 🔨

**Status:** In Progress

The runtime and compiler are being prepared for public distribution as release artifacts.

- [ ] GitHub Releases for `ontomcp`
- [ ] GitHub Releases / wheel for `ontocore`
- [ ] npm distribution of `ontoskills`
- [ ] Stable asset naming and version checks

## Future: OntoSkills Agent 💡

**Status:** Planned

The longer-term product layer will use OntoSkills as the knowledge backbone for an autonomous agent experience.

- [ ] Agent architecture design
- [ ] Multi-agent collaboration
- [ ] Knowledge graph reasoning
- [ ] Production deployment

---

## Track Progress

Follow development on [GitHub](https://github.com/mareasoftware/ontoskills).

Have ideas? [Open an issue](https://github.com/mareasoftware/ontoskills/issues).
