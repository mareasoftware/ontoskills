---
title: OntoStore
description: Search and install skills from the official OntoStore
sidebar:
  order: 13
slug: ontostore-guide
---

The OntoSkills marketplace is the install surface for published, compiled skills.

It is backed by OntoStore and exposed in two places:

- the homepage marketplace section
- the dedicated live page at [`/ontostore/`](/ontostore/)

## Quick example

```bash
ontoskills search xlsx
ontoskills install mareasw/office/xlsx
```

Skills are enabled by default on install.

## Qualified IDs

OntoStore installs use qualified ids:

```text
<package_id>/<skill_id>
```

Examples:

- `mareasw/greeting/hello`
- `obra/superpowers/test-driven-development`
- `obra/superpowers/systematic-debugging`

Install resolution supports three levels:

| Level | Example | Behavior |
|-------|---------|----------|
| Full | `obra/superpowers/test-driven-development` | Installs the exact skill |
| Package | `obra/superpowers` | Installs all skills in the package |
| Skill name | `test-driven-development` | Resolves the best match across stores |

## Install flow

1. Search or browse the OntoStore.
2. Copy the install command for the chosen skill.
3. Install the skill locally — it's enabled automatically.

```bash
ontoskills install mareasw/greeting/hello
```

If you previously disabled a skill and want to re-enable it:

```bash
ontoskills enable mareasw/greeting/hello
```

To install without generating embeddings:

```bash
ontoskills install mareasw/greeting/hello --no-embeddings
```

## Official vs third-party

The official marketplace is built in by default.

Third-party stores can be added separately:

```bash
ontoskills store add-source acme https://example.com/index.json
```

Those stores become visible to `ontoskills search`, but OntoStore remains the default discovery path.

## Live marketplace page

Use the interactive page for the full searchable catalog:

- [Open the live marketplace](/ontostore/)
