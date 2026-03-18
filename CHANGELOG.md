# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).


## [0.7.0] - 2026-03-18

### Changed

#### CLI Tooling Updates for Knowledge Nodes

Updated the PR #5 tooling to work with the current ontology structure (knowledge_nodes and requirements):

- **core/explainer.py** — Updated `SkillSummary` to extract:
  - `knowledge_nodes`: list of `KnowledgeNodeSummary` (node_type, directive_content, applies_to_context, has_rationale, severity_level)
  - `requirements`: list of `RequirementSummary` (requirement_value, is_optional)
  - Removed: `depends_on`, `extends`, `contradicts` (not used in current skills)

- **core/differ.py** — Updated drift detection:
  - Fixed `_diff_requirements()` to use `oc:hasRequirement` instead of `oc:requires`
  - Added `_diff_knowledge_nodes()` to track `oc:impartsKnowledge` changes (cosmetic)
  - Updated SPARQL queries in suggestions to use correct properties

- **core/linter.py** — Updated checks:
  - Replaced `orphan-skill` with `unreachable-state` check (skills with unreachable required states)
  - Kept: `dead-state`, `circular-dep`, `duplicate-intent` (still valid)

- **core/graph_export.py** — Changed from dependency graph to state transition graph:
  - Edges now show: Skill A `yieldsState` X → Skill B `requiresState` X
  - Visualizes actual execution flow between skills

