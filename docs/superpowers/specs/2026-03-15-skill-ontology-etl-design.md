# Skill Ontology ETL - Design Specification

**Date**: 2026-03-15
**Status**: Draft
**Author**: Claude + Marcello

---

## Overview

Skill Ontology ETL is a CLI tool that compiles unstructured Markdown agent skills into a W3C-standard **OWL 2** RDF/Turtle ontology. The tool enables "Semantic Routing" by allowing small LLMs to query SPARQL instead of reading long markdown files, avoiding context rot and hallucinations.

## Goals

1. **Eliminate context rot**: Transform prose skills into deterministic, queryable knowledge graphs
2. **Enable semantic routing**: Allow agents to find skills via SPARQL queries
3. **Ensure data integrity**: Deterministic IDs, intelligent merging, atomic writes
4. **Security first**: Defense-in-depth against prompt injection and malicious content
5. **OWL 2 ready**: Ontology uses OWL 2 constructs with property characteristics for future reasoning

## Non-Goals

- OpenAI support (Anthropic-only for tool-use capabilities)
- Real-time skill execution (compilation only)
- GUI interface (CLI only)

---

## Deterministic Algorithms

### ID Generation Algorithm

Skill IDs are derived from the skill directory name:

```python
def generate_skill_id(directory_name: str) -> str:
    """
    Generate deterministic slug from directory name.

    Algorithm:
    1. Lowercase the directory name
    2. Replace spaces and underscores with hyphens
    3. Remove all characters except alphanumeric and hyphens
    4. Collapse consecutive hyphens
    5. Truncate to 64 characters max
    """
    slug = directory_name.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]
```

**Examples**:
- `DOCX-Engineering` → `docx-engineering`
- `My_Awesome Skill!!!` → `my-awesome-skill`
- `skill` → `skill`

### Hash Computation Algorithm

Hash is computed over ALL files in the skill directory:

```python
def compute_skill_hash(skill_dir: Path) -> str:
    """
    Compute SHA-256 hash of all files in skill directory.

    Algorithm:
    1. Recursively find all non-hidden files
    2. Sort files by relative path (alphabetically)
    3. For each file: hash(filename) + hash(content)
    4. Concatenate all hashes
    5. Final SHA-256 of concatenated hash
    """
    hasher = hashlib.sha256()

    files = sorted(
        f for f in skill_dir.rglob('*')
        if f.is_file() and not f.name.startswith('.')
    )

    for file_path in files:
        # Include relative path in hash
        rel_path = file_path.relative_to(skill_dir)
        hasher.update(str(rel_path).encode('utf-8'))
        hasher.update(file_path.read_bytes())

    return hasher.hexdigest()
```

**Note on hash collisions**: SHA-256 collisions are astronomically unlikely (~2^128 effort). If a collision occurred, a modified skill would be incorrectly detected as unchanged. This is an acceptable theoretical risk for this use case.

**Files included**:
- `SKILL.md` (required)
- `references/*.md` (if present)
- `*.py`, `*.js`, etc. (code files)
- Any other non-hidden files

**Files excluded**:
- Hidden files (starting with `.`)
- `.DS_Store`, `__pycache__/`, etc.

---

## Architecture

### High-Level Flow

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

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **Entry Point** | `compiler.py` | Bootstrap CLI |
| **CLI** | `cli.py` | Click commands: compile, query, list-skills, security-audit |
| **Extractor** | `extractor.py` | Scan `SKILL.md` files, compute SHA-256 hashes |
| **Transformer** | `transformer.py` | Tool-use loop with Claude, structured extraction |
| **Security** | `security.py` | Regex patterns + LLM-as-judge (defense in depth) |
| **Loader** | `loader.py` | OWL 2 RDF/Turtle serialization, intelligent merge, atomic writes |
| **Schemas** | `schemas.py` | Pydantic models for extraction |

---

## Data Models

### ExtractedSkill (Pydantic)

