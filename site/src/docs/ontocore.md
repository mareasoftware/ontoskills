---
title: OntoCore Compiler
description: Install and use OntoCore for custom source skills
---

`ontocore` is the optional compiler that turns `SKILL.md` sources into validated OWL 2 ontology modules.

Most users don't need it — you only need OntoCore if you want to:
- Write custom skills from source
- Import and compile raw skill repositories
- Develop and test skills locally

---

## Installation

```bash
ontoskills install core
```

This creates a managed compiler runtime under:

```text
~/.ontoskills/core/
```

Requirements:
- **Python** 3.10+
- **Anthropic API key** (set `ANTHROPIC_API_KEY` env var)

---

## The Compilation Pipeline

```
SKILL.md → [Extract] → [Security] → [Serialize] → [SHACL] → ontoskill.ttl
```

| Stage | What Happens |
|-------|--------------|
| **Extract** | Claude reads SKILL.md and extracts structured knowledge |
| **Security** | Regex + LLM review for malicious content |
| **Serialize** | Pydantic models → RDF triples |
| **Validate** | SHACL shapes check logical validity |
| **Write** | Atomic write with backup |

If any stage fails, the skill is **not written**. The SHACL gatekeeper enforces constitutional rules.

---

## File Processing Rules

OntoCore processes files based on their type:

| Rule | Input | Output | Processing |
|------|-------|--------|------------|
| **A** | `SKILL.md` | `ontoskill.ttl` | LLM compilation |
| **B** | `*.md` (auxiliary) | `*.ttl` | LLM compilation as sub-skill |
| **C** | Other files | Direct copy | Asset (images, etc.) |

### Directory Mirroring

The output structure mirrors the input:

```text
skills/                          →    ontoskills/
├── office/                      →    ├── office/
│   ├── SKILL.md                 →    │   ├── ontoskill.ttl
│   ├── planning.md              →    │   ├── planning.ttl
│   └── review.md                →    │   └── review.ttl
└── pdf/                         →    └── pdf/
    ├── SKILL.md                 →        ├── ontoskill.ttl
    └── diagram.png              →        └── diagram.png
```

### Sub-Skills

Auxiliary `.md` files in a skill directory become **sub-skills**:

- They automatically `extend` the parent skill
- They inherit parent context during extraction
- They get qualified IDs: `package/parent/child`

---

## CLI Commands

### Initialize Core Ontology

```bash
ontoskills init-core
```

Creates `ontoskills-core.ttl` with the base TBox ontology (classes, properties, state definitions).

### Compile Skills

```bash
# Compile all skills in skills/
ontoskills compile

# Compile a specific skill
ontoskills compile office

# Compile with options
ontoskills compile --force          # Bypass cache
ontoskills compile --dry-run        # Preview without saving
ontoskills compile --skip-security  # Skip LLM security review
ontoskills compile -v               # Verbose logging
```

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `skills/`) |
| `-o, --output` | Output directory (default: `ontoskills/`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip LLM security review (regex checks still run) |
| `-f, --force` | Force recompilation (bypass cache) |
| `-y, --yes` | Skip confirmation prompts |
| `-v, --verbose` | Enable debug logging |
| `-q, --quiet` | Suppress progress output |

### Query the Graph

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
```

Runs SPARQL queries against the compiled ontology.

### Inspect Quality

```bash
# List all compiled skills
ontoskills list-skills

# Run security audit
ontoskills security-audit
```

---

## Output Structure

After compilation:

```text
ontoskills/
├── ontoskills-core.ttl      # Core TBox (shared classes/properties)
├── index.ttl                # Manifest with owl:imports
├── system/
│   └── index.enabled.ttl    # Skills enabled for MCP
└── <skill-path>/
    └── ontoskill.ttl        # Individual skill module
```

### The Core Ontology

`ontoskills-core.ttl` defines:

- `oc:Skill`, `oc:ExecutableSkill`, `oc:DeclarativeSkill`
- Properties: `dependsOn`, `extends`, `contradicts`, `resolvesIntent`, etc.
- Knowledge node classes: `oc:Heuristic`, `oc:AntiPattern`, etc.
- State classes for preconditions/postconditions

### The Index

`index.ttl` is a manifest that:
- Lists all compiled skills
- Enables `owl:imports` for the full graph
- Used by OntoMCP to discover available skills

---

## Caching

OntoCore is **cache-aware**:

- Each skill has a content hash stored in `oc:contentHash`
- Unchanged skills are skipped on recompilation
- Use `--force` to bypass cache

---

## Security Pipeline

The compiler runs a defense-in-depth security check:

1. **Unicode normalization** — NFC normalization, zero-width character removal
2. **Regex patterns** — Detects prompt injection, command injection, path traversal, credential exposure
3. **LLM review** — Claude reviews flagged content for nuanced threats

Detected threat types:
- Prompt injection (`ignore instructions`, `system:`, `you are now`)
- Command injection (`; rm`, `| bash`, command substitution)
- Data exfiltration (`curl -d`, `wget --data` with credentials)
- Path traversal (`../../../`, `/etc/passwd`)
- Credential exposure (hardcoded `api_key=`, `password=`)

Use `--skip-security` to bypass LLM review (regex checks still run).

---

## SHACL Validation

Every skill must pass SHACL validation before being written.

Constitutional rules enforced:

| Constraint | Rule |
|------------|------|
| `resolvesIntent` | Required (at least 1) |
| `generatedBy` | Required (exactly 1) |
| `requiresState` | Must be valid IRI |
| `yieldsState` | Must be valid IRI |
| `handlesFailure` | Must be valid IRI |

If validation fails, the skill is **not written** and an error is shown.

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `SkillNotFoundError` | Skill directory doesn't exist | Check path spelling |
| `OrphanSubSkillsError` | `.md` files without parent `SKILL.md` | Create SKILL.md in directory |
| `SecurityError` | Content blocked by security pipeline | Review content, use `--skip-security` if safe |
| `OntologyValidationError` | SHACL validation failed | Fix reported constraint violations |
| `ExtractionError` | LLM extraction failed | Check ANTHROPIC_API_KEY, retry |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `ANTHROPIC_BASE_URL` | API base URL | `https://api.anthropic.com` |
| `SECURITY_MODEL` | Model for security review | `claude-opus-4-6` |

---

## Next Steps

- [Getting Started](/getting-started/) — Install and first steps
- [Architecture](/architecture/) — How the system works
- [Knowledge Extraction](/knowledge-extraction/) — Understanding knowledge nodes
- [Skill Authoring](/authoring/) — Write your own skills
