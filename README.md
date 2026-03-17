<p align="center">
  <img src="assets/ontoclaw-banner.png" alt="OntoClaw: Neuro-Symbolic Skill Compiler" width="100%">
</p>

<h1 align="center">
  <a href="https://ontoclaw.marea.software" style="text-decoration: none; color: inherit; display: flex; align-items: center; justify-content: center; gap: 10px;">
    <img src="assets/ontoclaw-logo.png" alt="OntoClaw Logo Inline" height="40px" style="display: block;">
    <span>OntoClaw</span>
  </a>
</h1>

<p align="center">
  <strong>The <span style="color:#e91e63">deterministic</span> enterprise AI agent platform.</strong>
</p>

<p align="center">
  Neuro-symbolic architecture for the Agentic Web — <span style="color:#00bf63;font-weight:bold">OntoCore</span> • <span style="color:#2196F3;font-weight:bold">OntoMCP</span> • <span style="color:#9333EA;font-weight:bold">OntoStore</span>
</p>

<p align="center">
  <a href="#the-ontoclaw-ecosystem">Ecosystem</a> •
  <a href="#ontocore--the-compiler">OntoCore</a> •
  <a href="#installation">Installation</a> •
  <a href="#cli-commands">CLI</a> •
  <a href="PHILOSOPHY.md">Philosophy</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OWL%202-RDF%2FTurtle-green?style=for-the-badge&logo=w3c" alt="OWL 2 RDF/Turtle">
  <img src="https://img.shields.io/badge/SHACL-Validation-purple?style=for-the-badge&logo=graphql" alt="SHACL Validation">
  <a href="#license">
    <img src="https://img.shields.io/badge/license-MIT-orange?style=for-the-badge" alt="MIT License">
  </a>
</p>

---

## The OntoClaw Ecosystem

OntoClaw is a **complete neuro-symbolic platform** for building deterministic, enterprise-grade AI agents. It consists of four layered components:

```mermaid
flowchart TB
    subgraph ONTOCLAW["OntoClaw — Enterprise AI Agent"]
        TAG1["Deterministic • Fast • Reliable • Production-Ready"]
    end

    subgraph ONTOSTORE["OntoStore — Skill Registry"]
        TAG2["🚧 Planned — Versioned skill distribution"]
    end

    subgraph ONTOMCP["OntoMCP — Rust MCP Server"]
        TAG3["🚧 Planned — Blazing-fast SPARQL via MCP"]
    end

    subgraph ONTOSKILLS["OntoSkills — Compiled OWL 2 Ontologies"]
        TAG4["✅ Ready — Self-contained, modular, pluggable"]
    end

    subgraph ONTOCORE["OntoCore — Python Compiler"]
        TAG5["✅ Ready — SKILL.md → validated OWL 2 TTL"]
    end

    ONTOCLAW --> ONTOSTORE
    ONTOSTORE --> ONTOMCP
    ONTOMCP --> ONTOSKILLS
    ONTOSKILLS --> ONTOCORE

    style ONTOCLAW fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style ONTOSTORE fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style ONTOMCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style ONTOSKILLS fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style ONTOCORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style TAG1 fill:#6dc9ee,stroke:none,color:#0d0d14
    style TAG2 fill:#9763e1,stroke:none,color:#f0f0f5
    style TAG3 fill:#92eff4,stroke:none,color:#0d0d14
    style TAG4 fill:#abf9cc,stroke:none,color:#0d0d14
    style TAG5 fill:#e91e63,stroke:none,color:#f0f0f5
```

---

## OntoCore — The Compiler

**OntoCore** is the first component of the ecosystem. It's a **skill compiler** that transforms natural language skill definitions into **validated semantic knowledge graphs**.

### Design Time vs Runtime

OntoCore separates the skill lifecycle into two distinct phases:

```mermaid
flowchart LR
    subgraph DESIGN["🎨 Design Time"]
        MD["SKILL.md<br/>(Human-authored)"]
        CORE["OntoCore<br/>(Python)"]
        TTL["ontoskill.ttl<br/>(Self-contained)"]
        MD -->|"LLM extraction<br/>+ SHACL"| CORE
        CORE --> TTL
    end

    subgraph RUNTIME["🚀 Runtime"]
        MCP["OntoMCP (Rust)"]
        GRAPH["In-memory<br/>RDF Graph"]
        AGENT["LLM Agent"]
        MCP <--> AGENT
        MCP --> GRAPH
    end

    TTL -.->|"deployed"| MCP

    style DESIGN fill:#1a1a2e,stroke:#2a2a3e,color:#f0f0f5
    style RUNTIME fill:#16213e,stroke:#2a2a3e,color:#f0f0f5
    style MD fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style CORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style TTL fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style GRAPH fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
```