```python
class Requirement(BaseModel):
    type: Literal["EnvVar", "Tool", "Hardware", "API", "Knowledge"]
    value: str
    optional: bool = False

class ExecutionPayload(BaseModel):
    executor: Literal["shell", "python", "node", "claude_tool"]
    code: str
    timeout: int | None = None

class ExtractedSkill(BaseModel):
    # Identity
    id: str                          # Deterministic slug
    hash: str                        # SHA-256 of all files

    # Substance (Knowledge Architecture)
    nature: str                      # Essential nature
    genus: str                       # Broader category
    differentia: str                 # What distinguishes it

    # Relations (first-class citizens)
    intents: list[str]               # User intents resolved
    requirements: list[Requirement]  # Prerequisites
    depends_on: list[str] = []       # Other skills needed
    extends: list[str] = []          # Skills built upon
    contradicts: list[str] = []      # Opposing concepts

    # Constraints & Execution
    constraints: list[str]           # Critical rules
    execution_payload: ExecutionPayload | None

    # Provenance
    provenance: str | None           # Source file path
```

---

## LLM Extraction Strategy

### Tool-Use Architecture (Anthropic-only)

Instead of concatenating all files into one prompt, the tool uses Claude's native tool-use:

```
┌──────────────────────────────────────────────────────────────┐
│                        Claude LLM                             │
│  ┌─────────────┐    ┌─────────────┐    ┌────────────────┐   │
│  │ list_files  │───▶│ read_file   │───▶│ extract_skill  │   │
│  │ (discover)  │    │ (as needed) │    │ (final output) │   │
│  └─────────────┘    └─────────────┘    └────────────────┘   │
└──────────────────────────────────────────────────────────────┘
         │                   │                      │
         ▼                   ▼                      ▼
    [file list]        [file content]       [Pydantic object]
```

**Tools available to LLM**:
1. `list_files` - Discover files in skill directory
2. `read_file` - Read specific files (SKILL.md, references, code)
3. `extract_skill` - Submit final structured extraction

### Tool JSON Schemas

```python
TOOLS = [
    {
        "name": "list_files",
        "description": "List all files in the skill directory recursively.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from the skill directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from skill directory root"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "extract_skill",
        "description": "Submit the extracted skill data in structured format.",
        "input_schema": ExtractedSkill.model_json_schema()
    }
]
```

### Tool Response Formats

**list_files response**:
```json
{
    "files": ["SKILL.md", "references/guide.md", "examples/demo.py"]
}
```

**read_file response**:
```json
{
    "content": "# Skill Title\n\nContent here...",
    "path": "SKILL.md"
}
```

**read_file error**:
```json
{
    "error": "File not found: nonexistent.md"
}
```

**extract_skill response** (from tool handler):
```json
{
    "status": "success",
    "message": "Skill extracted successfully"
}
```

### Tool-Use Loop Specification

```python
# Configuration
MAX_ITERATIONS = 20
EXTRACTION_TIMEOUT = 120  # seconds per API call
COMPLETION_TOOL = "extract_skill"  # LLM must call this to finish
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6-20250514")

def tool_result(tool_id: str, content: str) -> dict:
    """Create a tool result message for the conversation."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content
        }]
    }

def tool_use_loop(skill_dir: Path) -> ExtractedSkill:
    """
    Orchestrates the tool-use conversation with Claude.

    Flow:
    1. Send initial message asking to analyze skill
    2. LLM responds with tool calls
    3. Execute tool calls, return results
    4. Repeat until LLM calls extract_skill or max iterations
    5. Validate extraction with Pydantic
    """
    messages = [{"role": "user", "content": "Analyze skill..."}]

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            tools=TOOLS,
            messages=messages,
            timeout=EXTRACTION_TIMEOUT
        )

        # Process tool calls
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "extract_skill":
                    # Validate and return
                    return ExtractedSkill.model_validate(block.input)
                else:
                    # Execute tool, add result to messages
                    result = execute_tool(block.name, block.input, skill_dir)
                    messages.append(tool_result(block.id, result))

        # Check for end_turn without extraction
        if response.stop_reason == "end_turn":
            raise ExtractionError("LLM finished without calling extract_skill")

    raise ExtractionError(f"Max iterations ({MAX_ITERATIONS}) exceeded")
```

