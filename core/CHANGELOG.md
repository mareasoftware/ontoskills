# Changelog

All notable changes to OntoCore (Python package) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-05-04

### Added

- **Intra-skill link inference** — New `linker.py` module adds three types of links via post-serialization inference:
  - `derivedFromSection` — KnowledgeNode → Section (token overlap matching)
  - `correctAlternative` — AntiPattern → Section/CodeExample (keyword matching)
  - `appliesToStep` — KnowledgeNode → WorkflowStep (numeric reference matching)
- **Named URIs instead of blank nodes** — All content nodes (sections, paragraphs, code blocks, tables, etc.) promoted from `BNode` to `URIRef` with deterministic SHA-256 hashes, enabling cross-referencing from the linker and SPARQL queries

### Changed

- **`--skip-security` bypasses entire pipeline** — Previously only skipped LLM review; now skips both pattern matching and LLM review
- **Serialization** — `make_bnode()` → `make_uri()` with prefix map for compact, deterministic named URIs

### Fixed

- **security.py** — `--skip-security` now correctly skips all security checks instead of only the LLM review stage

## [1.0.0] - 2026-04-28

### Changed

- **Ontology format bumped to 1.0** — Stable format with compact MCP responses, prefetch_knowledge tool, lazy content extraction, and relaxed SHACL validation
- **Version aligned** — OntoCore 1.0.0 matches OntoMCP 1.0.0

## [0.11.0] - 2026-04-20

### Added

- **Structural content extraction** — `content_parser.py` using `markdown-it-py` extracts code blocks, tables, flowcharts, ordered procedures, and templates from SKILL.md via deterministic parsing (no LLM)
- **4 new OWL classes** — `oc:CodeExample`, `oc:Table`, `oc:Flowchart`, `oc:Template` with full TBox axioms in core ontology
- **`oc:stepOrder`** — Integer property on `oc:WorkflowStep` for linear procedure ordering
- **Content block annotation** — LLM Phase 2 annotates pre-extracted blocks with purpose/context (no rewriting)
- **`ContentExtraction` models** — `CodeBlock`, `MarkdownTable`, `FlowchartBlock`, `TemplateBlock`, `OrderedProcedure`, `ProcedureStep` in schemas.py
- **Annotation models** — `CodeAnnotation`, `TableAnnotation`, `FlowchartAnnotation`, `TemplateAnnotation` on `ExtractedSkill`
- **SHACL shapes** for CodeExample, Table, Flowchart, Template validation
- **`markdown-it-py` + `mdit-py-plugins`** — New Python dependencies for CommonMark-compliant markdown parsing
- **`ontomcp-driver` skill** — Plain SKILL.md teaching agents how to use the OntoSkills MCP server
- **`--with-embeddings` install flag** — `ontoskills install <ref> --with-embeddings` optionally downloads per-skill embedding files from remote registries for semantic search
- **Per-skill embedding generation** — Every compiled skill produces `intents.json` with 384-dim L2-normalized embeddings alongside `ontoskill.ttl`. Requires `ontocore[embeddings]` extra; skipped with a warning when not installed
- **`oc:dependsOnSkill`** — New ObjectProperty replacing `oc:dependsOn` for unambiguous skill-to-skill dependencies (domain/range `oc:Skill`)
- **`oc:enablesSkill`** — Inverse ObjectProperty of `dependsOnSkill` (`owl:inverseOf`) for bidirectional skill relationship traversal
- **9 optional metadata properties** — `category`, `version`, `license`, `author`, `package_name`, `is_user_invocable`, `argument_hint`, `allowed_tools`, `aliases` in ontology, SHACL shapes, Pydantic models, and serialization
- **Multi-level install resolution** — `ontoskills install` supports author-level, package-level, and skill-level references via `resolve_install_ref()`
- **Parallel compile workers** — Configurable retry mechanism and parallel LLM extraction workers
- **Direct content injection** — Skip tool-use discovery phase, inject content directly to LLM
- **`ontocore lint` CLI command** — Run structural lint checks on compiled TTL files with Rich table output, `--errors-only` and `--json` flags
- **Content Extraction** — Every markdown element (sections, paragraphs, bullet lists, blockquotes) becomes a typed RDF node in a tree structure
- **`oc:Section`** — Document sections with title, level, order, nested subsections, and typed content
- **`oc:Paragraph`** — Free-form text preserving bold, links, inline code
- **`oc:BulletList` / `oc:BulletItem`** — Unordered list extraction with item ordering
- **`oc:BlockQuote`** — Blockquote extraction with optional attribution detection
- **Content tree serialization** — Section tree walks produce RDF triples with `oc:hasSection`, `oc:hasSubsection`, `oc:hasContent`
- **SHACL shapes** for Section, Paragraph, BulletList, BulletItem, BlockQuote validation
- **≥80% markdown coverage** — up from ~50% with structural blocks alone
- **Skeleton & Hydration** — LLM-assisted document tree building with deterministic byte-perfect content extraction via pointer-based architecture (Phase 1a flat extraction → Phase 1b LLM skeleton → Phase 1c hydration)
- **`oc:HTMLBlock`** — Raw HTML blocks from markdown extracted as typed RDF nodes
- **`oc:FrontmatterBlock`** — YAML frontmatter extracted as typed nodes with parsed properties
- **`FlatBlock` / `DocumentSkeleton`** — Pointer-based models: Phase 1a extracts flat blocks with unique IDs, Phase 1b LLM arranges IDs into tree, Phase 1c Python hydrates with real content
- **Nested list item extraction** — Code blocks, paragraphs, sub-lists inside bullet items and procedure steps via recursive token walking
- **`oc:hasChild`** — Object property for nested content blocks within list items
- **`BulletItem.children` / `ProcedureStep.children`** — Pydantic models support nested content blocks
- **100% line-level coverage** across 30 benchmark skills (14 superpowers + 16 Anthropic), up from 54.7% average in v1

