<p align="center">
  <img src="assets/ontoskills-banner.png" alt="OntoSkills: Neuro-Symbolic Skill Compiler" width="100%">
</p>

<h1 align="center">
  <a href="https://ontoskills.marea.software" style="text-decoration: none; color: inherit; display: flex; align-items: center; justify-content: center; gap: 10px;">
    <img src="assets/ontoskills-logo.png" alt="OntoSkills Logo Inline" height="40px" style="display: block;">
    <span>OntoSkills</span>
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
  <a href="#use-cases">Use Cases</a> •
  <a href="#installation">Installation</a> •
  <a href="#cli-commands">CLI</a> •
  <a href="#local-mcp-server">MCP Server</a> •
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

## OntoSkills: Neuro-Symbolic AI Agent Platform

OntoSkills is a **complete neuro-symbolic platform** for building deterministic, enterprise-grade AI agents. It consists of four layered components:

```mermaid
flowchart LR
    CORE["OntoCore<br/>━━━━━━━━━━<br/>SKILL.md → .ttl<br/>LLM + SHACL"] -->|"compiles"| CENTER["OntoSkills<br/>━━━━━━━━━━<br/>OWL 2 Ontologies<br/>.ttl artifacts"]
    CENTER -->|"loads"| MCP["OntoMCP<br/>━━━━━━━━━━<br/>Rust SPARQL<br/>in-memory graph"]
    MCP <-->|"queries"| AGENT["OntoSkills<br/>━━━━━━━━━━<br/>Enterprise Agent<br/>deterministic"]
    CENTER <-->|"distributes"| STORE["OntoStore<br/>━━━━━━━━━━<br/>Registry<br/>versioning"]

    style CORE fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style CENTER fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style MCP fill:#92eff4,stroke:#2a2a3e,color:#0d0d14
    style AGENT fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style STORE fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

---

## Use Cases

| Use Case | How OntoSkills Helps |
|----------|-------------------|
| **Enterprise AI Agents** | Deterministic skill selection via SPARQL queries instead of LLM judgment |
| **Edge Deployment** | Smaller models query large skill ecosystems without loading all files |
| **Multi-Agent Systems** | Shared OWL 2 ontology as coordination and knowledge layer |
| **Compliance & Audit** | Every skill carries `oc:generatedBy` attestation and content hash |
| **Skill Marketplaces** | OntoStore enables versioned, plug-and-play skill distribution |

---

## OntoCore — The Compiler

**OntoCore** is the first component of the ecosystem. It's a **skill compiler** that transforms natural language skill definitions into **validated semantic knowledge graphs**.

- **OntoMCP** (the Rust MCP server) loads only compiled `.ttl` files into an in-memory graph
- Skills are **self-contained** — all logic, requirements, and execution payloads live in the ontology
- Ontologies are **modular and pluggable** — add/remove `.ttl` files to change agent capabilities

**The compiled TTL is the executable artifact. The Markdown is just source code that gets compiled away.**

---

## Why OntoSkills? — Deterministic AI Agents

### The Determinism Problem

LLMs are inherently **non-deterministic** — the same query can yield different results, and reasoning about skill relationships requires reading entire documents. This creates:
- **Context rot** from lengthy skill files
- **Hallucinations** when information is scattered
- **No verifiable structure** for skill relationships

OntoSkills transforms this into **deterministic, queryable knowledge graphs**.

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
| **Knowledge Nodes** | 10-dimensional epistemic taxonomy (Heuristic, AntiPattern, PreFlightCheck, etc.) |
| **OWL 2 Serialization** | Outputs valid OWL 2 ontologies in RDF/Turtle format |
| **SHACL Validation** | Constitutional gatekeeper ensures logical validity before write |
| **State Machines** | Skills can define preconditions, postconditions, and failure handlers |
| **Security Pipeline** | Defense-in-depth: regex patterns + LLM review for malicious content |
| **Static Linting** | Detects dead states, circular deps, duplicate intents, unreachable skills |
| **Drift Detection** | Semantic diff between ontology versions with breaking change classification |
| **Graph Visualization** | State transition graphs in Mermaid/DOT format |

### What Gets Compiled

Every skill is extracted with:

- **Identity**: `nature`, `genus`, `differentia` (Knowledge Architecture)
- **Intents**: What user intentions this skill resolves
- **Requirements**: Dependencies (EnvVar, Tool, Hardware, API, Knowledge)
- **Knowledge Nodes**: Epistemic knowledge (8-12 nodes per skill)
- **Execution Payload**: Optional code to execute (`oc:code` inline or `oc:executionPath` for external assets)
- **State Transitions**: `requiresState`, `yieldsState`, `handlesFailure`
- **Provenance**: `generatedBy` attestation (LLM model used)

---

## How It Works

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

### The Validation Gatekeeper

Every skill must pass SHACL validation before being written to disk. The constitutional shapes in `specs/ontoclaw.shacl.ttl` enforce:

| Constraint | Rule | Error Message |
|------------|------|---------------|
| `resolvesIntent` | Required (min 1) | "Ogni Skill deve avere almeno un resolvesIntent" |
| `generatedBy` | Required (exactly 1) | "Ogni Skill deve avere esattamente un generatedBy" |
| `requiresState` | Must be IRI | "requiresState deve essere un URI" |
| `yieldsState` | Must be IRI | "yieldsState deve essere un URI" |
| `handlesFailure` | Must be IRI | "handlesFailure deve essere un URI" |

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
    style PAYLOAD fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style NOPAYLOAD fill:#ff6b6b,stroke:#2a2a3e,color:#f0f0f5
```

