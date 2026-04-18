---
title: CLI Reference
description: Complete command reference for the ontoskills CLI
sidebar:
  order: 10
---

`ontoskills` is the product entrypoint. It installs and manages the runtime, compiler, store skills, and local state under `~/.ontoskills/`.

---

## Quickstart

```bash
# First-time setup
npx ontoskills install mcp

# After bootstrap, use directly
ontoskills --help
```

---

## Installation commands

### `install mcp`

Install the MCP runtime, or install it and bootstrap one or more MCP clients in one command.

```bash
ontoskills install mcp
ontoskills install mcp --claude
ontoskills install mcp --codex --cursor
ontoskills install mcp --cursor --vscode --project
```

Creates:
- `~/.ontoskills/bin/ontomcp` — the MCP server binary
- `~/.ontoskills/ontologies/core.ttl` — core ontology (downloaded from `ontoskills.sh`)
- `~/.ontoskills/state/` — lockfiles and metadata

Supported flags:

| Flag | Meaning |
|------|---------|
| `--global` | Configure user-wide MCP settings (default) |
| `--project` | Configure only the current repository/workspace |
| `--all-clients` | Bootstrap every supported MCP client |
| `--codex` | Configure Codex |
| `--claude` | Configure Claude Code |
| `--qwen` | Configure Qwen Code |
| `--cursor` | Configure Cursor |
| `--vscode` | Configure VS Code |
| `--windsurf` | Configure Windsurf |
| `--antigravity` | Configure Antigravity (best effort/manual fallback) |
| `--opencode` | Configure OpenCode |

When a client cannot be configured fully, `ontoskills` still installs `ontomcp` and prints exact manual steps.

### `install core`

Install the OntoCore compiler (optional).

```bash
ontoskills install core
```

Requires Python 3.10+. Creates `~/.ontoskills/core/` with the compiler runtime.

---

## Store commands

### `search <query>`

Search for skills in OntoStore.

```bash
ontoskills search hello
ontoskills search pdf
ontoskills search "office document"
```

### `install <package-id>`

Install a skill from OntoStore.

```bash
ontoskills install mareasw/greeting/hello
ontoskills install obra/superpowers/test-driven-development
```

The package ID supports multi-level resolution:

| Level | Example | Installs |
|-------|---------|----------|
| **Author** | `anthropics` | All packages from that author |
| **Package** | `obra/superpowers` | All skills in that package |
| **Skill** | `obra/superpowers/test-driven-development` | Single skill (with dependency check) |

| Flag | Meaning |
|------|---------|
| `--with-embeddings` | Download per-skill embedding files (intents.json) for semantic search |

### `enable <package-id>`

Re-enable a disabled skill for the MCP runtime.

```bash
ontoskills enable mareasw/greeting/hello
```

Skills are enabled by default on install. Use this to re-enable a previously disabled skill.

### `disable <package-id>`

Disable a skill without removing it.

```bash
ontoskills disable mareasw/greeting/hello
```

### `remove <package-id>`

Remove an installed skill.

```bash
ontoskills remove mareasw/greeting/hello
```

### `list-installed`

List all installed skills.

```bash
ontoskills list-installed
```

---

## Store source commands

### `store list`

List configured skill stores.

```bash
ontoskills store list
```

### `store add-source <name> <url>`

Add a third-party skill store.

```bash
ontoskills store add-source acme https://example.com/skills/index.json
```

---

## Import commands

### `import-source <url>`

Import a raw Git repository containing SKILL.md files.

```bash
ontoskills import-source https://github.com/user/skill-repo
```

Imported skills are stored under `~/.ontoskills/skills/author/` and compiled to `~/.ontoskills/ontologies/author/`.

---

## Compiler commands

These commands require `ontocore` to be installed.

### `init-core`

Initialize the core ontology.

```bash
ontoskills init-core
```

Creates `core.ttl` with base classes and properties.

### `compile [skill]`

Compile skills to ontology modules.

```bash
# Compile all skills
ontoskills compile

# Compile specific skill
ontoskills compile my-skill

# With options
ontoskills compile --force          # Bypass cache
ontoskills compile --dry-run        # Preview only
ontoskills compile --skip-security  # Skip LLM security review
ontoskills compile -v               # Verbose output
```

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `skills/`) |
| `-o, --output` | Output directory (default: `ontoskills/`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip LLM security review |
| `-f, --force` | Force recompilation |
| `-y, --yes` | Skip confirmation prompts |
| `-v, --verbose` | Debug logging |
| `-q, --quiet` | Suppress progress output |

### `query <sparql>`

Run a SPARQL query against compiled ontologies.

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills query "SELECT ?intent WHERE { ?skill oc:resolvesIntent ?intent }"
```

### `list-skills`

List all compiled skills.

```bash
ontoskills list-skills
```

### `lint <ttl-path>`

Run structural lint checks on a compiled TTL file.

```bash
ontoskills lint ontoskills/index.ttl
ontoskills lint ontoskills/index.ttl --errors-only
ontoskills lint ontoskills/index.ttl --json
```

Checks for dead states, circular dependencies, duplicate intents, unreachable skills, and workflow cycles.

| Option | Description |
|--------|-------------|
| `--errors-only` | Only show errors (suppress warnings and info) |
| `--json` | Output results as JSON |

Exit codes: 0 if clean, 1 if errors found.

### `security-audit`

Run security audit on all skills.

```bash
ontoskills security-audit
```

---

## Management commands

### `update [target]`

Update a component or skill.

```bash
ontoskills update mcp
ontoskills update core
ontoskills update obra/superpowers/test-driven-development
```

### `rebuild-index`

Rebuild the ontology index.

```bash
ontoskills rebuild-index
```

### `doctor`

Diagnose installation issues.

```bash
ontoskills doctor
```

Checks:
- MCP binary exists and is executable
- Core ontology is valid
- Environment variables are set
- Index is consistent

---

## Uninstall

### `uninstall --all`

Remove the entire managed home.

```bash
ontoskills uninstall --all
```

**Warning:** This deletes everything under `~/.ontoskills/`.

---

## Managed home structure

```text
~/.ontoskills/
├── bin/
│   └── ontomcp           # MCP server binary
├── core/                  # Compiler runtime (if installed)
├── ontologies/            # Compiled ontology packages
│   ├── core.ttl
│   ├── index.ttl
│   ├── system/            # System-level files
│   │   ├── index.enabled.ttl  # Enabled skills manifest
│   │   └── embeddings/        # Semantic search artifacts
│   │       ├── model.onnx     # ONNX embedding model (~90MB)
│   │       └── tokenizer.json # HuggingFace tokenizer
│   └── author/            # Installed skill packages
│       └── <author>/<pkg>/<skill>/
│           ├── ontoskill.ttl
│           └── intents.json   # Per-skill embeddings (optional, with --with-embeddings)
├── skills/                # Source skills
│   └── author/            # Imported repositories
└── state/                 # Lockfiles and metadata
    ├── registry.sources.json
    └── registry.lock.json
```

---

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | API key for compilation | Required for compiler |
| `ANTHROPIC_BASE_URL` | API base URL | `https://api.anthropic.com` |
| `ONTOSKILLS_HOME` | Managed home directory | `~/.ontoskills` |

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Skill not found |
| 4 | Security error |
| 5 | Validation error |
| 6 | Network error |

---

## See also

- [Getting Started](/docs/getting-started/) — First-time setup tutorial
- [OntoCore](/docs/ontocore/) — Compiler reference
- [Store](/docs/store/) — Package management details
- [Troubleshooting](/docs/troubleshooting/) — Common issues
