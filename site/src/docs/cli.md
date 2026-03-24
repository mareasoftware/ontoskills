---
title: CLI Reference
description: Complete command reference for the ontoskills CLI
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

## Installation Commands

### `install mcp`

Install the MCP runtime.

```bash
ontoskills install mcp
```

Creates:
- `~/.ontoskills/bin/ontomcp` — the MCP server binary
- `~/.ontoskills/ontologies/` — compiled ontology packages
- `~/.ontoskills/state/` — lockfiles and metadata

### `install core`

Install the OntoCore compiler (optional).

```bash
ontoskills install core
```

Requires Python 3.10+. Creates `~/.ontoskills/core/` with the compiler runtime.

---

## Store Commands

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
ontoskills install mareasw/office/xlsx
```

The package ID format is: `owner/repo/skill`

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

## Store Source Commands

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

## Import Commands

### `import-source <url>`

Import a raw Git repository containing SKILL.md files.

```bash
ontoskills import-source https://github.com/user/skill-repo
```

Imported skills are stored under `~/.ontoskills/skills/vendor/` and compiled to `~/.ontoskills/ontologies/vendor/`.

---

## Compiler Commands

These commands require `ontocore` to be installed.

### `init-core`

Initialize the core ontology.

```bash
ontoskills init-core
```

Creates `ontoskills-core.ttl` with base classes and properties.

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

### `security-audit`

Run security audit on all skills.

```bash
ontoskills security-audit
```

---

## Management Commands

### `update [target]`

Update a component or skill.

```bash
ontoskills update mcp
ontoskills update core
ontoskills update mareasw/office/xlsx
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

## Managed Home Structure

```text
~/.ontoskills/
├── bin/
│   └── ontomcp           # MCP server binary
├── core/                  # Compiler runtime (if installed)
├── ontologies/            # Compiled ontology packages
│   ├── ontoskills-core.ttl
│   ├── index.ttl
│   ├── system/            # System-level files
│   │   └── index.enabled.ttl  # Enabled skills manifest
│   └── */ontoskill.ttl
├── skills/                # Source skills
│   └── vendor/            # Imported repositories
└── state/                 # Lockfiles and metadata
    ├── registry.sources.json
    └── registry.lock.json
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | API key for compilation | Required for compiler |
| `ANTHROPIC_BASE_URL` | API base URL | `https://api.anthropic.com` |
| `ONTOSKILLS_HOME` | Managed home directory | `~/.ontoskills` |

---

## Exit Codes

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

## See Also

- [Getting Started](/getting-started/) — First-time setup tutorial
- [OntoCore](/ontocore/) — Compiler reference
- [Store](/store/) — Package management details
- [Troubleshooting](/troubleshooting/) — Common issues
