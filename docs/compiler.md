---
title: Compiler
description: Install and use OntoCore for custom source skills
---

`ontocore` is the optional compiler that turns `SKILL.md` sources into validated ontology modules.

Most users do not need it to consume store skills. Install it when you want to write or import custom skills locally.

## Install

```bash
ontoskills install core
```

This adds a managed compiler runtime under:

```text
~/.ontoskills/core/
```

## Initialize The Core Ontology

```bash
ontoskills init-core
```

## Compile Skills

Compile the local tree:

```bash
ontoskills compile
```

Compile a single skill or subtree:

```bash
ontoskills compile office
ontoskills compile my-custom-skill
```

## Query The Local Graph

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
```

## Inspect Quality

```bash
ontoskills list-skills
ontoskills security-audit
```