**Error Handling**:
- Timeout → raise `ExtractionError`, don't save
- Max iterations → raise `ExtractionError`, don't save
- Invalid tool call → return error JSON, let LLM retry
- Pydantic validation failure → raise `ExtractionError`

**Benefits**:
- No token limits from concatenation
- LLM reads only what's needed
- Preserves file structure context
- Works with arbitrarily large skills

### System Prompt

The system prompt follows the Knowledge Architecture framework:

```text
You are an Ontological Architect. Your task is to analyze agent skills
and extract their essential structure using the Knowledge Architecture framework.

## KNOWLEDGE ARCHITECTURE FRAMEWORK

### Categories of Being
- Tool: Enables action
- Concept: A framework, methodology
- Work: A created artifact generator

### Genus and Differentia
"A is a B that C" - classical definition structure

### Relations as First-Class Citizens
- depends-on: Cannot function without
- extends: Builds upon
- contradicts: In tension with
- implements: Realizes abstraction
- exemplifies: Instance of pattern

### Essential vs Accidental
Essential: Remove it → becomes something else
Accidental: Could be different without changing identity
```

---

## Security Strategy (Defense in Depth)

### Stage 1: Regex Pattern Matching

Fast detection of common attack patterns:

- **Prompt injection**: "ignore previous instructions", "you are now..."
- **Command injection**: `; rm -rf`, `| bash`, command substitution
- **Data exfiltration**: `curl -d`, upload patterns

### Stage 2: LLM-as-Judge

If Stage 1 flags content, a smaller model (Haiku) reviews:

```python
SECURITY_MODEL = os.getenv("SECURITY_MODEL", "claude-3-5-haiku-20241022")
```

**Fail-closed**: Any error → block the content

### Unicode Normalization

Content is normalized before pattern matching to prevent bypass:
- NFC unicode normalization
- Zero-width character removal
- Whitespace normalization

---

## RDF Ontology Mapping

### Namespaces

```turtle
@prefix ag: <http://agentic.web/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
```

### OWL 2 Property Definitions

Properties are defined with OWL 2 characteristics for reasoning-ready semantics:

```python
# Property definitions with OWL characteristics
OWL_PROPERTIES = {
    "dependsOn": {
        "inverse": "enables",
        "asymmetric": True,  # If A depends on B, B cannot depend on A
    },
    "extends": {
        "inverse": "isExtendedBy",
        "transitive": True,  # If A extends B and B extends C, A extends C
    },
    "contradicts": {
        "symmetric": True,  # If A contradicts B, B contradicts A
    },
    "implements": {
        "inverse": "isImplementedBy",
    },
    "exemplifies": {
        "inverse": "isExemplifiedBy",
    },
}
```

**Reasoning extensibility**: These characteristics enable automatic entailment when `owlrl` is added:

```python
# Future: Enable reasoning (not implemented yet)
import owlrl
owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
# Now: A extends B, B extends C → automatically infers A extends C
```

### Predicate Mapping