The classification is **automatic** - you don't specify it. If a skill has code to execute, it's executable. If it's knowledge-only, it's declarative. These classes are **mutually exclusive** (`owl:disjointWith`) per OWL 2 DL semantics.

---

## Components

| Component | Language | Status | Phase | Description |
|-----------|----------|--------|-------|-------------|
| **OntoCore** (`core/`) | Python | ✅ Ready | Design Time | Skill compiler to OWL 2 ontology |
| **OntoMCP** (`mcp/`) | Rust | ✅ Ready | Runtime | MCP server for semantic skill discovery and planning |
| **OntoStore** | TBD | 📋 Roadmap | Distribution | Versioned skill registry |
| **OntoSkills** | Python/Rust | 📋 Roadmap | Agent | Enterprise AI agent |
| `skills/` | Markdown | ✅ Ready | Design Time | **Source code** — human-authored skill definitions |
| `ontoskills/` | Turtle | Generated | Runtime | **Artifact** — compiled, self-contained ontologies |
| `specs/` | Turtle | ✅ Ready | Both | SHACL shapes constitution |

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

### Compiler Configuration

The compiler reads environment variables directly and also auto-loads a repo-local `.env` file.

Typical settings:

```env
ANTHROPIC_API_KEY=your_api_key
ANTHROPIC_BASE_URL=https://your-provider-compatible-base-url
ANTHROPIC_MODEL=claude-opus-4-6
SECURITY_MODEL=claude-opus-4-6
```

This is useful when routing extraction through an Anthropic-compatible provider and avoids
re-exporting credentials before every compile run.

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

### MCP Dependencies

The local MCP server in [mcp/](mcp/) is a standalone Rust crate built with:

- `oxigraph` for Turtle loading and SPARQL querying
- `serde` / `serde_json` for MCP message handling
- `walkdir` for recursive ontology loading

---

## CLI Commands

