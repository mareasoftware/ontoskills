---
title: MCP Bootstrap
description: One-command MCP setup for global and project-local AI clients
sidebar:
  order: 7
---

`ontoskills` can install `ontomcp` and wire it into supported MCP clients in one command.

## Quickstart

```bash
# Global by default
npx ontoskills install mcp --claude
npx ontoskills install mcp --codex --cursor

# Project-local only
npx ontoskills install mcp --cursor --vscode --project
```

## Scope model

- `--global`: configure the current user or machine
- `--project`: configure only the current repository/workspace

If you omit both flags, `ontoskills` uses `--global`.

## Supported clients

| Client | Global | Project | Bootstrap mode |
|--------|--------|---------|----------------|
| Claude Code | Yes | Yes | Native CLI command |
| Codex | Yes | Manual | Native CLI command |
| Qwen Code | Yes | Yes | Native CLI or `settings.json` fallback |
| Cursor | Yes | Yes | JSON file |
| VS Code | Yes | Yes | CLI for global, JSON file for project |
| Windsurf | Yes | Manual | JSON file |
| Antigravity | Best effort | Manual | Config detection or manual fallback |
| OpenCode | Yes | Yes | JSON file |

## What gets registered

Every client is configured against the same managed runtime:

```text
~/.ontoskills/bin/ontomcp
```

By default `ontomcp` reads compiled ontologies from:

```text
~/.ontoskills/ontologies
```

## Common commands

```bash
# Claude Code, global
ontoskills install mcp --claude

# Claude Code + Codex + Cursor globally
ontoskills install mcp --claude --codex --cursor

# Cursor and VS Code only for this repo
ontoskills install mcp --cursor --vscode --project

# Install runtime without touching any client
ontoskills install mcp
```

## Manual fallbacks

Some clients do not expose a stable project-local bootstrap flow. In those cases `ontoskills`:

1. installs `ontomcp`
2. tries the safest supported automation path
3. prints exact manual steps if the client still needs user action

This is intentional: the command should never block MCP installation just because one client needs a manual final step.