### Changed

- **Lazy content extraction** — `scan_skill_directory()` no longer calls LLM during Phase 1; structural content extraction is deferred to Phase 2 compilation, reducing scan time from minutes to milliseconds per skill
- **SHACL validation relaxed** — `oc:hasRationale` and `oc:appliesToContext` on `KnowledgeNode` changed from required (`sh:minCount 1`) to optional warnings (`sh:severity sh:Warning`); `oc:dependsOnSkill` cross-reference validation also relaxed to warning (target skill may not yet be compiled)
- **Cross-reference URI normalization** — `depends_on`, `extends`, and `contradicts` skill references now resolve to qualified URIs via `skill_id_map`, ensuring consistent cross-package linking
- **`workflows` field moved** from `CompiledSkill` to `ExtractedSkill` — fixes bug where LLM prompt asked for workflows but tool schema didn't include them
- **Phase 1 pipeline** now includes structural content extraction via `content_parser.py`
- **Serialization** supports content blocks with annotation merge-by-index
- **Circular dependency guard** — `enrich_extracted_skill()` removes self-referencing depends_on
- **Embeddings fully optional end-to-end** — Compile time (`ontocore[embeddings]`), install time (`--with-embeddings`), and MCP runtime (BM25 fallback) all treat embeddings as optional
- **`generatedBy` made optional** — No longer required by SHACL validation; auto-filled when present
- **Global vendor→author rename** — Directory paths, variables, functions, types, ontology property, and all documentation
- **`oc:dependsOn` deprecated** — Marked with `owl:deprecated true`; linter, differ, and serialization now use `oc:dependsOnSkill`

### Fixed

- **Cross-reference URIs** — `dependsOnSkill` in TTL now uses qualified skill URIs (e.g., `oc:skill_anthropics_claude_office_skills_xlsx_manipulation`) instead of bare IDs, resolving correctly at MCP runtime
- **Compilation performance** — 408 skills compile in ~3h instead of never completing (Phase 1 LLM calls eliminated)
- **Knowledge node SHACL failures** — 82% of skills no longer rejected by validation due to optional `hasRationale`/`appliesToContext` fields
- **Workflows dropped by Pydantic** — `ExtractedSkill.model_json_schema()` now includes `workflows` field
- **Self-referencing dependencies** — `depends_on` filtered to exclude the skill's own ID
- **Compile error collector** — Cleared per invocation to prevent batch contamination across compilations
- **Skill registry context** — Preserved during sub-skill extraction to maintain LLM context
- **Differ backward compatibility** — Migration suggestion SPARQL queries use UNION to cover both `dependsOnSkill` and deprecated `dependsOn`
- **Linter property mismatch** — Circular dependency and workflow cycle detection now correctly query `oc:dependsOnSkill` instead of old `oc:dependsOn`

## [0.10.0] - 2026-03-27

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
- **Parent inheritance robustness** — Skip parents not in skill_parent_map to avoid extends references to non-existent modules
- **Name validation** — Tightened regex to disallow leading/trailing and repeated hyphens
- **Workflow dependency warning** — Log warning when step dependency references non-existent step_id
- **Reference docs handling** — Exclude `reference/**` from Rule B sub-skill processing (treat as assets)
- **File read error handling** — Wrap `read_text()` errors in `LoaderError` for graceful per-skill failure handling

### Removed

- **`ExecutableScript`** — Unused schema class, ontology class (`oc:ExecutableScript`), and all associated properties (`oc:hasExecutableScript`, `oc:scriptExecutor`, `oc:scriptIntent`, `oc:scriptCommand`, `oc:scriptOutput`, `oc:scriptHasRequirement`) removed. These were never consumed by the MCP runtime; `ExecutionPayload` remains the sole mechanism for executable skills

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
- Changed short-id conflict resolution to use precedence `official > local > verified > community`
- Changed compiler relation serialization to use stable skill URI references
- Changed compiler enrichment to infer parent inheritance deterministically
- Changed the import layout so raw source repos land in `skills/author/`
- Changed the enable/disable system so local compiled skills are tracked

### Fixed

- Fixed pySHACL validation bug where RDFS inference caused Literal values in dependency relations
- Fixed SHACL `sh:class oc:State` constraint that rejected novel states
- Fixed skill dependency serialization to use Literal strings
- Fixed duplicate `skill_output_paths` entries
- Fixed compiler-side skill inheritance for nested skills
- Fixed imported/author ontology cleanup
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
