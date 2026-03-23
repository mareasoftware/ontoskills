---
title: CLI
description: End-user command surface for the OntoSkills product
---

`ontoskills` is the product entrypoint. It installs and manages the runtime, compiler, store skills, and local state under `~/.ontoskills/`.

## Quickstart

```bash
npx ontoskills install mcp
```

After the bootstrap step, the persistent command is:

```bash
ontoskills
```

## Product Commands

### Install Components

```bash
ontoskills install mcp
ontoskills install core
```

### Install Store Skills

```bash
ontoskills search hello
ontoskills install mareasw/greeting/hello
ontoskills enable mareasw/greeting/hello
```

### Manage Runtime State

```bash
ontoskills disable mareasw/greeting/hello
ontoskills remove mareasw/greeting/hello
ontoskills rebuild-index
```

### Update Managed Components

```bash
ontoskills update mcp
ontoskills update core
ontoskills update marea/office/xlsx
```

### Inspect and Diagnose

```bash
ontoskills store list
ontoskills list-installed
ontoskills doctor
```

## Managed Home

Everything lives under:

```text
~/.ontoskills/
  bin/
  core/
  ontoskills/
  skills/
  state/
```

## Compiler Frontend

If `ontocore` is installed, `ontoskills` also fronts the most important authoring commands:

```bash
ontoskills init-core
ontoskills compile
ontoskills compile my-skill
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
ontoskills list-skills
ontoskills security-audit
```

## Uninstall

To remove the managed home entirely:

```bash
ontoskills uninstall --all
```
