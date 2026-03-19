---
title: Getting Started
description: Install and use OntoSkills to compile skills into ontologies
---

OntoSkills is currently in **Phase 4** development. OntoCore (compiler) and OntoMCP (server) are ready. OntoStore marketplace is in progress.

## Prerequisites

- **Python** 3.10+
- **pip** or **uv** package manager

## Installation

```bash
# Clone the repository
git clone https://github.com/mareasoftware/ontoskills.git
cd ontoskills

# Install core
cd core
pip install -e ".[dev]"
```

## CLI Commands

```bash
# Initialize core ontology with predefined states
ontoskills init-core

# Compile all skills to ontology
ontoskills compile

# Compile specific skill
ontoskills compile my-skill

# Query ontology with SPARQL
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"

# List all skills
ontoskills list-skills

# Run security audit
ontoskills security-audit
```

## Command Options

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `./skills/`) |
| `-o, --output` | Output file (default: `./ontoskills/skills.ttl`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip security checks (not recommended) |
| `-f, --force` | Force recompilation (bypass hash-based cache) |
| `--reason/--no-reason` | Apply OWL reasoning |
| `-v, --verbose` | Debug logging |

## MCP Server (Phase 3 — Ready)

OntoMCP exposes ontologies via the Model Context Protocol. Built in Rust for sub-millisecond SPARQL queries.

```bash
# Run the MCP server
cargo run --manifest-path mcp/Cargo.toml
```

### Available MCP Tools

| Tool | Purpose |
|------|---------|
| `list_skills` | List all available skills |
| `find_skills_by_intent` | Find skills matching a user intent |
| `get_skill` | Get full skill details by ID |
| `get_skill_requirements` | Get skill dependencies |
| `get_skill_transitions` | Get state transitions (requires/yields/handles) |
| `get_skill_dependencies` | Get skills this one depends on |
| `get_skill_conflicts` | Get skills that contradict this one |
| `find_skills_yielding_state` | Find skills that produce a state |
| `find_skills_requiring_state` | Find skills that need a state |
| `check_skill_applicability` | Check if skill can run |
| `plan_from_intent` | Generate execution plan from intent |
| `get_skill_payload` | Get execution code for a skill |

### Claude Code Integration

Register the MCP server with Claude Code:

```bash
claude mcp add ontoskills -- \
  cargo run --manifest-path /absolute/path/to/ontoskills/mcp/Cargo.toml
```

## What's Next?

- [Roadmap](/roadmap/) — See what's coming
- [GitHub](https://github.com/mareasoftware/ontoskills) — Contribute
