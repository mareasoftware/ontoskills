---
title: Architecture
description: How OntoSkills compiles, stores, and serves skills
---

## The Compilation Pipeline

```mermaid
flowchart LR
    MD["SKILL.md"] --> LLM["Claude"] --> PYD["Pydantic"] --> SEC["Security"] --> RDF["RDF"] --> SHACL["SHACL"]
    SHACL -->|"PASS"| TTL["ontoskill.ttl"] --> MCP["OntoMCP"] <--> AGENT["Agent"]
    SHACL -->|"FAIL"| FAIL["❌ Block"]

    style MD fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style LLM fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style PYD fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style SEC fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style RDF fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style SHACL fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style TTL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style FAIL fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
```

### Stage Details

| Stage | Input | Output | Description |
|-------|-------|--------|-------------|
| **Extract** | SKILL.md | ExtractedSkill | LLM extracts structured knowledge |
| **Security** | ExtractedSkill | ExtractedSkill | Regex + LLM review for threats |
| **Serialize** | ExtractedSkill | RDF Graph | Pydantic → RDF triples |
| **Validate** | RDF Graph | ValidationResult | SHACL shapes check validity |
| **Write** | RDF Graph | .ttl file | Atomic write with backup |

---

## Skill Types

```mermaid
flowchart LR
    SKILL["oc:Skill<br/>━━━━━━━━━━<br/>Base class"] --> EXE["oc:ExecutableSkill<br/>━━━━━━━━━━<br/>Has code to run"]
    SKILL --> DEC["oc:DeclarativeSkill<br/>━━━━━━━━━━<br/>Knowledge only"]

    EXE --> PAYLOAD["hasPayload exactly 1<br/>━━━━━━━━━━<br/>oc:code OR oc:executionPath"]
    DEC --> NOPAYLOAD["hasPayload forbidden<br/>━━━━━━━━━━<br/>owl:disjointWith"]

    style SKILL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style EXE fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style DEC fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
```

The classification is **automatic** — you don't specify it. If a skill has code to execute, it's executable. If it's knowledge-only, it's declarative. These classes are **mutually exclusive** (`owl:disjointWith`).

---

## OWL 2 Properties

```mermaid
flowchart LR
    A["dependsOn<br/>━━━━━━━━━━<br/>AsymmetricProperty<br/>A needs B"] --> UC1["Prerequisites<br/>━━━━━━━━━━<br/>Install before run"]
    B["extends<br/>━━━━━━━━━━<br/>TransitiveProperty<br/>A → B → C"] --> UC2["Inheritance<br/>━━━━━━━━━━<br/>Override behavior"]
    C["contradicts<br/>━━━━━━━━━━<br/>SymmetricProperty<br/>A ↔ B"] --> UC3["Conflicts<br/>━━━━━━━━━━<br/>Mutually exclusive"]
    D["implements<br/>━━━━━━━━━━<br/>Interface<br/>compliance"] --> UC4["Contracts<br/>━━━━━━━━━━<br/>Guaranteed API"]
    E["exemplifies<br/>━━━━━━━━━━<br/>Pattern<br/>demonstration"] --> UC5["Examples<br/>━━━━━━━━━━<br/>Best practices"]

    style A fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style B fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style C fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
    style D fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style E fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
```

| Property | Type | Semantics |
|----------|------|-----------|
| `dependsOn` | Asymmetric | A needs B, but B doesn't need A |
| `extends` | Transitive | If A extends B and B extends C, then A extends C |
| `contradicts` | Symmetric | If A contradicts B, then B contradicts A |
| `implements` | Irreflexive | A cannot implement itself |
| `exemplifies` | Irreflexive | A cannot exemplify itself |

---

## The Validation Gatekeeper

Every skill must pass SHACL validation before being written. The constitutional shapes enforce:

| Constraint | Rule | Error |
|------------|------|-------|
| `resolvesIntent` | Required (min 1) | Skill must resolve at least one intent |
| `generatedBy` | Required (exactly 1) | Skill must have attestation |
| `requiresState` | Must be IRI | Must be a valid state URI |
| `yieldsState` | Must be IRI | Must be a valid state URI |
| `handlesFailure` | Must be IRI | Must be a valid state URI |

