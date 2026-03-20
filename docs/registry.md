---
title: Registry
description: Official registry, third-party registries, and package lifecycle in OntoSkills
---

# Registry

OntoSkills uses a simple distribution model:

- the official registry is built in by default
- third-party registries can be added explicitly
- raw source repositories are imported separately and compiled locally

The user-facing CLI is `ontoskills`.

## Registry Types

### Official Registry

The official registry ships with the product. It does not need `registry add-source`.

Use it when you want published packages maintained by the OntoSkills project:

```bash
npx ontoskills search hello
npx ontoskills install marea.greeting/hello
npx ontoskills enable marea.greeting/hello
```

### Third-Party Registries

Third-party registries are opt-in. Add them when another team or community maintains a separate catalog:

```bash
ontoskills registry add-source acme https://example.com/index.json
ontoskills registry list
```

These sources are discoverable by `ontoskills search` and can be installed like the official registry, but they are not built in.

### Raw Source Imports

Raw source repositories contain `SKILL.md` files and are compiled locally.

```bash
ontoskills import-source-repo https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

Source imports are cloned into `~/.ontoskills/skills/vendor/` and compiled outputs are written to `~/.ontoskills/ontoskills/vendor/`.

## Skill Lifecycle

### Install

Install compiled packages from a registry:

```bash
ontoskills install marea.greeting/hello
```

### Enable and Disable

Enable or disable installed skills:

```bash
ontoskills enable marea.greeting/hello
ontoskills disable marea.greeting/hello
```

Enabled skills are the ones exposed to OntoMCP.

### Update

Update installed components explicitly:

```bash
ontoskills update mcp
ontoskills update core
ontoskills update marea.greeting/hello
```

### Rebuild Index

Rebuild the local registry state and enabled index:

```bash
ontoskills rebuild-index
```

### Remove

Remove a package or skill:

```bash
ontoskills remove marea.greeting/hello
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
- `state/` stores lockfiles, registry configuration, and cache metadata

## Practical Rules

- `install mcp` installs the runtime
- `install core` installs the compiler
- `install <qualified-skill-id>` installs a compiled package from a registry
- `import-source-repo <repo>` clones and compiles a raw source repository
- `enable` and `disable` control what OntoMCP sees
- the official registry is built in, so it should not be added manually