| Pydantic Field | RDF Predicate | OWL Type | Namespace | Notes |
|----------------|---------------|----------|-----------|-------|
| `id` | `dcterms:identifier` | `owl:DatatypeProperty` | Dublin Core | Literal |
| `nature` | `ag:nature` | `owl:DatatypeProperty` | Custom | Literal |
| `genus` | `skos:broader` | `owl:ObjectProperty` | SKOS | Literal |
| `differentia` | `ag:differentia` | `owl:DatatypeProperty` | Custom | Literal |
| `intents` | `ag:resolvesIntent` | `owl:DatatypeProperty` | Custom | Multiple literals |
| `depends_on` | `ag:dependsOn` | `owl:ObjectProperty, owl:AsymmetricProperty` | Custom | Skill ID, inverse: `ag:enables` |
| `extends` | `ag:extends` | `owl:ObjectProperty, owl:TransitiveProperty` | Custom | Skill ID, inverse: `ag:isExtendedBy` |
| `contradicts` | `ag:contradicts` | `owl:ObjectProperty, owl:SymmetricProperty` | Custom | Concept ID |
| `implements` | `ag:implements` | `owl:ObjectProperty` | Custom | Skill ID, inverse: `ag:isImplementedBy` |
| `exemplifies` | `ag:exemplifies` | `owl:ObjectProperty` | Custom | Pattern ID, inverse: `ag:isExemplifiedBy` |
| `constraints` | `ag:hasConstraint` | `owl:DatatypeProperty` | Custom | Multiple literals |
| `execution_payload` | `ag:hasPayload` | `owl:ObjectProperty` | Custom | Blank node |
| `provenance` | `prov:wasDerivedFrom` | `owl:ObjectProperty` | PROV | Literal (file path) |

### Requirement Mapping (Nested Structure)

Requirements are mapped as blank nodes with typed classes:

```turtle
ag:skill_abc123 ag:hasRequirement ag:req_x7z9k2 .

ag:req_x7z9k2 a ag:RequirementEnvVar ;
    ag:requirementValue "API_KEY" ;
    ag:isOptional false .
```

**Requirement type → RDF class mapping**:
| Requirement Type | RDF Class |
|------------------|-----------|
| `EnvVar` | `ag:RequirementEnvVar` |
| `Tool` | `ag:RequirementTool` |
| `Hardware` | `ag:RequirementHardware` |
| `API` | `ag:RequirementAPI` |
| `Knowledge` | `ag:RequirementKnowledge` |

**Requirement URI generation**:
```python
req_uri = f"ag:req_{sha256(f'{type}:{value}')[:8]}"
```

### Execution Payload Mapping

Payloads are mapped as blank nodes:

```turtle
ag:skill_abc123 ag:hasPayload ag:payload_abc123 .

ag:payload_abc123
    ag:executor "shell" ;
    ag:code "echo hello" ;
    ag:timeout 30 .
```

**Payload fields**:
| Field | Predicate | Type |
|-------|-----------|------|
| `executor` | `ag:executor` | Literal |
| `code` | `ag:code` | Literal |
| `timeout` | `ag:timeout` | Literal (integer) |

### Ontology Header

Every ontology file starts with OWL 2 declarations:

```turtle
@prefix ag: <http://agentic.web/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skos: <http://www.w3.org/2004/02/skos/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<http://agentic.web/ontology> a owl:Ontology ;
    dcterms:title "Agentic Skills Ontology" ;
    dcterms:description "Knowledge graph of agent skills extracted from markdown" .

# Classes
ag:Skill a owl:Class .
ag:Tool a owl:Class ; rdfs:subClassOf ag:Skill .
ag:Concept a owl:Class ; rdfs:subClassOf ag:Skill .
ag:Work a owl:Class ; rdfs:subClassOf ag:Skill .

# Object Properties with OWL characteristics
ag:dependsOn a owl:ObjectProperty, owl:AsymmetricProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill ;
    owl:inverseOf ag:enables .

ag:extends a owl:ObjectProperty, owl:TransitiveProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill ;
    owl:inverseOf ag:isExtendedBy .

ag:contradicts a owl:ObjectProperty, owl:SymmetricProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill .

ag:implements a owl:ObjectProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill ;
    owl:inverseOf ag:isImplementedBy .

ag:exemplifies a owl:ObjectProperty ;
    rdfs:domain ag:Skill ;
    rdfs:range ag:Skill ;
    owl:inverseOf ag:isExemplifiedBy .
```

