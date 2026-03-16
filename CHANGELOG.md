# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-03-16

### Added

#### Core Infrastructure
- **schemas.py** - Pydantic models for structured skill extraction
  - `Requirement` model with types: EnvVar, Tool, Hardware, API, Knowledge
  - `ExecutionPayload` model for code execution
  - `ExtractedSkill` model with Knowledge Architecture fields (nature, genus, differentia)

- **exceptions.py** - Custom exception hierarchy with exit codes
  - `SkillETLError` (base, exit_code=1)
  - `SecurityError` (exit_code=3)
  - `ExtractionError` (exit_code=4)
  - `OntologyLoadError` (exit_code=5)
  - `SPARQLError` (exit_code=6)
  - `SkillNotFoundError` (exit_code=7)

#### Extraction Pipeline
- **extractor.py** - Deterministic ID and hash generation
  - `generate_skill_id()` - Slugifies directory names to kebab-case (max 64 chars)
  - `compute_skill_hash()` - SHA-256 hash of all skill files (sorted, recursive)

- **transformer.py** - LLM tool-use extraction
  - Tool definitions: `list_files`, `read_file`, `extract_skill`
  - Tool-use loop with max 20 iterations, 120s timeout
  - Knowledge Architecture system prompt
  - Path traversal protection in file reading

#### Security Pipeline
- **security.py** - Defense-in-depth security checks
  - Stage 1: Regex pattern matching for:
    - Prompt injection (ignore instructions, system:, you are now)
    - Command injection (; rm, | bash, command substitution)
    - Data exfiltration (curl -d, wget --data)
    - Path traversal (../, /etc/passwd)
    - Credential exposure (api_key=, password=)
  - Stage 2: LLM-as-judge with Haiku for nuanced review
  - Unicode normalization (NFC, zero-width removal)
  - Fail-closed error handling

#### Ontology Loader
- **loader.py** - OWL 2 RDF/Turtle serialization
  - Full OWL 2 property characteristics:
    - `ag:dependsOn` - AsymmetricProperty with inverse `ag:enables`
    - `ag:extends` - TransitiveProperty with inverse `ag:isExtendedBy`
    - `ag:contradicts` - SymmetricProperty
    - `ag:implements` / `ag:exemplifies` with inverses
  - Skill serialization to RDF triples
  - Intelligent merge strategy:
    - Skip unchanged skills (hash match)
    - Update modified skills (same ID, different hash)
    - Add new skills
  - Atomic writes with backup/restore pattern
  - `--reason` flag for OWL reasoning with owlrl

#### SPARQL Engine
- **sparql.py** - Query execution against ontology
  - SELECT query support
  - Mutation prevention (no INSERT/DELETE)
  - Multiple output formats:
    - `table` - Rich tables for CLI
    - `json` - JSON array of results
    - `turtle` - Turtle-formatted bindings

#### CLI Interface
- **cli.py** - Complete Click-based CLI
  - Commands:
    - `compile [SKILL_NAME]` - Compile skills to ontology
    - `query "<sparql>"` - Execute SPARQL queries
    - `list-skills` - List all skills in ontology
    - `security-audit` - Re-validate skills against security patterns
  - Options:
    - `-i, --input` - Input directory (default: `./skills/`)
    - `-o, --output` - Output file (default: `./ontology/skills.ttl`)
    - `--dry-run` - Preview without saving
    - `--skip-security` - Skip security checks
    - `--reason/--no-reason` - Apply OWL reasoning
    - `-y, --yes` - Skip confirmation
    - `-v, --verbose` - Debug logging
    - `-q, --quiet` - Suppress progress
  - Proper exit codes per spec
  - Logging configuration

- **compiler.py** - Entry point for package

### Dependencies
- `anthropic>=0.39.0` - Claude API for extraction
- `click>=8.1.0` - CLI framework
- `pydantic>=2.0.0` - Data validation
- `rdflib>=7.0.0` - RDF graph handling
- `rich>=13.0.0` - Terminal formatting
- `owlrl>=1.0.0` - OWL reasoning

### Dev Dependencies
- `pytest>=8.0.0` - Testing
- `pytest-cov>=4.0.0` - Coverage
- `ruff>=0.1.0` - Linting
- `mypy>=1.0.0` - Type checking

### Testing
- **42 tests** with 86% code coverage
- Test files:
  - `test_schemas.py` - Pydantic model validation
  - `test_exceptions.py` - Exception exit codes
  - `test_extractor.py` - ID/hash generation
  - `test_transformer.py` - Tool-use loop, tool execution
  - `test_security.py` - Pattern matching, LLM review
  - `test_loader.py` - OWL properties, serialization, merge
  - `test_sparql.py` - Query execution, formatting
  - `test_cli.py` - CLI commands and options

### Documentation
- **README.md** - Updated with full usage instructions
- Architecture diagram
- CLI command reference
- Exit codes table

---

## Implementation Notes

### Knowledge Architecture Framework
The extraction follows the Knowledge Architecture framework:
- **Categories of Being**: Tool, Concept, Work
- **Genus and Differentia**: "A is a B that C" definition structure
- **Relations as First-Class Citizens**: depends-on, extends, contradicts, implements, exemplifies

### OWL 2 Design Decisions
- Properties defined with characteristics for future reasoning
- Inverse properties enable bidirectional queries
- Transitive properties enable inference chains
- Asymmetric properties prevent circular dependencies

### Security Philosophy
- Fail-closed: Any error blocks content
- Defense-in-depth: Regex + LLM review
- Unicode normalization prevents bypass attempts
- Pattern matching for common attack vectors
