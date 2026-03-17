---
title: What is OntoClaw?
description: MCP server for deterministic AI agents with ontoskills
---

# What is OntoClaw?

OntoClaw is an **MCP server** that exposes **ontoskills** — structured, queryable knowledge for AI agents.

## The Paradigm Shift

| Traditional Skills | Ontoskills |
|-------------------|------------|
| LLM reads markdown files | LLM queries the graph |
| O(n) text scanning | O(1) indexed lookup |
| Non-deterministic interpretation | Deterministic responses |
| Stateless | Evolving ABox |
| Context rot | Precise answers |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   SKILL.md      │────▶│    Compiler     │────▶│   RDF/Turtle    │
│  (natural lang) │     │    (Phase 1)    │     │   (ontoskill)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   LLM Agent     │◀────│   MCP Server    │◀────│    Oxigraph     │
│  (Claude, etc)  │     │    (Phase 2)    │     │   (graph DB)    │
└────────┬────────┘     └─────────────────┘     └─────────────────┘
         │
         │ execute & report
         ▼
┌─────────────────┐
│  ABox Update    │
│ (knowledge      │
│  evolves)       │
└─────────────────┘
```

## Knowledge Components

### TBox (Terminology Box)
Stable concepts and classes. Changes rarely.

```
CanInstallPythonLib ≡ ∃requires.PythonInstalled
```

### RBox (Role Box)
Stable relations and properties. Changes rarely.

```
requires ⊆ dependsOn
```

### ABox (Assertion Box)
Mutable facts about the world. Changes frequently.

```
PythonInstalled(myMachine) → true/false
```

When the LLM executes an action and succeeds or fails, the ABox updates automatically.

## MCP Integration

OntoClaw implements the [Model Context Protocol](https://modelcontextprotocol.io/), enabling:

- **Claude Desktop** — Direct ontoskill queries
- **VSCode** — IDE integration
- **Custom agents** — Any MCP-compatible client

## Get Started

[Get Started](/getting-started/) with OntoClaw in minutes.

## Links

- [GitHub Repository](https://github.com/mareasoftware/ontoclaw)
- [Roadmap](/roadmap/)
