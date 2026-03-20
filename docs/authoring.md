---
title: Skill Authoring
description: Write, import, and compile custom source skills
---

# Skill Authoring

OntoSkills supports two ways to work with source skills:

- author a local `SKILL.md`
- import a repository containing one or more `SKILL.md` files

## Local Authoring

Typical flow:

```bash
ontoskills install core
ontoskills init-core
ontoskills compile
```

## Import A Source Repository

If a repository contains raw source skills, import and compile it locally:

```bash
ontoskills import-source-repo https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

The importer:

- clones or copies the repository
- discovers `SKILL.md` files
- compiles them locally
- writes the compiled outputs into the managed ontology home

## After Compilation

Compiled skills still follow the same runtime lifecycle:

```bash
ontoskills enable <qualified-id>
ontoskills disable <qualified-id>
```
