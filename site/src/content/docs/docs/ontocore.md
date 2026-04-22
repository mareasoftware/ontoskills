---
title: OntoCore Compiler
description: Install and use OntoCore for custom source skills
sidebar:
  order: 5
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

> **Optional:** Install `ontocore[embeddings]` to enable per-skill embedding generation for semantic search (recommended for large skill catalogs):
> ```bash
> pip install ontocore[embeddings]
> ```

---

## The compilation pipeline

```
SKILL.md → [Extract] → [Security] → [Serialize] → [SHACL] → [Embed (opt)] → ontoskill.ttl + intents.json
```

| Stage | What Happens |
|-------|--------------|
| **Extract** | Structural content extraction + LLM knowledge extraction → compact knowledge nodes |
| **Security** | Regex + LLM review for malicious content |
| **Serialize** | Pydantic models → RDF triples |
| **Validate** | SHACL shapes check logical validity |
| **Embed** | Per-skill intent embeddings (384-dim, L2-normalized) — optional, requires `ontocore[embeddings]` |
| **Write** | Atomic write with backup |

If any stage fails, the skill is **not written**. The SHACL gatekeeper enforces constitutional rules. The embedding stage is optional — skipped with a warning when `ontocore[embeddings]` is not installed.

### Content extraction

The **Extract** stage is the core of OntoCore. It transforms your markdown into compact knowledge nodes — the primary output that agents consume. Internally, this happens through an intermediate pipeline of structured content blocks and section trees.

```
SKILL.md → flat blocks → section tree → knowledge nodes
```

1. **Flat block extraction** — The parser tokenizes markdown into typed blocks: paragraphs, code blocks, tables, bullet lists, ordered procedures, blockquotes, flowcharts, templates, HTML blocks, frontmatter, and headings
2. **Section tree building** — Blocks are organized into a hierarchical tree based on heading levels, preserving document structure with parent-child relationships
3. **LLM enhancement** (optional) — If `ANTHROPIC_API_KEY` is set, an LLM skeleton step improves section nesting before falling back to deterministic tree building

### Content block types

Every element in your SKILL.md becomes a typed RDF node during the intermediate extraction pipeline. The 11 block types:

| Block Type | What It Captures | Key Properties |
|------------|-----------------|----------------|
| `paragraph` | Free-form text | `textContent` |
| `code_block` | Fenced code with language | `codeLanguage`, `codeContent` |
| `table` | Markdown tables | `tableMarkdown`, `rowCount` |
| `flowchart` | Mermaid or Graphviz diagrams | `flowchartType`, `flowchartSource` |
| `template` | Reusable templates with `{variables}` | `templateContent`, `templateVariables` |
| `bullet_list` | Unordered lists with nested children | `hasItem` → `itemText`, `itemOrder` |
| `blockquote` | Quoted text with optional attribution | `quoteContent`, `quoteAttribution` |
| `ordered_procedure` | Numbered step-by-step procedures | `hasStep` → `stepText`, `stepOrder` |
| `html_block` | Raw HTML content | `htmlContent` |
| `frontmatter` | YAML metadata | `rawYaml`, parsed properties |
| `heading` | Section headings | Integrated into section tree |

Items in bullet lists and steps in procedures can contain **nested child blocks** (code examples, blockquotes, etc.) via the `hasChild` property.

---

## File processing rules

OntoCore processes files based on their type:

| Rule | Input | Output | Processing |
|------|-------|--------|------------|
| **A** | `SKILL.md` | `ontoskill.ttl` | LLM compilation |
| **B** | `*.md` (auxiliary) | `*.ttl` | LLM compilation as sub-skill |
| **C** | Other files | Direct copy | Asset (images, etc.) |

### Directory mirroring

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

### Sub-skills

Auxiliary `.md` files in a skill directory become **sub-skills**:

- They automatically `extend` the parent skill
- They inherit parent context during extraction
- They get qualified IDs: `package/parent/child`

---

## CLI commands

### Initialize core ontology

```bash
ontoskills init-core
```

Creates `core.ttl` with the base TBox ontology (classes, properties, state definitions).

