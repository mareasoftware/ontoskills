# Skill Ontology ETL

**The semantic compiler for the Agentic Web.** A CLI tool that compiles unstructured Markdown agent skills into a W3C-standard **OWL 2 RDF/Turtle ontology** for semantic routing.

## The Problem: Context Rot & Hallucinations

Current AI agent frameworks rely on "Skills" written in Markdown. While human-friendly, they suffer from:

- **Context Rot:** Large skill files saturate the LLM's context window
- **Ambiguity:** Small/local LLMs struggle to parse complex prerequisites in raw text
- **Non-Determinism:** Agents "hallucinate" how to use tools because instructions are buried in prose

## The Solution: Semantic Compilation

This tool acts as an **Offline Compiler**. It "digests" raw skills and produces a structured **OWL 2 Ontology** using W3C standards (RDF/SPARQL).

Instead of reading a 200-line Markdown file, your agent queries a **Knowledge Graph**:

1. **Intent Identification:** What is the user asking for?
2. **Prerequisite Check:** Do I have the hardware/API keys required?
3. **Deterministic Execution:** What is the exact command to run?

## Features

- **LLM Tool-Use Extraction:** Uses Claude's native tool-use for unlimited skill sizes
- **OWL 2 Property Characteristics:** Transitive, symmetric, asymmetric relations
- **Intelligent Merge:** Skip unchanged skills, update modified ones
- **Security Pipeline:** Regex patterns + LLM-as-judge for defense-in-depth
- **Atomic Writes:** Backup/restore pattern for data integrity
- **SPARQL Query Engine:** Query the ontology with standard SPARQL

## Installation

```bash
# Clone and setup virtual environment
git clone https://github.com/your-username/skill-ontology-etl.git
cd skill-ontology-etl

# Create venv and install
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Configuration

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Optional configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6-20250514` | Extraction model |
| `SECURITY_MODEL` | `claude-3-5-haiku-20241022` | Security review model |
| `ANTHROPIC_BASE_URL` | - | Custom API endpoint |

## Usage

### Compile Skills

```bash
# Compile all skills in ./skills/
skill-ontology compile

# Compile specific skill
skill-ontology compile my-skill

# With options
skill-ontology compile --dry-run --reason -v
```

**Options:**

| Flag | Description |
|------|-------------|
| `-i, --input` | Input directory (default: `./skills/`) |
| `-o, --output` | Output file (default: `./ontology/skills.ttl`) |
| `--dry-run` | Preview without saving |
| `--skip-security` | Skip security checks (not recommended) |
| `--reason` | Apply OWL reasoning to infer relationships |
| `-y, --yes` | Skip confirmation prompt |
| `-v, --verbose` | Debug logging |
| `-q, --quiet` | Suppress progress |

### Query the Ontology

```bash
# Basic query
skill-ontology query "SELECT ?s ?n WHERE { ?s ag:nature ?n }"

# JSON output
skill-ontology query "SELECT ?skill WHERE { ?skill a ag:Skill }" -f json
```

### List Skills

```bash
skill-ontology list-skills
```

### Security Audit

```bash
skill-ontology security-audit
```

## Example Ontology Output

```turtle
@prefix ag: <http://agentic.web/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<http://agentic.web/ontology> a owl:Ontology ;
    dcterms:title "Agentic Skills Ontology" .

ag:skill_abc123def456 a ag:Tool ;
    dcterms:identifier "docx-engineering" ;
    ag:contentHash "abc123def456..." ;
    ag:nature "Document generation tool that creates DOCX files" ;
    ag:resolvesIntent "create_docx" , "extract_tables" ;
    ag:hasConstraint "Always validate file paths before writing" ;
    prov:wasDerivedFrom "/skills/docx-engineering/SKILL.md" .

# OWL 2 Property with characteristics
ag:dependsOn a owl:ObjectProperty, owl:AsymmetricProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill ;
    owl:inverseOf ag:enables .

ag:extends a owl:ObjectProperty, owl:TransitiveProperty ;
    owl:inverseOf ag:isExtendedBy .
```

## Architecture

```
skills/                    ontology/
├── skill-a/               └── skills.ttl
│   ├── SKILL.md    ───────────────▲
│   └── references/                │
│       └── guide.md               │
├── skill-b/               ┌───────┴───────┐
│   └── SKILL.md    ──────►│     ETL       │
└── ...                    │   Pipeline    │
                           └───────┬───────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
               EXTRACTOR     TRANSFORMER      LOADER
               (scan/hash)   (LLM+tools)    (RDF+merge)
```

## Components

| Component | File | Responsibility |
|-----------|------|----------------|
| Entry Point | `compiler.py` | Bootstrap CLI |
| CLI | `cli.py` | Click commands |
| Extractor | `extractor.py` | Scan SKILL.md, compute SHA-256 |
| Transformer | `transformer.py` | Tool-use loop with Claude |
| Security | `security.py` | Regex + LLM-as-judge |
| Loader | `loader.py` | OWL 2 serialization, merge, atomic writes |
| Schemas | `schemas.py` | Pydantic models |
| SPARQL | `sparql.py` | Query execution |

## CLI Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Security threat detected |
| 4 | Extraction failed |
| 5 | Ontology load/write error |
| 6 | SPARQL error |
| 7 | Skill not found |
| 130 | Interrupted (Ctrl+C) |

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## License

MIT
