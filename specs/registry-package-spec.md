# Registry Package Spec

This document defines the current compiled package format consumed by the OntoClaw registry pipeline.

## Common Fields

All package manifests use `package.json`.

Required common fields:
- `package_id`
- `version`
- `trust_tier`
- `skills`

Optional common fields:
- `core_version`
- `source`
- `checksum`

## Skill Entry

Each exported skill is described as:

```json
{
  "id": "xlsx",
  "path": "office/public/xlsx/ontoskill.ttl",
  "default_enabled": false,
  "aliases": ["excel", "spreadsheet"]
}
```

Rules:
- `id` is the short skill id
- `path` is package-relative
- runtime canonical identity becomes `package_id/id`
- `default_enabled` controls initial install state
- `aliases` are lookup conveniences only

## Ontology Package

An ontology package distributes compiled TTL files.

Required additional field:
- `modules`

## Registry Index Spec

The registry index is a JSON file listing installable packages.

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

## Runtime Semantics

- install unit: package
- enable unit: skill
- exact qualified id always wins
- short id lookup precedence is:
  - `local > verified > trusted > community`

## Direct Source Repository Import

OntoClaw supports direct raw repository import outside the compiled registry.

Expected behavior:
- accept a local path or GitHub URL
- clone/copy the repository
- discover all `SKILL.md` files
- compile them locally
- store the source under `skills/vendor/<slug>`
- store the compiled output under `ontoskills/vendor/<package_id>`
- keep imported skills disabled by default