### Compile skills

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

### Query the graph

```bash
ontoskills query "SELECT ?s WHERE { ?s a oc:Skill }"
```

Runs SPARQL queries against the compiled ontology.

### Inspect quality

```bash
# List all compiled skills
ontoskills list-skills

# Run security audit
ontoskills security-audit
```

---

## Output structure

After compilation:

```text
ontoskills/
├── core.ttl      # Core TBox (shared classes/properties)
├── index.ttl                # Manifest with owl:imports
├── system/
│   └── index.enabled.ttl    # Skills enabled for MCP
└── <skill-path>/
    ├── ontoskill.ttl        # Individual skill module
    └── intents.json         # Pre-computed intent embeddings (optional)
```

### The core ontology

The core ontology (`core.ttl`) is the shared TBox that all skill modules reference via `owl:imports`. It is:

- **Served online** at `https://ontoskills.sh/ontology/core.ttl`
- **Downloaded automatically** by `ontoskills install mcp` into `~/.ontoskills/ontologies/core.ttl`
- **Regenerated locally** by `ontoskills init-core` or `ontoskills compile` when developing

Compiled skill modules reference the core via `owl:imports <https://ontoskills.sh/ontology/core.ttl>`. The MCP resolves this to the local copy in your ontology root.

`core.ttl` defines:

- `oc:Skill`, `oc:ExecutableSkill`, `oc:DeclarativeSkill`
- Properties: `dependsOnSkill`, `extends`, `contradicts`, `resolvesIntent`, etc.
- Knowledge node classes: `oc:Heuristic`, `oc:AntiPattern`, etc.
- State classes for preconditions/postconditions

### The index

`index.ttl` is a manifest that:
- Lists all compiled skills
- References the core ontology via `owl:imports <https://ontoskills.sh/ontology/core.ttl>`
- Used by OntoMCP to discover available skills

---

## Caching

OntoCore is **cache-aware**:

- Each skill has a content hash stored in `oc:contentHash`
- Unchanged skills are skipped on recompilation
- Use `--force` to bypass cache

---

## Security pipeline

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

## SHACL validation

Every skill must pass SHACL validation before being written. The constitutional shapes are defined in `core/specs/ontoskills.shacl.ttl` and enforce constraints across 6 node shapes.

**Required fields (blocking):**

| Constraint | Rule |
|------------|------|
| `resolvesIntent` | Required (at least 1) — also needed for semantic search embeddings |
| `generatedBy` | Optional (attestation) |
| `requiresState` | Must be valid IRI |
| `yieldsState` | Must be valid IRI |
| `handlesFailure` | Must be valid IRI |

**Type-specific rules:**
- `ExecutableSkill` must have exactly 1 `hasPayload` (with `code` or `executionPath`)
- `DeclarativeSkill` must not have `hasPayload`

If validation fails, the skill is **not written** and an error is shown.

See [Skill Authoring](/docs/authoring/) for practical guidance on writing skills that pass validation.

---

## Error handling

| Error | Cause | Solution |
|-------|-------|----------|
| `SkillNotFoundError` | Skill directory doesn't exist | Check path spelling |
| `OrphanSubSkillsError` | `.md` files without parent `SKILL.md` | Create SKILL.md in directory |
| `SecurityError` | Content blocked by security pipeline | Review content, use `--skip-security` if safe |
| `OntologyValidationError` | SHACL validation failed | Fix reported constraint violations |
| `ExtractionError` | LLM extraction failed | Check ANTHROPIC_API_KEY, retry |

---

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `ANTHROPIC_BASE_URL` | API base URL | `https://api.anthropic.com` |
| `SECURITY_MODEL` | Model for security review | `claude-opus-4-6` |
| `DEFAULT_SKILLS_AUTHOR` | Default author for skills with no package structure | `local` |

---

## Next steps

- [Getting Started](/docs/getting-started/) — Install and first steps
- [Architecture](/docs/architecture/) — How the system works
- [Knowledge Extraction](/docs/knowledge-extraction/) — Understanding knowledge nodes
- [Skill Authoring](/docs/authoring/) — Write your own skills
