# Changelog

All notable changes to OntoCore (Python package) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.9.2] - 2026-03-26

### Changed

- **OWL Semantic Fixes** — Breaking changes to ontology properties for correct OWL reasoning:
  - `oc:contentHash` on files → `oc:fileHash` (domain: ReferenceFile, ExecutableScript via owl:unionOf)
  - `oc:executor` on scripts → `oc:scriptExecutor` (domain: ExecutableScript)
  - `oc:executionIntent` → `oc:scriptIntent`
  - `oc:commandTemplate` → `oc:scriptCommand`
  - `oc:producesOutput` → `oc:scriptOutput`
  - `oc:hasRequirement` on scripts → `oc:scriptHasRequirement`
  - `oc:description` on workflows → `dcterms:description`
  - `oc:dependsOn` on steps with Literal → `oc:stepDependsOn` (ObjectProperty)
  - `oc:relativePath` → `oc:filePath`
  - `oc:mimeType` → `oc:fileMimeType`
- **SYSTEM_PROMPT** — Added extraction instructions for reference files, executable scripts, workflows, and examples

### Added

- **Phase 1 Loader** (`loader.py`) — Python-only preprocessing before LLM extraction:
  - `parse_frontmatter()` — YAML parsing with Anthropic-compatible validation
  - `scan_skill_directory()` — Directory structure enumeration with file hashes
- **New Pydantic models** — `Frontmatter`, `FileInfo`, `DirectoryScan`, `ReferenceFile`, `ExecutableScript`, `Example`, `Workflow`, `WorkflowStep`, `CompiledSkill`
- **Blank node serialization** — Reference files, executable scripts, workflows, examples serialized as RDF blank nodes
- **Progressive disclosure support** — File metadata (hash, size, MIME type) for lazy loading

### Fixed

- **Reserved words validation** — Now blocks OntoSkills system words (ontoskills, marea, mareasw, core, system, index) in any segment of skill name (not just prefix/suffix)
- **Missing RDFS.domain** — Added domain declaration for `oc:requirementType` property
- **Duplicate imports** — Removed redundant import statements in core_ontology.py
- **BNode uniqueness** — Example blank nodes now use index-based identifiers to avoid collisions
- **CLI module execution** — Added `__main__.py` to enable `python -m compiler.cli`
- **Workflow cycle detection** — Linter now correctly detects cycles in `oc:stepDependsOn`
- **Parent skill ID** — CLI compile uses frontmatter-based skill ID for parent relationships

### Security