---

## Security Pipeline

```mermaid
flowchart LR
    INPUT["User Content"] --> NORM["Unicode NFC"]
    NORM --> PATTERNS["Regex Check"]
    PATTERNS --> LLM["LLM Review"]
    LLM --> DECISION{"Safe?"}

    DECISION -->|"Yes"| PASS["✅ Allow"]
    DECISION -->|"No"| BLOCK["❌ Reject"]

    style INPUT fill:#1a1a2e,stroke:#2a2a3e,color:#f0f0f5
    style NORM fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style PATTERNS fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
    style LLM fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style DECISION fill:#feca57,stroke:#2a2a3e,color:#0d0d14
    style PASS fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style BLOCK fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
```

**Detected threats:**
- Prompt injection (`ignore instructions`, `system:`, `you are now`)
- Command injection (`; rm`, `| bash`, command substitution)
- Data exfiltration (`curl -d`, `wget --data`)
- Path traversal (`../`, `/etc/passwd`)
- Credential exposure (`api_key=`, `password=`)

---

## Project Structure

```
ontoskills/
├── core/                       # OntoCore — Python skill compiler
│   ├── src/
│   │   ├── cli/                # Click CLI commands
│   │   │   ├── compile.py      # Compilation command
│   │   │   ├── query.py        # SPARQL query command
│   │   │   └── ...
│   │   ├── config.py           # Configuration constants
│   │   ├── core_ontology.py    # Namespace and TBox ontology creation
│   │   ├── differ.py           # Semantic drift detector
│   │   ├── drift_report.py     # Drift report generator
│   │   ├── embeddings/         # Vector embeddings export
│   │   ├── env.py              # Environment loading
│   │   ├── exceptions.py       # Exception hierarchy with exit codes
│   │   ├── explainer.py        # Skill explanation generator
│   │   ├── extractor.py        # ID and hash generation
│   │   ├── graph_export.py     # Graph format export
│   │   ├── linter.py           # Static ontology linter
│   │   ├── prompts.py          # LLM prompt templates
│   │   ├── registry/           # Store/package management
│   │   ├── schemas.py          # Pydantic models
│   │   ├── security.py         # Defense-in-depth security
│   │   ├── serialization.py    # RDF serialization with SHACL gatekeeper
│   │   ├── snapshot.py         # Ontology snapshots
│   │   ├── sparql.py           # SPARQL query engine
│   │   ├── storage.py          # File I/O, merging, orphan cleanup
│   │   ├── transformer.py      # LLM tool-use extraction
│   │   └── validator.py        # SHACL validation gatekeeper
│   └── tests/                  # Test suite
├── mcp/                        # OntoMCP — Rust MCP server
│   ├── Cargo.toml              # Rust package manifest
│   └── src/
│       ├── main.rs             # MCP stdio server
│       └── ...
├── skills/                     # Input: SKILL.md definitions
├── ontoskills/                 # Output: compiled .ttl files
│   ├── ontoskills-core.ttl     # Core ontology with states
│   └── */ontoskill.ttl         # Individual skill modules
├── registry/                   # OntoStore blueprint
└── specs/
    └── ontoskills.shacl.ttl    # SHACL shapes constitution
```

**Any source skill directory works** — add a `SKILL.md` file and OntoCore will compile it to a validated ontology module.

## Runtime Model

OntoMCP reads compiled ontology packages from `ontoskills/`. It does not read raw `SKILL.md` sources directly.

The user-facing `ontoskills` CLI is responsible for:

- installing `ontomcp`
- installing `ontocore`
- importing raw source repositories into `skills/vendor/`
- installing compiled packages from OntoStore or third-party stores
- enabling and disabling skills before they reach the MCP runtime

## Store Model

OntoStore is published as a static GitHub repository and is built in by default.

- Official packages are available immediately after install
- Third-party stores are added explicitly with `store add-source`
- Raw source repositories are compiled locally before being installed into `ontoskills/vendor/`
