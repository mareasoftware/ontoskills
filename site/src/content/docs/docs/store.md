---
title: Store
description: OntoStore, third-party stores, and package lifecycle
sidebar:
  order: 14
---

OntoSkills uses a simple distribution model:

- **OntoStore** — built in by default
- **Third-party stores** — added explicitly
- **Source imports** — cloned and compiled locally

---

## Store types

### OntoStore (built-in)

OntoStore ships with the product. No configuration needed.

```bash
ontoskills search hello
ontoskills install mareasw/greeting/hello
```

Skills are automatically enabled on install.

**Package ID format:** `owner/repo/skill`

Example: `mareasw/office/xlsx`

### Third-party stores

Opt-in stores maintained by other teams or communities.

```bash
# Add a store
ontoskills store add-source acme https://example.com/index.json

# List configured stores
ontoskills store list
```

Third-party packages use the same ID format and install flow.

### Source imports

Raw repositories with `SKILL.md` files, compiled locally.

```bash
ontoskills import-source https://github.com/user/skill-repo
```

- Cloned to `~/.ontoskills/skills/vendor/`
- Compiled to `~/.ontoskills/ontologies/vendor/`
- Requires OntoCore compiler installed

---

## Package lifecycle

### Install

```bash
ontoskills install mareasw/office/xlsx
```

Downloads compiled `.ttl` from the store and places it in `~/.ontoskills/ontologies/`.

### Enable / Disable

```bash
ontoskills disable mareasw/office/xlsx
ontoskills enable mareasw/office/xlsx
```

Skills are enabled by default on install. Use `disable` to hide a skill from OntoMCP without removing it. Use `enable` to re-enable.

### Update

```bash
ontoskills update mareasw/office/xlsx
```

Fetches the latest version from the store.

### Remove

```bash
ontoskills remove mareasw/office/xlsx
```

Deletes the package from local storage.

### Rebuild index

```bash
ontoskills rebuild-index
```

Regenerates `~/.ontoskills/ontologies/system/index.enabled.ttl` from all enabled skills. Run this if you manually modified `.ttl` files.

---

## CLI commands reference

| Command | Description |
|---------|-------------|
| `search <query>` | Search skills across all stores |
| `install <package-id>` | Install a compiled package |
| `enable <package-id>` | Enable for MCP runtime |
| `disable <package-id>` | Disable from MCP runtime |
| `remove <package-id>` | Uninstall package |
| `update <package-id>` | Update to latest version |
| `list-installed` | List all installed packages |
| `store list` | List configured stores |
| `store add-source <name> <url>` | Add third-party store |
| `import-source <url>` | Import and compile source repo |
| `rebuild-index` | Regenerate enabled index |
| `uninstall --all` | Remove entire managed home |

---

## Local layout

```text
~/.ontoskills/
├── bin/                    # Managed binaries
│   └── ontomcp
├── core/                   # Compiler runtime (optional)
├── ontologies/             # Compiled ontologies
│   ├── core.ttl
│   ├── index.ttl
│   ├── system/             # System-level files
│   │   └── index.enabled.ttl  # Enabled skills manifest
│   └── */ontoskill.ttl
├── skills/                 # Source skills
│   └── vendor/             # Imported repositories
└── state/                  # Metadata and locks
    ├── registry.sources.json
    └── registry.lock.json
```

---

## Store index format

Stores serve a static `index.json`:

```json
{
  "packages": [
    {
      "package_id": "mareasw/office",
      "manifest_url": "./packages/mareasw/office/package.json",
      "trust_tier": "verified"
    }
  ]
}
```

---

## Troubleshooting

### "Package not found"

- Check the package ID spelling
- Run `ontoskills search <query>` to discover available packages
- If using third-party store, verify it's configured: `ontoskills store list`

### "Skill not visible in MCP"

If a skill was disabled, re-enable it:

```bash
ontoskills enable mareasw/office/xlsx
ontoskills rebuild-index
```

### "Source import failed"

Ensure OntoCore is installed:

```bash
ontoskills install core
```

Then retry the import.

### "Index corrupted"

Rebuild from scratch:

```bash
ontoskills rebuild-index
```

---

## Practical rules

| Command | What it does |
|---------|--------------|
| `install mcp` | Installs the MCP runtime |
| `install core` | Installs the compiler |
| `install <id>` | Installs a compiled package |
| `import-source <url>` | Clones and compiles source |
| `enable` / `disable` | Controls MCP visibility |
| OntoStore | Built-in, never needs `store add-source` |
