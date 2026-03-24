# OntoSkills Registry Blueprint

This directory mirrors the structure of the official registry repository.

Use it as:
- the source layout to publish in the registry repo
- the reference for package manifests
- the canonical example for compiled OntoSkill distribution

The official store is built into `ontoskills` by default. Users should not have to add it manually.

`store add-source` is only for additional stores maintained by third parties.

## User Workflow

For a normal end user, the store flow is:

```bash
npx ontoskills search hello
npx ontoskills install mareasw/greeting/hello
```

Skills are enabled by default on install.

For a third-party store:

```bash
npx ontoskills store add-source acme https://example.com/index.json
npx ontoskills search spreadsheet
```

For a raw source repository:

```bash
npx ontoskills import-source https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

That source import flow:
- clones or copies the repository into `~/.ontoskills/skills/vendor/<slug>`
- discovers every `SKILL.md`
- compiles the discovered skills locally
- writes compiled output into `~/.ontoskills/ontologies/vendor/<package_id>`
- enables imported skills by default

## Store Repo Layout

```text
registry/
  README.md
  index.json
  packages/
    mareasw/greeting/
      package.json
      hello/
        ontoskill.ttl
    mareasw/office/
      package.json
      office/
        ontoskill.ttl
        public/
          docx/ontoskill.ttl
          pdf/ontoskill.ttl
          pptx/ontoskill.ttl
          xlsx/ontoskill.ttl
```

## Package Model

Compiled store packages contain prebuilt `.ttl` artifacts.

Required manifest fields:
- `package_id`
- `version`
- `trust_tier`
- `modules`
- `skills`

Each exported skill should be installable and activatable independently.

## Store Index

The store index is a static JSON file listing installable packages.

```json
{
  "packages": [
    {
      "package_id": "mareasw/office",
      "manifest_url": "https://example.invalid/packages/mareasw/office/package.json",
      "trust_tier": "verified"
    }
  ]
}
```

This means the store can be published as a plain GitHub repository plus raw file URLs. No custom backend is required for v1.

## Resolution Rules

- Canonical runtime identity is `package_id/skill_id`
- Short ids are accepted only as lookup convenience
- Ambiguous short ids resolve with precedence:
  - `local > verified > trusted > community`

## Activation Rules

- install unit: package
- activation unit: skill
- enabling a skill auto-enables required `extends` / `dependsOn`
- skills are enabled by default on install/import
