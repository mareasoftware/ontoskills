# OntoMCP

Rust-based local MCP (Model Context Protocol) server for the OntoClaw ecosystem.

**Status:** ✅ Ready

## Overview

OntoMCP is the **runtime layer** of OntoClaw. It loads compiled OntoSkills (`.ttl` files) into an in-memory RDF graph and provides blazing-fast SPARQL queries to AI agents via the Model Context Protocol.

```
┌─────────────────────────────────────────────────────────┐
│                      RUNTIME                            │
│                                                         │
│   Agent ◄──────► OntoMCP (Rust) ◄──────► .ttl files    │
│                                                         │
│   SKILL.md files DO NOT EXIST in the agent's context    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Scope

The MCP server is intentionally focused on:

- skill discovery from compiled ontologies
- semantic lookup by intent, dependency, and state transitions
- planning support from `requiresState` and `yieldsState`
- payload retrieval for the calling agent

The server does **not** execute skill payloads. Payload execution is delegated to the calling agent in its current runtime context.

## Transport

The server speaks MCP over `stdio`.

## Ontology Source

The server loads the global compiled ontology catalog from a directory containing `.ttl` files such as:

- `ontoclaw-core.ttl`
- `index.ttl`
- skill modules under nested `ontoskill.ttl` files

Default ontology root:

- auto-discovered by looking for `ontoskills/` from the current directory and its parents
- fallback: `./ontoskills`

Override with:

- `--ontology-root /path/to/ontoskills`
- or `ONTOCLAW_MCP_ONTOLOGY_ROOT=/path/to/ontoskills`

## Implemented Tools

- `list_skills`
- `find_skills_by_intent`
- `get_skill`
- `get_skill_requirements`
- `get_skill_transitions`
- `get_skill_dependencies`
- `get_skill_conflicts`
- `find_skills_yielding_state`
- `find_skills_requiring_state`
- `check_skill_applicability`
- `plan_from_intent`
- `get_skill_payload`

## Why Rust?

- **Performance**: Sub-millisecond SPARQL queries for real-time agent interaction
- **Memory efficiency**: Compact in-memory graph representation
- **Safety**: Memory-safe by design, critical for production deployments
- **Concurrency**: Parallel query execution without GIL limitations

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   MCP Tool   │     │  SPARQL      │     │  RDF Graph   │
│   Interface  │────►│  Engine      │────►│  (In-Memory) │
│              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                                               │
                                               ▼
                                       ┌──────────────┐
                                       │  .ttl files  │
                                       │  (OntoSkills)│
                                       └──────────────┘
```

## Run

Simple run from repository root:

```bash
cargo run --manifest-path mcp/Cargo.toml
```

Explicit path when needed:

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

## Claude Code Integration

You can register the OntoClaw MCP server in Claude Code using the local stdio transport.

Example from the repository root:

```bash
claude mcp add ontoclaw -- \
  cargo run --manifest-path /absolute/path/to/ontoclaw/mcp/Cargo.toml -- \
  --ontology-root /absolute/path/to/ontoclaw/ontoskills
```

Or, if you want to rely on auto-discovery of `ontoskills/`:

```bash
claude mcp add ontoclaw -- \
  cargo run --manifest-path /absolute/path/to/ontoclaw/mcp/Cargo.toml
```

After registration, Claude Code can call tools such as:

- `ontoclaw.list_skills`
- `ontoclaw.find_skills_by_intent`
- `ontoclaw.get_skill`
- `ontoclaw.plan_from_intent`
- `ontoclaw.get_skill_payload`

For a full step-by-step guide, see [CLAUDE_CODE_GUIDE.md](CLAUDE_CODE_GUIDE.md).

## Manual MCP Smoke Test

If you want to verify the protocol directly without a client, you can run the server and send MCP `initialize`, `tools/list`, and `tools/call` messages over `stdio`.

The simplest maintained verification path is:

```bash
cd mcp
cargo test
```

Current Rust test coverage includes:

- intent lookup
- payload lookup
- planning with preparatory skills
- planner preference for direct skills over setup-heavy alternatives

## Related Components

| Component | Language | Description |
|-----------|----------|-------------|
| **OntoCore** | Python | Design-time compiler |
| **OntoMCP** | Rust | Runtime server (this) |
| **OntoStore** | TBD | Skill registry (planned) |
| **OntoClaw** | Python/Rust | Enterprise AI agent (planned) |

---

*Part of the [OntoClaw ecosystem](../README.md).*