```bash
# Initialize core ontology with predefined states
ontoclaw init-core

# Compile all skills to ontology
ontoclaw compile

# Compile specific skill
ontoclaw compile my-skill

# Compile a nested skill path
ontoclaw compile demo/markdown-inventory

# Query ontology with SPARQL
ontoclaw query "SELECT ?s WHERE { ?s a oc:Skill }"

# List all skills
ontoclaw list-skills

# Run security audit
ontoclaw security-audit

# ─── Ontology Analysis ─────────────────────────────────

# Lint compiled ontology for structural issues
ontoclaw lint

# Lint with JSON output (for CI/CD)
ontoclaw lint --format json

# Show a human-readable summary card for a skill
ontoclaw explain pdf

# Visualize skill state transitions as Mermaid graph
ontoclaw graph

# Export graph as DOT format
ontoclaw graph --format dot --output graph.dot

# Show 1-hop subgraph around a skill
ontoclaw graph --skill pdf

# ─── Drift Detection ───────────────────────────────────

# Compare current ontology against previous snapshot
ontoclaw diff

# Show only breaking changes (exit code 9 if found)
ontoclaw diff --breaking-only

# Generate migration suggestions for breaking changes
ontoclaw diff --suggest
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

## Local MCP Server

OntoSkills now includes a **local Rust MCP server** under [mcp/](mcp/).

The MCP server is intentionally focused on:

- skill discovery from compiled ontologies
- semantic lookup by intent, dependency, and state transitions
- planning support from `requiresState` and `yieldsState`
- payload lookup for the calling agent

The server does **not** execute skill payloads. Payload execution is delegated to the calling agent in its own runtime context.

### Implemented MCP Tools

- `list_skills`
- `find_skills_by_intent`
- `get_skill`
- `get_skill_requirements`
- `get_skill_transitions`
- `get_skill_dependencies`
- `get_skill_conflicts`
- `find_skills_yielding_state`
- `find_skills_requiring_state`
- `check_skill_applicability`
- `plan_from_intent`
- `get_skill_payload`

### Run The MCP Server

From the repository root:

```bash
cargo run --manifest-path mcp/Cargo.toml
```

The server auto-discovers `ontoskills/` by looking in the current directory and its parents.

To force a specific ontology root:

```bash
cargo run --manifest-path mcp/Cargo.toml -- --ontology-root ./ontoskills
```

### Claude Code Guide

For full setup and verification steps with Claude Code, see [mcp/CLAUDE_CODE_GUIDE.md](mcp/CLAUDE_CODE_GUIDE.md).

### MCP Smoke Checks

```bash
cd mcp
cargo test
```

Current Rust test coverage includes:

- intent lookup
- payload lookup
- planning with preparatory skills
- planner preference for direct skills over setup-heavy alternatives

---

## Exit Codes

| Code | Exception | Description |
|------|-----------|-------------|
| 0 | - | Success |
| 1 | `SkillETLError` / `LintError` | General ETL error / Lint errors found |
| 3 | `SecurityError` | Security threat detected |
| 4 | `ExtractionError` | Skill extraction failed |
| 5 | `OntologyLoadError` | Ontology file not found or invalid |
| 6 | `SPARQLError` | Invalid SPARQL query |
| 7 | `SkillNotFoundError` | Skill not found in ontology |
| **8** | `OntologyValidationError` | **SHACL validation failed** |
| **9** | `DriftDetectedError` | **Breaking changes detected by `ontoclaw diff`** |

---

## Project Structure

```
ontoclaw/
├── core/                    # OntoCore — Python skill compiler
│   ├── cli.py               # Click CLI interface
│   ├── config.py            # Configuration constants
│   ├── core_ontology.py     # Namespace and TBox ontology creation
│   ├── differ.py            # Semantic drift detector
│   ├── drift_report.py      # Drift report formatter
│   ├── exceptions.py        # Exception hierarchy with exit codes
│   ├── explainer.py         # Human-readable skill summaries
│   ├── extractor.py         # ID and hash generation
│   ├── graph_export.py      # State transition graph exporter
│   ├── linter.py            # Static ontology linter
│   ├── schemas.py           # Pydantic models
│   ├── security.py          # Defense-in-depth security
│   ├── serialization.py     # RDF serialization with SHACL gatekeeper
│   ├── snapshot.py          # Ontology snapshot manager
│   ├── sparql.py            # SPARQL query engine
│   ├── storage.py           # File I/O, merging, orphan cleanup
│   ├── transformer.py       # LLM tool-use extraction
│   ├── validator.py         # SHACL validation gatekeeper
│   └── tests/               # Test suite (170+ tests)
├── mcp/                     # OntoMCP — Rust MCP server
│   ├── Cargo.toml           # Rust package manifest
│   ├── Cargo.lock           # Dependency lockfile
│   ├── README.md            # MCP server documentation
│   ├── CLAUDE_CODE_GUIDE.md # Claude Code integration guide
│   └── src/
│       ├── main.rs          # MCP stdio server
│       └── catalog.rs       # Ontology catalog + planner
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
    IN["skills/SKILL.md<br/>━━━━━━━━━━<br/>Source input"] -->|"generate ID/hash"| E["extractor<br/>━━━━━━━━━━<br/>ID + SHA-256"]
    E -->|"skill_dir"| T["transformer<br/>━━━━━━━━━━<br/>LLM tool-use"]
    T -->|"ExtractedSkill"| SEC["security<br/>━━━━━━━━━━<br/>Regex + LLM"]
    SEC -->|"if safe"| SR["serialization<br/>━━━━━━━━━━<br/>Pydantic → RDF"]
    SR -->|"validate"| ST["storage<br/>━━━━━━━━━━<br/>Write + merge"]
    ST --> OUT["ontoskills/<br/>ontoskill.ttl"]

    style IN fill:#6dc9ee,stroke:#2a2a3e,color:#0d0d14
    style E fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style T fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style SEC fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style SR fill:#e91e63,stroke:#2a2a3e,color:#f0f0f5
    style ST fill:#abf9cc,stroke:#2a2a3e,color:#0d0d14
    style OUT fill:#9763e1,stroke:#2a2a3e,color:#f0f0f5