### Example Skill Instance

```turtle
ag:skill_abc123def456 a ag:Tool ;
    dcterms:identifier "docx-engineering" ;
    ag:contentHash "abc123def456789..." ;
    ag:nature "Document generation tool that creates DOCX files from templates" ;
    skos:broader "Document Processing Tool" ;
    ag:differentia "that uses python-docx library" ;
    ag:resolvesIntent "create_docx" , "extract_tables" ;
    ag:hasRequirement ag:req_k8m2p5 ;
    ag:hasConstraint "Always validate file paths before writing" ;
    ag:hasPayload ag:payload_abc123 ;
    prov:wasDerivedFrom "/skills/docx-engineering/SKILL.md" .

ag:req_k8m2p5 a ag:RequirementTool ;
    ag:requirementValue "python-docx" ;
    ag:isOptional false .

ag:payload_abc123
    ag:executor "python" ;
    ag:code "from docx import Document\ndoc = Document()" ;
    ag:timeout 60 .
```

---

## Merge Strategy

### Intelligent Append

1. Load existing ontology, extract `hash → URI` mapping
2. For each new skill:
   - If hash exists → skip (unchanged)
   - If same ID but different hash → remove old, add new
   - If new ID → add
3. Preserve all unmodified triples

### Atomic Writes

```
1. Backup existing skills.ttl → backups/skills_YYYYMMDD_HHMMSS.ttl
2. Write to skills.ttl.tmp
3. Rename skills.ttl.tmp → skills.ttl (atomic)
4. On failure: restore from backup
5. Cleanup: After successful write, delete oldest backups keeping only 5
```

**Cleanup timing**: Backup cleanup runs immediately after successful atomic rename, in the same operation.

---

## OWL Reasoning

### Optional Entailment

When `--reason` flag is enabled, the ontology is expanded with inferred triples:

```python
import owlrl
from rdflib import Graph

def apply_reasoning(graph: Graph) -> Graph:
    """
    Apply OWL 2 RL reasoning to infer new triples.

    Inferences:
    - Inverse: A dependsOn B → B enables A
    - Transitive: A extends B, B extends C → A extends C
    - Symmetric: A contradicts B → B contradicts A

    Modifies graph in-place and returns it.
    """
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
    return graph
```

### Performance Considerations

- Reasoning is disabled by default for performance
- Large ontologies (1000+ skills) may take several seconds
- Inferred triples are not persisted unless saved
- Use `--reason` only when you need the expanded graph for queries

---

## CLI Commands

### `skill-etl compile [SKILL_NAME]`

Compile skills into ontology.

- No argument: Compile all skills in `./skills/`
- With SKILL_NAME: Compile specific skill (shows preview, asks confirmation)

**Options**:
- `-i, --input`: Input directory (default: `./skills/`)
- `-o, --output`: Output file (default: `./ontology/skills.ttl`)
- `--dry-run`: Preview without saving
- `--skip-security`: Skip security checks (not recommended)
- `--reason / --no-reason`: Apply OWL reasoning to infer relationships (default: `--no-reason`)
- `-y, --yes`: Skip confirmation prompt
- `-v, --verbose`: Enable debug logging
- `-q, --quiet`: Suppress progress output

**Flow for single skill**:
1. Security check (regex → LLM if flagged)
2. LLM extraction via tool-use
3. Display detailed preview
4. Ask: "Add this skill to the ontology?"
5. If yes: merge and save

### `skill-etl query "<sparql>"`

Execute SPARQL query against ontology.

**Options**:
- `-o, --ontology`: Ontology file (default: `./ontology/skills.ttl`)
- `-f, --format`: Output format (table/json/turtle)

**Example**:
```bash
skill-etl query "SELECT ?s ?n WHERE { ?s ag:nature ?n }" -f json
```

### SPARQL Implementation

Uses `rdflib` for SPARQL execution:

