---
title: Marketplace
description: Search, install, and enable skills from the official registry
---

# Marketplace

The OntoSkills marketplace is the install surface for published, compiled skills.

It is backed by the official registry and exposed in two places:

- the homepage marketplace section
- the dedicated live page at [`/explore/`](/explore/)

## Quick Example

```bash
ontoskills search xlsx
ontoskills install marea.office/xlsx
ontoskills enable marea.office/xlsx
```

## Qualified IDs

Marketplace installs use qualified ids:

```text
<package_id>/<skill_id>
```

Examples:

- `marea.greeting/hello`
- `marea.office/xlsx`
- `marea.office/docx`

## Install Flow

1. Search or browse the marketplace.
2. Copy the install command for the chosen skill.
3. Install the skill locally.
4. Enable it so OntoMCP exposes it.

```bash
ontoskills install marea.greeting/hello
ontoskills enable marea.greeting/hello
```

## Official vs Third-Party

The official marketplace is built in by default.

Third-party registries can be added separately:

```bash
ontoskills registry add-source acme https://example.com/index.json
```

Those registries become visible to `ontoskills search`, but the official registry remains the default discovery path.

## Live Marketplace Page

Use the interactive page for the full searchable catalog:

- [Open the live marketplace](/explore/)
