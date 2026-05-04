# Changelog

All notable changes to ontomcp (Rust MCP Server) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-05-04

### Added

- **Unified `ontoskill` tool** — Replaces 4 separate tools (`search`, `get_skill_context`, `evaluate_execution_plan`, `query_epistemic_rules`) with a single `ontoskill(q, top_k)` tool. When `q` matches a known skill ID, returns full skill context; otherwise falls back to BM25 keyword search (or semantic when embeddings are enabled)
- **Knowledge node BM25 ranking** — `NodeBm25Engine` ranks knowledge nodes by query relevance with bottom-percentile cutoff (keeps top 80%, minimum 10 nodes). `NODE_BUDGET_CHARS` (12K chars) prevents overwhelming the agent
- **Section tree content** — New `SectionBm25Engine` ranks code examples and reference tables within `SECTION_BUDGET_CHARS` (3K chars). Content served alongside knowledge nodes in compact output
- **Intra-skill link rendering** — `KnowledgeNodeLink` struct with `correctAlternative` and `appliesToStep` properties, rendered as `→ Correct: "..."` and `→ Applies to: ...` in compact output
- **Backward-compatible old tool handlers** — Legacy `search`, `get_skill_context`, `evaluate_execution_plan`, `query_epistemic_rules` handlers still present for direct JSON-RPC calls

### Changed

- **Tool surface reduced from 5 to 1** — `prefetch_knowledge` kept as internal handler (backward compat), removed from `tool_definitions()`
- **Compact context** — `compact_context_with_query()` supports optional BM25 filtering for both knowledge nodes and section content
- **Version aligned** — OntoMCP 1.1.0 matches OntoCore 1.1.0

## [1.0.0] - 2026-04-28

### Added

- **Compact response format** — New `compact.rs` module (457 lines) producing token-efficient markdown-like text for all tool responses. 88% average token reduction: search 90%, get_skill_context 79%, evaluate_execution_plan 96%, query_epistemic_rules 79%. Full JSON preserved in `structuredContent` (zero knowledge loss)
- **`prefetch_knowledge` tool** — One-call knowledge retrieval combining search + get_skill_context. Accepts explicit `skill_ids` or `query` parameter. Returns compact text ready for the model, eliminating multi-turn tool discovery
- **`format` parameter on all tools** — Every tool accepts `format: "compact"` (default) or `format: "raw"` for verbose JSON. Enables debugging and backward compatibility

### Changed

- **Simplified `ontomcp-driver` skill** — Reduced from 113 to 32 lines (~950 token saving per turn). Compact responses are self-descriptive, making verbose per-tool documentation unnecessary
- **Sparse serialization** — `skip_serializing_if` annotations on catalog structs reduce JSON output for unavailable payloads and empty fields

## [0.11.0] - 2026-04-15

### Added

- **Per-skill `intents.json` scanning** — Embedding engine scans the entire ontology tree for per-skill `intents.json` files instead of requiring a centralized file
- **Backward-compatible centralized loading** — Still loads `system/embeddings/intents.json` if present, then merges per-skill files on top
- **BM25 keyword search engine** — In-memory BM25 index built from Catalog data (intents, aliases, nature) at startup. Always available, no additional files on disk
- **Hybrid search dispatch** — Semantic search is preferred when embeddings are available (ONNX). BM25 is used as fallback when embeddings are not installed or return no results
- **Search response `mode` field** — Responses include `"mode": "bm25"` or `"mode": "semantic"` to indicate which engine produced the results
- **`aliases` in SkillSummary** — `list_skills()` and `find_skills_by_intent()` now include skill aliases

### Changed

- **Per-skill embedding architecture** — `EmbeddingEngine::load()` now takes `ontology_root` as second argument for tree-wide scanning
- **Embedding initialization guard** — Checks for `model.onnx` instead of directory existence to avoid loading without model files
- **BM25 is the default search** — The `search` tool with `query` parameter now uses BM25 by default instead of requiring ONNX embeddings
- **Embeddings are optional** — `ort`, `tokenizers`, `ndarray` are behind `embeddings` feature flag in Cargo.toml. Default build has zero ML dependencies
- **`sentence-transformers` is optional** — Moved from mandatory to `[project.optional-dependencies] embeddings` in OntoCore's pyproject.toml
- **Compile without embeddings** — `ontocore compile` skips embedding generation when `sentence-transformers` is not installed, prints a warning instead of failing
- **Trust tier scoring** — BM25 results use the same quality multipliers as the embedding engine (official: 1.2, local/verified: 1.0, community: 0.8)

### Removed

- **Mandatory ONNX Runtime** — No longer required for default installation. Only needed when `--features embeddings` is enabled

## [0.10.0] - 2026-04-14

### Added

