# OntoSkillRegistry Blueprint

This directory is the local blueprint for the official OntoSkillRegistry repo.

It defines:
- the registry index format
- the package manifest format
- the folder layout for official verified packages

The current compiler/runtime can already consume this model through:
- `ontoskill registry add-source`
- `ontoskill install`
- `ontoskill import-source`

## Layout

```text
registry/
  README.md
  index.json
  packages/
    marea.office/
      package.json
    marea.greeting/
      package.json
```

## Package Kind

### Compiled ontology package

Contains already compiled `.ttl` artifacts.

Required fields:
- `package_id`
- `version`
- `trust_tier`
- `modules`
- `skills`

### Direct source repository import

OntoClaw also supports importing a raw source repository directly from a local path or GitHub URL.

Example:

```bash
ontoclaw import-source-repo https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

The importer:
- clones or copies the repository
- discovers every `SKILL.md`
- compiles the discovered skills locally
- stores the source under `skills/vendor/<slug>`
- stores the compiled output under `ontoskills/vendor/<package_id>`
- keeps imported skills disabled by default

## Registry Index

The registry index is a JSON document listing installable packages.

```json
{
  "packages": [
    {
      "package_id": "marea.office",
      "manifest_url": "https://example.invalid/packages/marea.office/package.json",
      "trust_tier": "verified"
    }
  ]
}
```

## Trust Tiers

- `verified`
- `trusted`
- `community`
- `local`

## Resolution Rules

- Canonical runtime identity is `package_id/skill_id`
- Short ids are accepted only as lookup convenience
- Ambiguous short ids resolve with precedence:
  - `local > verified > trusted > community`

## Activation Rules

- install unit: package
- activation unit: skill
- enabling a skill auto-enables required `extends` / `dependsOn`
- imported skills stay disabled until explicitly enabled