- **OntoMCP** (the Rust MCP server) loads only compiled `.ttl` files into an in-memory graph
- Skills are **self-contained** — all logic, requirements, and execution payloads live in the ontology
- Ontologies are **modular and pluggable** — add/remove `.ttl` files to change agent capabilities

**The compiled TTL is the executable artifact. The Markdown is just source code that gets compiled away.**

---

## Why OntoClaw?

### The Determinism Problem

LLMs are inherently **non-deterministic** — the same query can yield different results, and reasoning about skill relationships requires reading entire documents. This creates:
- **Context rot** from lengthy skill files
- **Hallucinations** when information is scattered
- **No verifiable structure** for skill relationships

OntoClaw transforms this into **deterministic, queryable knowledge graphs**.

### Description Logics Foundation

Built on **OWL 2** ($\mathcal{SROIQ}^{(D)}$ Description Logic), enabling:
- **Decidable reasoning** — transitive, symmetric, inverse properties
- **Formal semantics** — no ambiguity in skill relationships
- **SPARQL queries** with O(1) indexed lookup vs O(n) text scanning

### For Smaller Models

When an agent has 50+ skills, reading all SKILL.md files is impractical. With ontologies:
- Query only what's needed: `SELECT ?skill WHERE { ?skill oc:resolvesIntent "create_pdf" }`
- Schema exposure: know what nodes/relations exist before querying
- Smaller models can reason about complex skill ecosystems

[→ Read the full philosophy](PHILOSOPHY.md)

---

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **LLM Extraction** | Uses Claude to extract structured knowledge from SKILL.md files |
| **Knowledge Architecture** | Follows the "A is a B that C" definition pattern (genus + differentia) |
| **OWL 2 Serialization** | Outputs valid OWL 2 ontologies in RDF/Turtle format |
| **SHACL Validation** | Constitutional gatekeeper ensures logical validity before write |
| **State Machines** | Skills can define preconditions, postconditions, and failure handlers |
| **Security Pipeline** | Defense-in-depth: regex patterns + LLM review for malicious content |

### What Gets Compiled

Every skill is extracted with:

- **Identity**: `nature`, `genus`, `differentia` (Knowledge Architecture)
- **Intents**: What user intentions this skill resolves
- **Requirements**: Dependencies (EnvVar, Tool, Hardware, API, Knowledge)
- **Execution Payload**: Optional code to execute (shell, python, node, claude_tool)
- **State Transitions**: `requiresState`, `yieldsState`, `handlesFailure`
- **Provenance**: `generatedBy` attestation (LLM model used)

---

## How It Works

```mermaid
flowchart LR
    subgraph DT["Design Time"]
        MD["SKILL.md"]
    end

    subgraph OC["OntoCore Pipeline"]
        LLM["Claude API"] --> PYD["Pydantic"]
        PYD --> SEC["Security"]
        SEC --> RDF["RDF Graph"]
        RDF --> SHACL["SHACL"]
    end

    subgraph OS["OntoSkills"]
        TTL["ontoskill.ttl"]
    end

    subgraph RT["Runtime"]
        MCP["OntoMCP"] <--> AGENT["Agent"]
    end

    MD --> LLM
    SHACL -->|"PASS"| TTL
    SHACL -->|"FAIL"| FAIL["❌ Block"]
    TTL --> MCP

    style DT fill:#1a1a2e,stroke:#2a2a3e,color:#f0f0f5
    style OC fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style OS fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style RT fill:#16213e,stroke:#2a2a3e,color:#f0f0f5
    style MD fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style LLM fill:#e91e63,stroke:none,color:#f0f0f5
    style PYD fill:#e91e63,stroke:none,color:#f0f0f5
    style SEC fill:#e91e63,stroke:none,color:#f0f0f5
    style RDF fill:#e91e63,stroke:none,color:#f0f0f5
    style SHACL fill:#e91e63,stroke:none,color:#f0f0f5
    style TTL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style FAIL fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
```

### The Validation Gatekeeper

Every skill must pass SHACL validation before being written to disk. The constitutional shapes in `specs/ontoclaw.shacl.ttl` enforce:

| Constraint | Rule | Error Message |
|------------|------|---------------|
| `resolvesIntent` | Required (min 1) | "Ogni Skill deve avere almeno un resolvesIntent" |
| `generatedBy` | Required (exactly 1) | "Ogni Skill deve avere esattamente un generatedBy" |
| `requiresState` | Must be IRI of `oc:State` | "requiresState deve essere un URI che punta a un'istanza di oc:State" |
| `yieldsState` | Must be IRI of `oc:State` | "yieldsState deve essere un URI..." |
| `handlesFailure` | Must be IRI of `oc:State` | "handlesFailure deve essere un URI..." |

---

## Skill Types

