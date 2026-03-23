---
title: Store
description: OntoStore, third-party stores, and package lifecycle in OntoSkills
---

OntoSkills uses a simple distribution model:

- OntoStore is built in by default
- third-party stores can be added explicitly
- raw source repositories are imported separately and compiled locally

The user-facing CLI is `ontoskills`.

For a live searchable view of OntoStore, use the dedicated marketplace page:

- [Open the live marketplace](/explore/)

## Store Types

### OntoStore

OntoStore ships with the product. It does not need `store add-source`.

Use it when you want published packages maintained by the OntoSkills project:

```bash
npx ontoskills search hello
npx ontoskills install mareasw/greeting/hello
npx ontoskills enable mareasw/greeting/hello
```

### Third-Party Stores

Third-party stores are opt-in. Add them when another team or community maintains a separate catalog:

```bash
ontoskills store add-source acme https://example.com/index.json
ontoskills store list
```

These sources are discoverable by `ontoskills search` and can be installed like OntoStore, but they are not built in.

### Raw Source Imports

Raw source repositories contain `SKILL.md` files and are compiled locally.

```bash
ontoskills import-source https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

Source imports are cloned into `~/.ontoskills/skills/vendor/` and compiled outputs are written to `~/.ontoskills/ontoskills/vendor/`.

## Skill Lifecycle

### Install

Install compiled packages from a store:

```bash
ontoskills install mareasw/greeting/hello
```

### Enable and Disable

Enable or disable installed skills:

```bash
ontoskills enable mareasw/greeting/hello
ontoskills disable mareasw/greeting/hello
```

Enabled skills are the ones exposed to OntoMCP.

### Update

Update installed components explicitly:

```bash
ontoskills update mcp
ontoskills update core
ontoskills update mareasw/greeting/hello
```

### Rebuild Index

Rebuild the local store state and enabled index:

```bash
ontoskills rebuild-index
```

### Remove

Remove a package or skill:

```bash
ontoskills remove mareasw/greeting/hello
```

### Uninstall Everything

Remove the entire managed user home:

```bash
ontoskills uninstall --all
```

This removes the whole `~/.ontoskills/` tree, including installed binaries, compiled ontologies, locks, caches, and any managed compiler install.

## Local Layout

The managed home is organized like this:

```text
~/.ontoskills/
  bin/
  core/
  ontoskills/
  skills/
  state/
```

- `bin/` stores managed binaries such as `ontomcp`
- `core/` stores the managed compiler install, if present
- `ontoskills/` stores compiled ontology artifacts
- `skills/` stores imported source repositories
- `state/` stores lockfiles, store configuration, and cache metadata

## Practical Rules

- `install mcp` installs the runtime
- `install core` installs the compiler
- `install <qualified-skill-id>` installs a compiled package from a store
- `import-source <repo-or-path>` clones and compiles a raw source repository
- `enable` and `disable` control what OntoMCP sees
- OntoStore is built in, so it should not be added manually
