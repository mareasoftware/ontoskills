---
title: Getting Started
description: Set up OntoClaw and query your first ontoskill
---

# Getting Started

OntoClaw is currently in **Phase 2** development. Here's how to get started with what's available.

## Prerequisites

- **Rust** 1.70+ (for building from source)
- **Node.js** 18+ (for the compiler CLI)
- **Claude Desktop** (for MCP integration)

## Phase 1: Compiler

The compiler transforms `SKILL.md` files into RDF/Turtle ontologies.

### Installation

```bash
# Clone the repository
git clone https://github.com/mareasoftware/ontoclaw.git
cd ontoclaw

# Build the compiler
cargo build --release
```

### Usage

```bash
# Compile a skill definition
ontoclaw compile ./skills/SKILL.md --output ./ontoskills/
```

This produces:
- `ontoskills/skill.ttl` — OWL 2 DL ontology
- `ontoskills/skill.shacl.ttl` — SHACL shapes for validation

## Phase 2: MCP Server (In Progress)

The MCP server exposes ontoskills via the Model Context Protocol.

### Build Status

The MCP server is currently under active development. Track progress on [GitHub](https://github.com/mareasoftware/ontoclaw).

### Expected Usage

```bash
# Start the MCP server (coming soon)
ontoclaw-mcp --ontologies ./ontoskills/
```

### Claude Desktop Configuration

Once available, add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "ontoclaw": {
      "command": "ontoclaw-mcp",
      "args": ["--ontologies", "/path/to/ontoskills"]
    }
  }
}
```

## What's Next?

- [Roadmap](/roadmap/) — See what's coming
- [GitHub](https://github.com/mareasoftware/ontoclaw) — Contribute