```mermaid
flowchart LR
    SKILL["oc:Skill"] --> EXE["oc:ExecutableSkill"]
    SKILL --> DEC["oc:DeclarativeSkill"]

    EXE --> PAYLOAD["hasPayload<br/>exactly 1"]
    DEC --> NOPAYLOAD["hasPayload<br/>forbidden"]

    style SKILL fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style EXE fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style DEC fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style PAYLOAD fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style NOPAYLOAD fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
```

The classification is **automatic** - you don't specify it. If a skill has code to execute, it's executable. If it's knowledge-only, it's declarative.

---

## Components

| Component | Language | Status | Phase | Description |
|-----------|----------|--------|-------|-------------|
| **OntoCore** (`core/`) | Python | ✅ Ready | Design Time | Skill compiler to OWL 2 ontology |
| **OntoMCP** (`mcp/`) | Rust | 🚧 Planned | Runtime | Fast MCP server for ontology queries |
| **OntoStore** | TBD | 📋 Roadmap | Distribution | Versioned skill registry |
| **OntoClaw** | Python/Rust | 📋 Roadmap | Agent | Enterprise AI agent |
| `skills/` | Markdown | ✅ Ready | Design Time | **Source code** — human-authored skill definitions |
| `ontoskills/` | Turtle | Generated | Runtime | **Artifact** — compiled, self-contained ontologies |
| `specs/` | Turtle | ✅ Ready | Both | SHACL shapes constitution |

---

## Roadmap

```mermaid
timeline
    title OntoClaw Ecosystem Roadmap

    section Phase 1
        OntoCore : Python compiler
        OntoSkills : OWL 2 ontologies

    section Phase 2
        OntoMCP : Rust MCP server
        : Blazing-fast SPARQL
        : In-memory graph

    section Phase 3
        OntoStore : Skill registry
        : Version management
        : Distribution

    section Phase 4
        OntoClaw Agent : Enterprise AI agent
        : Deterministic reasoning
        : Production-ready
```

---

## Installation

```bash
# Clone repository
git clone https://github.com/marea-software/ontoclaw.git
cd ontoclaw

# Install OntoCore
cd core
pip install -e ".[dev]"
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `anthropic>=0.39.0` | Claude API for extraction |
| `click>=8.1.0` | CLI framework |
| `pydantic>=2.0.0` | Data validation |
| `rdflib>=7.0.0` | RDF graph handling |
| `pyshacl>=0.25.0` | SHACL validation |
| `rich>=13.0.0` | Terminal formatting |
| `owlrl>=1.0.0` | OWL reasoning |

---

## CLI Commands

```bash
# Initialize core ontology with predefined states
ontoclaw init-core

# Compile all skills to ontology
ontoclaw compile

# Compile specific skill
ontoclaw compile my-skill

# Query ontology with SPARQL
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"

# List all skills
ontoclaw list-skills