- **core/tests/** — Updated all test files for the new functionality

## [0.6.0] - 2026-03-18

### Added

- Added repo-local `.env` loading for the Python compiler so extraction and security checks can
  read `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, and model overrides without manual shell exports
- Added `.env.example` with the compiler variables needed for Anthropic-compatible providers

### Changed

- Updated compiler documentation with `.env`-based configuration and an example nested-skill
  compile command
- Updated Claude Code MCP troubleshooting guidance to call out stale background processes after
  rebuilding the Rust server
- Relaxed SHACL state validation to allow novel states (e.g., `oc:SpreadsheetCreated`) without
  requiring them to be pre-defined in the core ontology - the MCP server resolves states at runtime
- Updated README.md validation table to reflect relaxed state constraints (IRI required, not
  necessarily `oc:State` instance)

### Fixed

- Fixed Rust MCP `tools/call` responses so `structuredContent` is always a record object, avoiding
  Claude Code schema errors for tools returning arrays such as `list_skills` and
  `find_skills_by_intent`
- Fixed pySHACL validation bug where RDFS inference caused Literal values in dependency relations
  to be treated as focus nodes for validation - now uses `inference='none'`
- Fixed SHACL `sh:class oc:State` constraint that rejected novel states extracted by LLM -
  removed class constraint, keeping only `sh:nodeKind sh:IRI`
- Fixed skill dependency serialization to use Literal strings instead of URIRef to prevent
  pySHACL from validating them as skill nodes
- Fixed duplicate `skill_output_paths` entries when skills were skipped due to hash match

## [0.5.0] - 2026-03-17

### Added

#### Static Linter (`ontoclaw lint`)

Analyses the compiled ontology without calling the Anthropic API.
Catches structural issues before they reach runtime or waste API tokens.

- **core/linter.py** — `lint_ontology(ttl_path) → LintResult`
  - `dead-state` (warning): skill requiresState X but no skill yieldsState X
  - `circular-dep` (error): cycle detected in oc:dependsOn graph via DFS
  - `duplicate-intent` (error): two skills resolve the same intent string
  - `orphan-skill` (info): isolated skill with no dependents and unreachable states
- **core/tests/test_linter.py** — 6 tests
- **core/cli.py** — `lint` command: `--ontology`, `--format` (rich/json), `--errors-only`
  - Exit code 1 when errors found (CI gate)

#### Dependency Graph Visualiser (`ontoclaw graph`)

Exports the skill relationship graph as Mermaid or Graphviz DOT.

- **core/graph_export.py** — `build_graph(ttl_path, fmt, skill_filter) → str`
  - Covers oc:dependsOn (solid arrow), oc:extends (dashed), oc:contradicts (bidirectional)
  - Deduplicates symmetric contradicts edges
  - Optional 1-hop `skill_filter` for subgraph output
- **core/tests/test_graph_export.py** — 7 tests
- **core/cli.py** — `graph` command: `--ontology`, `--format` (mermaid/dot), `--skill`, `--output`

#### Skill Explainer (`ontoclaw explain <skill-id>`)

Renders a Rich summary card for a compiled skill without reading raw Turtle.

- **core/explainer.py** — `explain_skill(ttl_path, skill_id) → SkillSummary | None`
  - Extracts: intents, requiresState, yieldsState, handlesFailure, dependsOn,
    extends, contradicts, executor (from payload node), contentHash, generatedBy
  - `list_skill_ids(ttl_path)` — lists all available skill IDs for autocomplete/error hints
- **core/tests/test_explainer.py** — 9 tests
- **core/cli.py** — `explain` command: positional `SKILL_ID`, `--ontology`
  - Prints available IDs when skill not found

#### Migration Guidance (`ontoclaw diff --suggest`)

Extends the Skill Drift Detector with actionable remediation for breaking changes.

- **core/differ.py** — `MigrationSuggestion` dataclass + `DriftReport.suggestions()`
  - `skill-removed`: SPARQL to find agents with oc:dependsOn pointing to removed skill
  - `intent-renamed`: SPARQL to find callers of the old intent string
  - `requirement-added`: SPARQL to find skills with the new oc:requires relationship
- **core/drift_report.py** — `print_suggestions()` Rich-formatted output
- **core/cli.py** — `--suggest` flag on `diff` command
- **core/tests/test_differ.py** — 4 new suggestion tests
- **core/tests/test_cli.py** — 1 new CLI test for `--suggest`
#### Local MCP Server

- Added a new **Rust-based local MCP server** under `mcp/`
  - Loads compiled OntoClaw ontologies from `.ttl` files
  - Speaks MCP over `stdio`
  - Auto-discovers `ontoskills/` from the current directory and its parents
  - Can also be pointed at a custom ontology root with `--ontology-root`

#### MCP Tooling

- Implemented MCP tools for semantic skill discovery and planning:
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

#### Planning Engine

- Added state-aware planning inside the Rust MCP catalog:
  - checks `requiresState` against caller-provided current states
  - finds preparatory skills through `yieldsState`
  - ranks candidate plans by unresolved states and step count
  - prefers direct skills over setup-heavy alternatives when possible

#### Rust Test Coverage

- Added Rust unit tests for:
  - intent lookup
  - payload lookup
  - planning with preparatory skills
  - planner ranking preference for direct skills

### Changed

#### Documentation

- Updated `README.md` to reflect that `mcp/` is now implemented
- Added MCP usage, run commands, and verification instructions
- Updated `mcp/README.md` with scope, tool list, auto-discovery behavior, and run instructions
- Added `mcp/CLAUDE_CODE_GUIDE.md` with build, run, registration, verification, and troubleshooting steps for Claude Code

#### MCP Compatibility

- Updated the Rust MCP server to support Claude Code's current handshake behavior
  - supports protocol version `2025-11-25`
  - accepts line-delimited JSON requests on `stdio` in addition to framed `Content-Length` transport
  - replies using the same wire mode used by the client
  - exposes empty `resources/list`, `resources/templates/list`, and `prompts/list` endpoints for client compatibility

---

## [0.4.0] - 2026-03-17

### Added

#### Skill Drift Detector (`ontoclaw diff`)

Semantic diffing system that compares two versions of the compiled ontology
and classifies every change by its impact on agents querying the graph.

- **core/snapshot.py** — Snapshot manager
  - `save_snapshot(ttl_path)`: saves a timestamped, SHA-256-hashed copy of
    `index.ttl` into `.ontoclaw/snapshots/` after every successful compile
  - `get_latest_snapshot()`: returns the second-to-last snapshot (baseline
    for the next diff)
  - `_prune_snapshots(keep=10)`: keeps only the 10 most recent snapshots

- **core/differ.py** — Semantic diff engine
  - `SkillChange` dataclass: `skill_id`, `change_type` (breaking / additive /
    cosmetic), `category`, `description`, `old_value`, `new_value`
  - `DriftReport` dataclass: aggregates changes with `has_breaking` and
    `is_clean` properties
  - `compute_diff(old_ttl, new_ttl)`: loads two RDF graphs and diffs them
    across four semantic axes — intents, requiresState/yieldsState, oc:requires,
    and skill presence
  - Removed intent → breaking; added intent → additive
  - Added oc:requires → breaking; removed oc:requires → additive
  - Removed skill entirely → breaking; new skill → additive

- **core/drift_report.py** — Report formatter
  - `print_report()`: Rich-formatted terminal output with colour-coded panels
    and summary table
  - `export_json()`: serialises `DriftReport` to JSON for CI/CD pipelines

- **core/cli.py** — `diff` command and compile hook
  - New `diff` command with options: `--from`, `--to`, `--breaking-only`,
    `--format` (rich/json/md), `--output`
  - Exit code 9 on breaking changes (pipeline gate)
  - `save_snapshot()` hook added to `compile`: every successful compile
    automatically creates a snapshot

- **core/exceptions.py** — `DriftDetectedError(SkillETLError)`, exit code 9

- **core/tests/test_differ.py** — 5 unit tests for the differ module
- **core/tests/test_cli.py** — 6 CLI tests for the `diff` command
### Breaking Changes

#### Output Filename Change

- **`skill.ttl` → `ontoskill.ttl`** - Output skill modules are now named `ontoskill.ttl` instead of `skill.ttl`
  - Affects all path references in code and tests
  - Run `ontoclaw compile --force` after upgrading to regenerate modules with new naming

### Changed

#### Perfect Mirroring Architecture

The compiler now acts as a **Semantic Bundler** - the output directory (`ontoskills/`) is a perfect, executable mirror of the input directory (`skills/`).

- **Traversal logic** - Now iterates through ALL files recursively using `rglob("*")` instead of only finding directories with `SKILL.md`
- **3-Rule File Processing**:
  - **Rule A (Core Skills)**: `SKILL.md` → compiled via LLM → `ontoskill.ttl`
  - **Rule B (Auxiliary Markdown)**: `*.md` → compiled via LLM → `*.ttl` (logged, pipeline pending)
  - **Rule C (Asset Copying)**: Non-markdown files (`.py`, `.js`, `.xsd`, etc.) → direct copy via `shutil.copy2`

#### Orphan Cleanup Enhanced

- **`clean_orphaned_files()`** - Replaces `clean_orphaned_skills()` with comprehensive mirror sync:
  - `ontoskill.ttl` → `SKILL.md` mapping
  - `*.ttl` → `*.md` mapping (auxiliary markdown)
  - Direct asset mapping (non-ttl files map to same path)
- **`SYSTEM_FILES` safeguard** - Protects compiler-generated files from cleanup:
  - `ontoclaw-core.ttl` - Core TBox ontology
  - `index.ttl` - Manifest with owl:imports

### Removed

- **`clean_orphaned_skills()`** - Replaced by `clean_orphaned_files()` (no backward compatibility wrapper)
- **Legacy `skill.ttl` references** - All code and tests updated to use `ontoskill.ttl`

### Testing

- **test_storage.py** - 8 new tests for perfect mirroring:
  - `test_clean_orphaned_files_removes_orphan`
  - `test_clean_orphaned_files_preserves_valid`
  - `test_clean_orphaned_files_dry_run`
  - `test_clean_orphaned_files_preserves_system_files`
  - `test_clean_orphaned_files_removes_orphan_asset`
  - `test_clean_orphaned_files_preserves_valid_asset`
  - `test_clean_orphaned_files_auxiliary_markdown_mapping`
  - `test_clean_orphaned_files_preserves_auxiliary_with_source`
  - `test_system_files_constant`
- All existing tests updated for `ontoskill.ttl` naming
- Removed backward compatibility test

### Test Summary

- **156 tests** pass (3 deselected integration tests)

### Added

#### Core Ontology Enhancements

- **`oc:executionPath`** - New DatatypeProperty for external asset paths
  - Domain: `oc:ExecutionPayload`
  - Supports Perfect Mirroring asset bundler architecture
  - Enables referencing external script files (`.py`, `.cjs`, etc.) copied by the compiler

- **`owl:disjointWith`** - DeclarativeSkill and ExecutableSkill are now explicitly mutually exclusive
  - Enforces OWL 2 DL ($\mathcal{SROIQ}^{(D)}$) strictness
  - A skill cannot be both declarative and executable

#### SHACL Validation Updates

- **XOR constraint** - ExecutionPayload must have either `oc:code` OR `oc:executionPath`
  - `sh:or` constraint ensures at least one is present
  - Inline code or external asset path (not both required)
- **`oc:code`** - No longer strictly mandatory (minCount removed)
- **`oc:executionPath`** - New property constraint (maxCount 1, xsd:string)

---

## [0.3.0] - 2026-03-17

### Changed

#### Architecture Refactoring

The monolithic `loader.py` (855 lines) has been refactored into 3 focused modules following the Single Responsibility Principle:

- **core_ontology.py** (~344 lines) - Namespace management and core TBox ontology creation
- **serialization.py** (~168 lines) - Pydantic-to-RDF serialization with SHACL gatekeeper
- **storage.py** (~484 lines) - File I/O, intelligent merging, orphan cleanup

### Added

#### Cache Invalidation

- **`--force` flag** for `compile` command - Bypass hash-based caching to force recompilation of all skills
  - Useful when SHACL schemas or LLM prompts are updated
  - Usage: `ontoclaw compile --force` or `ontoclaw compile -f`

#### Lifecycle Management

- **`clean_orphaned_skills()`** function - Automatically removes `.ttl` files when source `SKILL.md` is deleted
  - Runs at the start of every compilation
  - Supports `dry_run` mode for preview
  - Logs all orphaned files found and removed

#### Bug Fixes

- **`serialize_skill_to_module()` signature** - Fixed pre-existing bug where CLI passed 3 arguments but function only accepted 2
  - Added `output_base: Optional[Path] = None` parameter with sensible default

#### Testing

- **test_core_ontology.py** (41 tests) - Tests for namespace and core ontology functions
- **test_serialization.py** (10 tests) - Tests for RDF serialization including SHACL gatekeeper
- **test_storage.py** (31 tests) - Tests for file I/O, merging, and orphan cleanup
  - 6 new tests for `clean_orphaned_skills()` function
  - Tests for `merge_skill()` force parameter
- **test_cli.py** - 2 new tests for `--force` flag behavior

### Removed

- **loader.py** - Replaced by core_ontology.py, serialization.py, and storage.py
- **test_loader.py** - Split into test_core_ontology.py, test_serialization.py, and test_storage.py

### Test Summary

- **150 tests** pass (3 deselected)
- All SHACL validation tests pass (gatekeeper preserved)

---

## [0.2.0] - 2026-03-16

### Added

#### SHACL Validation Gatekeeper

A constitutional validation layer that ensures every skill ontology is logically valid before being written to disk. Invalid skills are blocked with detailed error reports.

- **validator.py** - SHACL validation module
  - `ValidationResult` NamedTuple with `conforms`, `results_text`, `results_graph`
  - `load_shacl_shapes()` - Loads constitutional shapes from `specs/ontoclaw.shacl.ttl`
  - `load_core_ontology()` - Loads TBox for `sh:class` validation (critical for state validation)
  - `validate_skill_graph()` - Validates RDF graph against SHACL shapes with RDFS inference
  - `validate_and_raise()` - Raises `OntologyValidationError` on failure

- **specs/ontoclaw.shacl.ttl** - Constitutional SHACL shapes
  - `oc:SkillShape` - Base constraints for all skills
    - `resolvesIntent` minCount 1 (required)
    - `generatedBy` exactly 1 (required attestation)
    - `requiresState`, `yieldsState`, `handlesFailure` must be IRIs of `oc:State`
  - `oc:ExecutableSkillShape` - Constraints for skills with payloads
    - `hasPayload` exactly 1, must be `oc:ExecutionPayload`
  - `oc:DeclarativeSkillShape` - Constraints for knowledge-only skills
    - `hasPayload` maxCount 0 (forbidden)
  - `oc:ExecutionPayloadShape` - Payload constraints
    - `executor` must be one of: shell, python, node, claude_tool
    - `code` required, string
    - `timeout` optional, integer
  - `oc:StateShape` - State instance constraints (warning level)
    - `rdfs:label` recommended
  - All error messages in Italian

- **schemas.py** - Added computed `skill_type` property
  - Automatically returns "executable" or "declarative" based on `execution_payload` presence
  - Uses Pydantic `@computed_field` for serialization

- **loader.py** - Added skill subclasses and validation hooks
  - `oc:ExecutableSkill` and `oc:DeclarativeSkill` added to core ontology
  - `serialize_skill()` now adds appropriate subclass type based on `skill_type`
  - `serialize_skill_to_module()` validates before write - invalid skills NOT written
  - `merge_skill()` validates before return - invalid skills NOT merged

- **exceptions.py** - Added `OntologyValidationError`
  - Exit code 8
  - Includes full SHACL validation report

#### Testing

- **test_validation.py** - 5 comprehensive SHACL validation tests
  - Valid executable skill passes
  - Skill missing intent fails with appropriate message
  - Declarative skill (no payload) passes
  - Literal as state fails (IRI required)
  - Executable skill with payload passes
- **test_loader.py** - 3 new tests for validation hooks
  - `serialize_skill_to_module` blocks invalid skills
  - File not written on validation failure
  - `merge_skill` blocks invalid skills
- **test_schemas.py** - 2 new tests for `skill_type` property
  - Computed as "executable" with payload
  - Computed as "declarative" without payload
- **test_exceptions.py** - 1 new test for `OntologyValidationError`

### Changed

- Existing tests updated to include required `generated_by` field for SHACL compliance
- Test count increased from 42 to 91 tests

### Dependencies

- Added `pyshacl>=0.25.0` for SHACL validation

---

## [0.1.0] - 2026-03-16

### Added

#### Core Infrastructure

- **schemas.py** - Pydantic models for structured skill extraction
  - `Requirement` model with types: EnvVar, Tool, Hardware, API, Knowledge
  - `ExecutionPayload` model for code execution (executor, code, timeout)
  - `ExtractedSkill` model with Knowledge Architecture fields (nature, genus, differentia)
  - `StateTransition` model for state machine definitions

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
  - State transition extraction instructions

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
  - Predefined states: SystemAuthenticated, PermissionDenied, etc.

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
    - `init-core` - Initialize core ontology with predefined states
    - `compile [SKILL_NAME]` - Compile skills to ontology
    - `query "<sparql>"` - Execute SPARQL queries
    - `list-skills` - List all skills in ontology
    - `security-audit` - Re-validate skills against security patterns
  - Options:
    - `-i, --input` - Input directory (default: `./skills/`)
    - `-o, --output` - Output file (default: `./ontoskills/skills.ttl`)
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

- 42 tests with 86% code coverage
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

- README.md with full usage instructions
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

### SHACL Validation Philosophy

- **Fail-closed**: Invalid skills are never written to disk
- **Constitutional**: Shapes define the "laws" skills must follow
- **RDFS-aware**: State validation uses TBox from core ontology
- **Clear messages**: Italian error messages for debugging

### Security Philosophy

- Fail-closed: Any error blocks content
- Defense-in-depth: Regex + LLM review
- Unicode normalization prevents bypass attempts
- Pattern matching for common attack vectors