```

**Any skill directory works** - just add a `SKILL.md` file and OntoCore will compile it to a validated OWL 2 ontology module.

---

## Testing

### Python Tests (OntoCore)

```bash
cd core
pytest tests/ -v
```

### Rust Tests (OntoMCP)

```bash
cd mcp
cargo test
```

**Test Coverage**: 170+ Python tests + Rust unit tests covering:
- Pydantic model validation
- Exception exit codes
- ID/hash generation
- Tool-use loop execution
- Security pattern matching + LLM review
- OWL properties, serialization, merge
- SPARQL query execution
- CLI commands and options
- **SHACL validation (5 comprehensive tests)**
- **Drift detection and diff**
- **Static linting (dead-state, circular-dep, duplicate-intent)**
- **State transition graph export**
- **Skill explainer with knowledge nodes**

---

## Knowledge Architecture

Skills are extracted following the **Knowledge Architecture** framework:

- **Categories of Being**: Tool, Concept, Work
- **Genus and Differentia**: "A is a B that C" definition structure
- **State Transitions**: Skills connect through shared states
  - `requiresState` - Preconditions for skill execution
  - `yieldsState` - Outcomes after successful execution
  - `handlesFailure` - Recoverable error states
- **Knowledge Nodes**: Epistemic knowledge imparted by skills
  - 10-dimensional taxonomy: Heuristic, AntiPattern, PreFlightCheck, RecoveryTactic, etc.
  - Each node: `directiveContent`, `appliesToContext`, `hasRationale`, `severityLevel`
- **Skill Relations**:
  - `dependsOn` - Skill prerequisites (direct dependency)
  - `extends` - Skill inheritance
  - `contradicts` - Incompatible skills

---

## OWL 2 Design

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

OntoSkills is open-source software, licensed under the **[MIT License](LICENSE)**.

| Permissions | Conditions | Limitations |
|-------------|------------|-------------|
| ✅ Commercial use | 📝 Include license and copyright notice | ⚖️ No Liability |
| ✅ Modification | | 🛡️ No Warranty |
| ✅ Distribution | | |
| ✅ Private use | | |

*© 2026 [Marea Software](https://marea.software)*