# Run security audit
ontoclaw security-audit
```

### Command Options

| Option | Description |
|--------|-------------|
| `-i, --input` | Input directory (default: `./skills/`) |
| `-o, --output` | Output file (default: `./ontoskills/skills.ttl`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip security checks (not recommended) |
| `-f, --force` | Force recompilation (bypass hash-based cache) |
| `--reason/--no-reason` | Apply OWL reasoning |
| `-y, --yes` | Skip confirmation |
| `-v, --verbose` | Debug logging |
| `-q, --quiet` | Suppress progress |

---

## Exit Codes

| Code | Exception | Description |
|------|-----------|-------------|
| 0 | - | Success |
| 1 | `SkillETLError` | General ETL error |
| 3 | `SecurityError` | Security threat detected |
| 4 | `ExtractionError` | Skill extraction failed |
| 5 | `OntologyLoadError` | Ontology file not found or invalid |
| 6 | `SPARQLError` | Invalid SPARQL query |
| 7 | `SkillNotFoundError` | Skill not found in ontology |
| **8** | `OntologyValidationError` | **SHACL validation failed** |

---

## Project Structure

```
ontoclaw/
├── core/                    # OntoCore — Python skill compiler
│   ├── cli.py               # Click CLI interface
│   ├── config.py            # Configuration constants
│   ├── core_ontology.py     # Namespace and TBox ontology creation
│   ├── exceptions.py        # Exception hierarchy with exit codes
│   ├── extractor.py         # ID and hash generation
│   ├── schemas.py           # Pydantic models
│   ├── security.py          # Defense-in-depth security
│   ├── serialization.py     # RDF serialization with SHACL gatekeeper
│   ├── sparql.py            # SPARQL query engine
│   ├── storage.py           # File I/O, merging, orphan cleanup
│   ├── transformer.py       # LLM tool-use extraction
│   ├── validator.py         # SHACL validation gatekeeper
│   └── tests/               # Test suite (156 tests)
├── mcp/                     # OntoMCP — Rust MCP server (planned)
├── specs/
│   └── ontoclaw.shacl.ttl   # SHACL shapes constitution
├── skills/                  # Input: SKILL.md definitions (source code)
├── ontoskills/              # Output: compiled .ttl files (artifacts)
│   ├── ontoclaw-core.ttl    # Core ontology with states
│   ├── index.ttl            # Index of all skills
│   └── */ontoskill.ttl      # Individual skill modules
└── docs/                    # Documentation
```

---

## Architecture

```mermaid
flowchart LR
    subgraph IN["skills/ (Source)"]
        S1["create-document/<br/>SKILL.md"]
        S2["analyze-data/<br/>SKILL.md"]
        S3["send-email/<br/>SKILL.md"]
    end

    subgraph CORE["OntoCore Pipeline"]
        E["extractor.py"] --> T["transformer.py"]
        T --> SEC["security.py"]
        SEC --> CO["core_ontology.py"]
        CO --> SR["serialization.py"]
        SR --> ST["storage.py"]
    end

    subgraph OUT["ontoskills/ (Artifacts)"]
        CORE_TTL["ontoclaw-core.ttl"]
        IDX["index.ttl"]
        O1["create-document/<br/>ontoskill.ttl"]
        O2["analyze-data/<br/>ontoskill.ttl"]
        O3["send-email/<br/>ontoskill.ttl"]
    end

    S1 --> E
    S2 --> E
    S3 --> E
    ST --> CORE_TTL
    ST --> IDX
    ST --> O1
    ST --> O2
    ST --> O3

    style IN fill:#1a1a2e,stroke:#2a2a3e,color:#f0f0f5
    style CORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style OUT fill:#16213e,stroke:#2a2a3e,color:#f0f0f5
    style S1 fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style S2 fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style S3 fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style E fill:#e91e63,stroke:none,color:#f0f0f5
    style T fill:#e91e63,stroke:none,color:#f0f0f5
    style SEC fill:#e91e63,stroke:none,color:#f0f0f5
    style CO fill:#9763e1,stroke:none,color:#f0f0f5
    style SR fill:#e91e63,stroke:none,color:#f0f0f5
    style ST fill:#abf9cc,stroke:none,color:#0d0d14
    style CORE_TTL fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style IDX fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style O1 fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style O2 fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style O3 fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
```

**Any skill directory works** - just add a `SKILL.md` file and OntoCore will compile it to a validated OWL 2 ontology module.

---

## Testing

```bash
cd core
pytest tests/ -v
```

**Test Coverage**: 156 tests covering:
- Pydantic model validation
- Exception exit codes
- ID/hash generation
- Tool-use loop execution
- Security pattern matching + LLM review
- OWL properties, serialization, merge
- SPARQL query execution
- CLI commands and options
- **SHACL validation (5 comprehensive tests)**

---

## Knowledge Architecture

Skills are extracted following the **Knowledge Architecture** framework:

- **Categories of Being**: Tool, Concept, Work
- **Genus and Differentia**: "A is a B that C" definition structure
- **Relations as First-Class Citizens**:
  - `depends-on` - Skill prerequisites
  - `extends` - Skill inheritance
  - `contradicts` - Incompatible skills
  - `implements` - Interface compliance
  - `exemplifies` - Pattern demonstration

---

## OWL 2 Design

```mermaid
flowchart LR
    subgraph PROPS["OWL 2 Properties"]
        A["dependsOn<br/>Asymmetric"]
        B["extends<br/>Transitive"]
        C["contradicts<br/>Symmetric"]
        D["implements"]
        E["exemplifies"]
    end

    subgraph USE["Use Cases"]
        UC1["Dependencies"]
        UC2["Inheritance"]
        UC3["Conflicts"]
        UC4["Interfaces"]
        UC5["Patterns"]
    end

    A --> UC1
    B --> UC2
    C --> UC3
    D --> UC4
    E --> UC5

    style PROPS fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
    style USE fill:#1a1a2e,stroke:#2a2a3e,color:#f0f0f5
    style A fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style B fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style C fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
    style D fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style E fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
```

---

## Security Philosophy

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

Detected threats:
- Prompt injection (`ignore instructions`, `system:`, `you are now`)
- Command injection (`; rm`, `| bash`, command substitution)
- Data exfiltration (`curl -d`, `wget --data`)
- Path traversal (`../`, `/etc/passwd`)
- Credential exposure (`api_key=`, `password=`)

---

## <a id="license"></a>License

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License" height="40px">
  </a>
</p>

OntoClaw is open-source software, licensed under the **[MIT License](LICENSE)**.

| Permissions | Conditions | Limitations |
|-------------|------------|-------------|
| ✅ Commercial use | 📝 Include license and copyright notice | ⚖️ No Liability |
| ✅ Modification | | 🛡️ No Warranty |
| ✅ Distribution | | |
| ✅ Private use | | |

*© 2026 [Marea Software](https://marea.software)*
