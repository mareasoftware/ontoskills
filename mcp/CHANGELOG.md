# Changelog

All notable changes to ontoskills-mcp (Rust MCP Server) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
