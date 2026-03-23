---
title: Getting Started
description: Install OntoSkills, OntoMCP, and OntoCore
---

OntoSkills ships as a product suite with three pieces:

- `ontoskills` - the user-facing CLI
- `ontomcp` - the local MCP runtime
- `ontocore` - the optional compiler for source skills

OntoStore is built in by default. Third-party stores can be added explicitly.

## Prerequisites

- **Node.js** 18+ for the `ontoskills` CLI
- **Git** for source imports
- Optional: **Python** 3.10+ if you install `ontocore`

## Installation

```bash
npx ontoskills install mcp
npx ontoskills install core
```

This creates a managed user home under `~/.ontoskills/` with:

- `bin/ontomcp`
- `core/` for the compiler runtime, if installed
- `ontoskills/` for compiled ontology packages
- `state/` for lockfiles and store metadata

## Common Commands

```bash
ontoskills init-core
ontoskills compile
ontoskills compile my-skill
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills list-skills
ontoskills security-audit
```

If you only want the runtime and the published skills, you do not need the compiler commands.

## Store Workflow

### Built-In OntoStore

OntoStore is already available to `ontoskills`. You can discover and install published skills without any extra setup.

```bash
npx ontoskills search hello
npx ontoskills install mareasw/greeting/hello
npx ontoskills enable mareasw/greeting/hello
```

### Third-Party Stores

```bash
ontoskills registry add-source acme https://example.com/index.json
ontoskills registry list
```

### Import Source Skills

Raw repositories containing `SKILL.md` files can be imported and compiled locally:

```bash
ontoskills import-source-repo https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

Imported source skills are stored under `~/.ontoskills/skills/vendor/` and compiled outputs land in `~/.ontoskills/ontoskills/vendor/`.

## MCP Server

OntoMCP exposes compiled ontologies via the Model Context Protocol.

```bash
npx ontoskills install mcp
```

The current public tool set is:

- `search_skills`
- `get_skill_context`
- `evaluate_execution_plan`
- `query_epistemic_rules`

Client-specific setup guides:

- [General MCP runtime](./mcp.md)
- [Claude Code guide](./mcp-claude-code.md)
- [Codex guide](./mcp-codex.md)

## What's Next?

- [CLI](/cli/) — Full command surface and product workflows
- [Marketplace](/marketplace/) — Search and install published skills
- [Compiler](/compiler/) — Install the optional compiler
- [Skill Authoring](/authoring/) — Import and compile source repositories
- [Store](/registry/) — Install, update, remove, and uninstall skills
- [Troubleshooting](/troubleshooting/) — Diagnose install and runtime issues
- [Roadmap](/roadmap/) — See what's coming
- [GitHub](https://github.com/mareasoftware/ontoskills) — Contribute
