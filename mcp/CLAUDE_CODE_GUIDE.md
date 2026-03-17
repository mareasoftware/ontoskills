# OntoClaw MCP With Claude Code

## Overview

This guide explains how to:

- build the OntoClaw MCP server
- run it manually
- register it in Claude Code
- verify that Claude Code sees it as connected
- understand where ontology data comes from

The OntoClaw MCP server is a **local stdio server**.
It is not an HTTP service and it does not listen on a TCP port.

Claude Code starts it as a subprocess and talks to it over `stdin/stdout`.

## Prerequisites

You need:

- Rust toolchain installed
- Claude Code installed
- a compiled ontology directory such as `ontoskills/`

The server reads compiled `.ttl` files, not raw `SKILL.md`.

## Build

From the repository root:

```bash
cargo build --manifest-path mcp/Cargo.toml
```

Or run tests and build:

```bash
cargo test --manifest-path mcp/Cargo.toml
cargo build --manifest-path mcp/Cargo.toml
```

The binary will be available at:

```text
./mcp/target/debug/ontoclaw-mcp
```

## Run Manually

Simple run:

```bash
cargo run --manifest-path mcp/Cargo.toml
```

This works when `ontoskills/` can be auto-discovered from the current directory or its parents.

Explicit ontology root:

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

Direct binary:

```bash
./mcp/target/debug/ontoclaw-mcp --ontology-root ./ontoskills
```

## How Ontology Root Resolution Works

The server resolves ontology input in this order:

1. `--ontology-root /path/to/ontoskills`
2. `ONTOCLAW_MCP_ONTOLOGY_ROOT=/path/to/ontoskills`
3. auto-discovery of `ontoskills/` from the current directory and its parents
4. fallback to `./ontoskills`

## Register In Claude Code

Recommended command from the repository root:

```bash
claude mcp add --scope local ontoclaw \
  /absolute/path/to/ontoclaw/mcp/target/debug/ontoclaw-mcp \
  -- --ontology-root /absolute/path/to/ontoclaw/ontoskills
```

If you want to rely on auto-discovery:

```bash
claude mcp add --scope local ontoclaw \
  /absolute/path/to/ontoclaw/mcp/target/debug/ontoclaw-mcp
```

Notes:

- `--scope local` stores the config only for the current project
- using the built binary is more reliable than wrapping with `cargo run`

## Verify Connection

Check one server:

```bash
claude mcp get ontoclaw
```

Expected output includes:

```text
Status: ✓ Connected
```

List all configured servers:

```bash
claude mcp list
```

You should see something like:

```text
ontoclaw: /absolute/path/to/ontoclaw/mcp/target/debug/ontoclaw-mcp ... ✓ Connected
```

## Remove Or Replace The Server

Remove it:

```bash
claude mcp remove -s local ontoclaw
```

Re-add it with a different ontology root if needed.

## What Claude Code Uses

Once connected, Claude Code can call tools exposed by OntoClaw, including:

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

## Important Behavior

The server:

- discovers skills from compiled ontologies
- helps with semantic lookup and planning
- returns payloads

The server does **not** execute payloads.

Payload execution is delegated to the calling agent in its own environment.

## Troubleshooting

### Claude Code says `Failed to connect`

Check:

- the binary exists
- the ontology root exists
- the ontology directory contains `.ttl` files
- the registered command points to the built binary, not a stale path

Rebuild:

```bash
cargo build --manifest-path mcp/Cargo.toml
```

Then remove and re-add the MCP server in Claude Code.

### No ontology found

Run with an explicit path:

```bash
./mcp/target/debug/ontoclaw-mcp --ontology-root ./ontoskills
```

### I only have `SKILL.md`

You must compile first with the Python compiler.
The MCP server reads `.ttl`, not raw skill markdown.