- **Path traversal protection** — Rejects `..` in file paths, backslashes, and absolute paths
- **Symlink protection** — Rejects symlinked skill directories to prevent filesystem escape
- **Backslash pruning** — Directories containing `\` are pruned during directory scan

### Performance

- **Directory scanning** — Switched from `rglob` to `os.walk` with early pruning of excluded directories
- **Deterministic hashing** — Files sorted before directory hash computation for reproducibility

### Tests

- 3 new tests for workflow cycle detection
- 32 new tests for loader module (55 total tests now passing)

## [0.9.1] - 2026-03-23

### Changed

- **CLI refactoring** — Split monolithic `cli.py` into modular `cli/` package with separate modules per command group:
  - `cli/__init__.py` — Entry point and command registration
  - `cli/compile.py` — Compile command with sub-skills support
  - `cli/query.py` — SPARQL query command
  - `cli/registry.py` — Registry and package management commands
  - `cli/audit.py` — Security audit and diff commands
  - `cli/export.py` — Embeddings export command
- **Registry refactoring** — Split monolithic `registry.py` into modular `registry/` package:
  - `registry/__init__.py` — Public API exports
  - `registry/compile.py` — Source tree compilation helpers
  - `registry/index.py` — Registry index rebuilding
  - `registry/install.py` — Package installation from directories/registries
  - `registry/models.py` — Pydantic models for manifests and state
  - `registry/paths.py` — Registry path utilities
  - `registry/state.py` — Registry state management
- **README update** — Improved positioning and tagline emphasizing deterministic skills vs probabilistic alternatives
- **Command name** — CLI now uses `ontocore` command (was `ontoskills`)

### Added

- **Chinese documentation** — Added `README_zh.md` and `PHILOSOPHY_zh.md` with language switcher links

### Fixed

- **Test suite** — Fixed mock patching issues after CLI refactoring, all 22 tests pass

## [0.9.0] - 2026-03-22

### Added

- **Qualified IDs** — Skills now use slash-separated package IDs (`owner/repo/skill`) instead of dot-separated
- **Sub-skills compilation** — Auxiliary `*.md` files are compiled to `*.ttl` modules with deterministic `extends` injection
- **Orphan sub-skill validation** — Compiler validates that sub-skills have valid parent skills
- **Dry-run behavior** — Compilation previews show what would be compiled without writing
- **CLI refactoring** — Split monolithic `cli.py` into modular `cli/` package with separate modules per command group

### Changed

- **Namespace migration** — All package IDs migrated from `marea/*` to `mareasw/*`
- **Registry artifacts** — Updated `docs/registry/examples` and all documentation to use `mareasw/` namespace
- **URI collision prevention** — Short IDs and qualified IDs are now handled separately to prevent URI collisions across packages

### Fixed

- **Package ID normalization** — `resolve_package_id()` now normalizes manifest names (handles spaces, uppercase, dots, npm scoped packages)
- **Defensive URI slugification** — `skill_uri_for_id()` now lowercases and replaces all non-alphanumeric characters for QName compatibility
- **Runtime base URI** — `collect_skill_records_from_file()` in MCP now uses the runtime `ONTOSKILLS_BASE_URI` instead of hard-coded `DEFAULT_BASE_URI`

## [0.7.3] - 2026-03-19

### Fixed

- Added `license` and `classifiers` metadata to `pyproject.toml` to fix missing Python and License badges on PyPI
- Copied `LICENSE` file into the package directory

## [0.7.2] - 2026-03-19

### Fixed

- Fixed missing PyPI project description by declaring `readme = "README.md"` in `pyproject.toml`

## [0.7.1] - 2026-03-19

### Added

- Added dedicated comprehensive `README.md` for the PyPI package

## [0.7.0] - 2026-03-19

### Added

- **URI namespace** — `ontoskills.marea.software` → `ontoskills.sh`
- **Core file** — `ontoskills-core.ttl` naming
- **Registry** — `OntoSkillRegistry` → `ontoskills-registry`
- **CLI** — Renamed to `ontoskills` (later `ontocore`)
- Bootstrap and publication flow for the official registry repository
- First remote demo package `mareasw/greeting/hello` to validate end-to-end registry installs

### Changed

- Changed the `ontoskills` product workflow so the official registry is built in by default
- Updated the user documentation to clarify the runtime flow: `search` → `install` → `enable`

## [0.6.0] - 2026-03-18

### Added

- Documentation restructure: README reduced, docs/ expanded
- `docs/architecture.md` — system design, OWL properties, security
- `docs/knowledge-extraction.md` — focus on knowledge nodes
- Repo-local `.env` loading for the Python compiler
- Global ontology registry management under `ontoskills/`
- Registry/package commands to the compiler CLI
- Support for importing remote ontology packages from registry indexes
- Direct raw source repository import from local paths or GitHub URLs
- Local `registry/` blueprint directory and package spec

### Changed

- Refactored the MCP public API from many granular tools to 4 consolidated tools
- Changed MCP runtime to prefer the enabled index manifest
- Extended MCP responses with package-aware metadata
- Changed MCP skill resolution to accept both short ids and qualified ids
- Changed short-id conflict resolution to use precedence `local > verified > trusted > community`
- Changed compiler relation serialization to use stable skill URI references
- Changed compiler enrichment to infer parent inheritance deterministically
- Changed the import layout so raw source repos land in `skills/vendor/`
- Changed the enable/disable system so local compiled skills are tracked

### Fixed

- Fixed pySHACL validation bug where RDFS inference caused Literal values in dependency relations
- Fixed SHACL `sh:class oc:State` constraint that rejected novel states
- Fixed skill dependency serialization to use Literal strings
- Fixed duplicate `skill_output_paths` entries
- Fixed compiler-side skill inheritance for nested skills
- Fixed imported/vendor ontology cleanup
- Fixed MCP ambiguity handling

## [0.5.0] - 2026-03-17

### Added

- **Local MCP Server** — Rust-based local MCP server under `mcp/`
- **MCP Tooling** — Implemented MCP tools for semantic skill discovery and planning
- **Planning Engine** — State-aware planning inside the Rust MCP catalog
- **Rust Test Coverage** — Unit tests for intent lookup, payload lookup, planning

### Changed

- Updated documentation to reflect that `mcp/` is now implemented
- MCP compatibility updates for Claude Code handshake

## [0.4.0] - 2026-03-17

### Breaking Changes

- **Output Filename Change** — `skill.ttl` → `ontoskill.ttl`

### Changed

- **Perfect Mirroring Architecture** — Compiler now acts as a Semantic Bundler
- **Orphan Cleanup Enhanced** — `clean_orphaned_files()` replaces `clean_orphaned_skills()`

### Added

- **`oc:executionPath`** — New DatatypeProperty for external asset paths
- **`owl:disjointWith`** — DeclarativeSkill and ExecutableSkill are now mutually exclusive
- **XOR constraint** — ExecutionPayload must have either `oc:code` OR `oc:executionPath`

### Removed

- `clean_orphaned_skills()` — Replaced by `clean_orphaned_files()`
- Legacy `skill.ttl` references

## [0.3.0] - 2026-03-17

### Changed

- **Architecture Refactoring** — Monolithic `loader.py` (855 lines) refactored into 3 modules:
  - `core_ontology.py` (~344 lines) — Namespace management and core TBox ontology
  - `serialization.py` (~168 lines) — Pydantic-to-RDF serialization with SHACL gatekeeper
  - `storage.py` (~484 lines) — File I/O, intelligent merging, orphan cleanup

### Added

- **`--force` flag** — Bypass hash-based caching to force recompilation
- **`clean_orphaned_skills()`** — Automatically removes `.ttl` files when source `SKILL.md` is deleted
- **Test coverage** — 150 tests pass

## [0.2.0] - 2026-03-16

### Added

- **SHACL Validation Gatekeeper** — Constitutional validation layer
- **`specs/ontoskills.shacl.ttl`** — Constitutional SHACL shapes
- **schemas.py** — Added computed `skill_type` property
- **loader.py** — Added skill subclasses and validation hooks
- **exceptions.py** — Added `OntologyValidationError`
- **Testing** — 91 tests

### Changed

- Existing tests updated to include required `generated_by` field for SHACL compliance

### Dependencies

- Added `pyshacl>=0.25.0` for SHACL validation

## [0.1.0] - 2026-03-16

### Added

- **schemas.py** — Pydantic models for structured skill extraction
- **exceptions.py** — Custom exception hierarchy with exit codes
- **extractor.py** — Deterministic ID and hash generation
- **transformer.py** — LLM tool-use extraction
- **security.py** — Defense-in-depth security checks
- **loader.py** — OWL 2 RDF/Turtle serialization
- **sparql.py** — Query execution against ontology
- **cli.py** — Complete Click-based CLI
- 42 tests with 86% code coverage