```python
from rdflib import Graph

def execute_sparql(ontology_path: Path, query: str, format: str) -> str:
    """
    Execute SPARQL query and format results.

    Implementation:
    1. Load ontology with rdflib
    2. Execute query with graph.query()
    3. Format results based on output format
    """
    graph = Graph()
    graph.parse(ontology_path, format="turtle")

    try:
        results = graph.query(query)
    except Exception as e:
        raise SPARQLError(f"Invalid query: {e}")

    return format_results(results, format)

def format_results(results, format: str) -> str:
    """Format SPARQL results for output."""
    if format == "json":
        import json
        rows = [dict(row) for row in results]
        return json.dumps(rows, indent=2, default=str)

    elif format == "turtle":
        lines = []
        for row in results:
            lines.extend(str(v) for v in row)
        return "\n".join(lines)

    else:  # table
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Query Results")
        for var in results.vars:
            table.add_column(str(var))

        for row in results:
            table.add_row(*[str(v) for v in row])

        console = Console()
        with console.capture() as capture:
            console.print(table)
        return capture.get()
```

**Result serialization by format**:

| Format | Implementation |
|--------|----------------|
| `table` | Use `rich.Table`, columns from `results.vars`, rows from result bindings |
| `json` | `[dict(row) for row in results]`, serialize with `json.dumps()` |
| `turtle` | For CONSTRUCT queries, serialize graph; for SELECT, print bindings |

**Query validation**:
- No mutations (INSERT/DELETE not supported)
- Must be valid SPARQL syntax
- Namespaces must be declared or use full URIs

### `skill-etl list-skills`

List all skills in the ontology.

### `skill-etl security-audit`

Re-validate all skills in ontology against current security patterns.

### `skill-etl --version`

Display tool version.

### CLI Exit Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| `0` | Success | Command completed successfully |
| `1` | General error | Unhandled exception, generic failure |
| `2` | Invalid arguments | CLI argument parsing failed |
| `3` | Security threat | Content blocked by security pipeline |
| `4` | Extraction failed | LLM extraction did not complete |
| `5` | Ontology error | Load/parse/write ontology failed |
| `6` | SPARQL error | Invalid query or execution failed |
| `7` | Not found | Skill or file not found |
| `130` | Interrupted | User cancelled (Ctrl+C) |

### Logging Strategy

```python
# Configuration
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

def setup_logging(verbose: bool, quiet: bool):
    """
    Configure logging based on verbosity flags.

    -v, --verbose: DEBUG level, show all messages
    (default): INFO level, show progress and warnings
    -q, --quiet: WARNING level, suppress progress messages
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )
```

**Log levels usage**:
- `DEBUG`: Tool call details, file contents, hash computations
- `INFO`: Progress updates, skill counts, file operations
- `WARNING`: Skipped files, security flags, recoverable errors
- `ERROR`: Failures that halt processing
- `CRITICAL`: Security breaches, data corruption

**Log file**: No persistent log file by default. All output to stderr.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `ANTHROPIC_BASE_URL` | No | - | Custom API endpoint |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-6-20250514` | Extraction model |
| `SECURITY_MODEL` | No | `claude-3-5-haiku-20241022` | Security review model |

### Timeout Configuration

| Operation | Timeout | Configurable |
|-----------|---------|--------------|
| LLM extraction API call | 120s | No (hardcoded) |
| Security review API call | 30s | No (hardcoded) |
| Tool-use max iterations | 20 | No (hardcoded) |

**Retry behavior**: No automatic retries. On timeout, raise error and exit.

### Empty Skills Directory Behavior

When `./skills/` is empty or contains no `SKILL.md` files:
1. Print: "No SKILL.md files found in input directory"
2. Exit with code 0 (success, nothing to do)

### Skill Name Validation

For `skill-etl compile <SKILL_NAME>`:
- Valid: alphanumeric, hyphens, underscores
- Invalid: paths with `/`, `.`, `..`, hidden dirs (starting with `.`)
- On invalid: print error, list available skills, exit code 7

---

## File Structure

```
skill-ontology-etl/
├── compiler.py           # Entry point
├── cli.py                # Click CLI commands
├── extractor.py          # Skill scanning & hashing
├── transformer.py        # LLM tool-use extraction
├── security.py           # Security pipeline
├── loader.py             # RDF serialization & merge
├── schemas.py            # Pydantic models
├── requirements.txt      # Dependencies
├── pyproject.toml        # Package config
├── README.md
├── LICENSE               # MIT
├── CLAUDE.md
├── .gitignore
├── skills/               # Input skills
│   └── (skill directories with SKILL.md)
├── ontology/             # Output
│   ├── skills.ttl
│   └── backups/
└── tests/                # 100% coverage
    ├── conftest.py
    ├── test_extractor.py
    ├── test_security.py
    ├── test_loader.py
    ├── test_schemas.py
    ├── test_transformer.py
    ├── test_cli.py
    └── test_integration.py