- **Unified `search` tool** — Smart dispatch: `query` → semantic intent search, `alias` → alias resolution, otherwise → structured skill search (consolidated from 6 tools to 4)
- **Hybrid scoring** — Semantic search results ranked by cosine similarity × trust-tier quality multiplier (official: 1.2, local/verified: 1.0, community: 0.8)
- **Query safety truncation** — Defensive 512-byte cap on search queries
- **ONNX embedding engine** — Full pipeline: `model.onnx` + `tokenizer.json` + `intents.json` with mean pooling, L2 normalization, and adaptive cutoff
- **E2E test** — `mcp/tests/e2e_search.sh` validates compile → merge → ONNX export → JSON-RPC search

### Changed

- **Trust tiers from catalog** — `trust_tier_map()` wired into embedding engine at startup for hybrid scoring
- **Version aligned** — OntoMCP 0.11.0 matches OntoCore 0.11.0
- **`dependsOnSkill` in JS** — `extractSkillInfo()` regex updated to match `oc:dependsOnSkill`
- **JS install fix** — `installSkill()` now correctly parses `author/package/skill` refs (was splitting at first `/`)
- **vendor→author rename** — Catalog path resolution uses `ontologies/author/` (was `ontologies/vendor/`). E2E test updated. Hybrid scoring table uses "author skills" terminology

## [0.9.1] - 2026-03-24

### Added

- **Legacy path fallback** — MCP falls back to `~/.ontoskills/ontoskills/` if `~/.ontoskills/ontologies/` not found, with deprecation warning
- **Fifth tool** — `search_intents` for intent-based discovery (optional, requires embeddings)

### Changed

- **Package rename** — `ontoskills-mcp` → `ontomcp`
- **Default ontology root** — `~/.ontoskills/ontoskills/` → `~/.ontoskills/ontologies/`
- **Store terminology** — Docs aligned with "store" (was "registry")
- **Auto-enable behavior** — Skills enabled by default; `enable` only for re-enabling

### Fixed

- Path placeholder consistency in docs (`/path/to/ontology-root`)

## [0.9.0] - 2026-03-22

### Added

- **Adaptive cutoff** — Semantic search now uses an adaptive cutoff algorithm to filter low-quality results
  - Detects score gaps to find natural relevance boundaries
  - Falls back to threshold-based filtering when no gap is detected
  - Improved search result quality for semantic queries

### Changed

- **Runtime base URI** — `collect_skill_records_from_file()` now uses the runtime `ONTOSKILLS_BASE_URI` instead of hard-coded `DEFAULT_BASE_URI`
- **Version alignment** — Aligned with core package versioning (both at 0.9.0)

## [0.8.1] - 2026-03-20

### Fixed

- Upgraded GitHub Actions workflow versions for Node 24 compatibility
- Unified publish workflow triggers

## [0.8.0] - 2026-03-20

### Added

- Cross-platform binary releases via GitHub Actions
  - Linux x64 and ARM64
  - macOS Intel (x64) and Apple Silicon (ARM64)
- `ontoskills-core.ttl` bundled with release artifacts

### Changed

- Renamed CLI from `ontoclaw` to `ontoskills`
- Aligned ontology namespace identifiers to `ontoskills.sh`
- Refreshed client guides and documentation

## [0.5.0] - 2026-03-17

### Added

#### MCP Server

- Rust-based local MCP server under `mcp/`
  - Speaks MCP over `stdio`
  - Auto-discovers `ontoskills/` from current directory and parents
  - `--ontology-root` flag for custom ontology paths

#### MCP Tooling

- `list_skills` — List all skills in loaded ontologies
- `find_skills_by_intent` — Find skills matching an intent string
- `get_skill` — Get full skill details by ID
- `get_skill_requirements` — Get skill requirements
- `get_skill_transitions` — Get state transitions for a skill
- `get_skill_dependencies` — Get skill dependencies
- `get_skill_conflicts` — Get conflicting skills
- `find_skills_yielding_state` — Find skills that produce a state
- `find_skills_requiring_state` — Find skills that require a state
- `check_skill_applicability` — Check if skill applies given current states
- `plan_from_intent` — Generate execution plan from intent
- `get_skill_payload` — Get executable payload for a skill

#### Planning Engine

- State-aware planning inside MCP catalog
  - Checks `requiresState` against caller-provided current states
  - Finds preparatory skills through `yieldsState`
  - Ranks candidate plans by unresolved states and step count
  - Prefers direct skills over setup-heavy alternatives

### Changed

- MCP compatibility updates for Claude Code handshake
  - Protocol version `2025-11-25` support
  - Line-delimited JSON on stdio
  - Empty resources/prompts endpoints for client compatibility

### Testing

- Rust unit tests for intent lookup, payload lookup, planning, and planner ranking
