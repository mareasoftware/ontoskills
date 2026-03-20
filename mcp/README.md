# OntoMCP

Rust-based local MCP runtime for OntoSkills.

The public documentation now lives under `docs/`:

- [General MCP guide](../docs/mcp.md)
- [Claude Code guide](../docs/mcp-claude-code.md)
- [Codex guide](../docs/mcp-codex.md)

This folder stays focused on the runtime implementation itself.

## Run From Source

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

## Test

```bash
cargo test --manifest-path mcp/Cargo.toml
```

## Install As A Product Runtime

```bash
npx ontoskills install mcp
```
