# OntoSkills Registry Blueprint

This directory mirrors the structure of the official registry repository.

Use it as:
- the source layout to publish in the registry repo
- the reference for package manifests
- the canonical example for compiled OntoSkill distribution

The official registry is built into `ontoskills` by default. Users should not have to add it manually.

`registry add-source` is only for additional registries maintained by third parties.

## User Workflow

For a normal end user, the registry flow is:

```bash
npx ontoskills search hello
npx ontoskills install marea.greeting/hello
npx ontoskills enable marea.greeting/hello
```

For a third-party registry:

```bash
npx ontoskills registry add-source acme https://example.com/index.json
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
- writes compiled output into `~/.ontoskills/ontoskills/vendor/<package_id>`
- leaves imported skills disabled until explicitly enabled

## Registry Repo Layout

```text
registry/
  README.md
  index.json
  packages/
    marea.greeting/
      package.json
      hello/
        ontoskill.ttl
    marea.office/
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

Compiled registry packages contain prebuilt `.ttl` artifacts.

Required manifest fields:
- `package_id`
- `version`
- `trust_tier`
- `modules`
- `skills`

Each exported skill should be installable and activatable independently.

## Registry Index

The registry index is a static JSON file listing installable packages.

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

This means the registry can be published as a plain GitHub repository plus raw file URLs. No custom backend is required for v1.

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