```

---

## Dependencies

```
anthropic>=0.39.0
click>=8.1.0
pydantic>=2.0.0
rdflib>=7.0.0
rich>=13.0.0
owlrl>=1.0.0
```

**Dev dependencies**:
```
pytest>=8.0.0
pytest-cov>=4.0.0
ruff>=0.1.0
mypy>=1.0.0
```

---

## Testing Strategy

### Requirements

- **Test-Driven Development**: Write tests before implementation
- **100% Code Coverage**: All modules must have complete coverage
- **Unit Tests**: Each component tested in isolation
- **Integration Tests**: Full pipeline tests (require API key)

### Coverage Targets

| Module | Target |
|--------|--------|
| `schemas.py` | 100% |
| `extractor.py` | 100% |
| `security.py` | 100% |
| `loader.py` | 100% |
| `transformer.py` | 100% |
| `cli.py` | 100% |

### Test Categories

1. **Unit Tests**: Mock external dependencies (LLM, filesystem)
2. **Integration Tests**: Real API calls (marked `@pytest.mark.integration`)
3. **Security Tests**: Pattern matching, bypass attempts

### Run Command

```bash
pytest --cov=. --cov-report=html --cov-fail-under=100
```

---

## Error Handling

### Fail-Closed Principles

| Scenario | Behavior |
|----------|----------|
| Security threat detected | Block skill, report threats |
| LLM extraction fails | Raise error, don't save partial data |
| Ontology parse error | Raise error, suggest restore from backup |
| Write failure | Restore from backup automatically |
| Invalid SPARQL query | Return error, don't modify ontology |

### Error Types

```python
class SkillETLError(Exception):
    """Base exception for skill-etl errors."""
    exit_code: int = 1

class OntologyLoadError(SkillETLError):
    """Raised when ontology loading/parsing fails."""
    exit_code = 5

class SecurityError(SkillETLError):
    """Raised when security check fails."""
    exit_code = 3

class ExtractionError(SkillETLError):
    """Raised when LLM extraction fails."""
    exit_code = 4

class SPARQLError(SkillETLError):
    """Raised when SPARQL query fails."""
    exit_code = 6

class SkillNotFoundError(SkillETLError):
    """Raised when skill directory or file not found."""
    exit_code = 7
```

---

## Success Criteria

1. ✅ CLI compiles skills to valid OWL 2 RDF/Turtle
2. ✅ SPARQL queries return correct results
3. ✅ Merge preserves unmodified skills
4. ✅ Security blocks malicious content
5. ✅ 100% test coverage
6. ✅ Atomic writes with backup/restore
7. ✅ Tool-use handles arbitrarily large skills
8. ✅ OWL property characteristics (inverse, transitive, symmetric) defined
9. ✅ Optional OWL reasoning with `--reason` flag

---

## Future Considerations

- [ ] Web UI for ontology browsing
- [ ] Skill versioning and history
- [ ] Multi-language support
- [ ] Custom ontology namespaces per project
