# OntoSkills Benchmark

## Prerequisites

### Environment variables
- `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` — required for both agents
- `ANTHROPIC_BASE_URL` — set to `https://api.z.ai/api/anthropic` (proxy)
- Model ID: `glm-5.1` (via proxy, NOT a standard Claude model)

### Python dependencies
```
datasets    — HuggingFace dataset loading (installed)
anthropic   — API client (installed)
rdflib      — TTL parsing for content coverage (installed)
requests    — HTTP client for API calls (installed)
pdfplumber  — PDF text extraction (installed)
python-docx — Word document creation (installed)
python-pptx — PowerPoint generation (installed)
pandas      — Data manipulation (installed)
youtube-transcript-api — YouTube transcript fetching (installed)
toml        — TOML config parsing (installed)
```

### NOT available
- `gaia-benchmark/GAIA` — gated dataset on HuggingFace. Requires `huggingface-cli login` first. NOT authenticated currently.

### Binary prerequisites
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server, rebuild from `mcp/` if outdated
- Compiled TTLs at `~/.ontoskills/packages/` — 840 files (408 skills + sub-skills), 11 author packages

## Architecture

```
benchmark/
├── run.py                  # Main orchestrator (CLI entry point)
├── content_coverage.py     # Parser coverage + knowledge yield (no API calls)
├── config.py               # Model pricing, benchmark definitions
├── agents/
│   ├── base.py             # BaseAgent with Anthropic API, run-loop, retry
│   ├── claudecode.py       # ClaudeCodeAgent: CLI-based agent (--print --bare mode)
│   ├── traditional.py      # Skill registry + read_skill tool (like Claude Code)
│   ├── ontoskills.py       # 4 MCP tools (search, get_skill_context, etc.)
│   └── utils.py            # Shared utilities (extract_python_code)
├── wrappers/
│   ├── gaia.py             # GAIA: Q&A with file attachments
│   ├── perpackage.py       # Per-package: run selected packages only
│   ├── skillsbench.py      # SkillsBench: Docker-based deterministic eval (podman + pytest)
│   ├── swebench.py         # SWE-bench: repo checkout + diff patch generation
│   └── tau2bench.py        # tau2-bench: agent benchmarking wrapper
├── reporting/
│   ├── metrics.py          # compute_comparison()
│   ├── comparison.py       # generate_comparison_report()
│   └── chart_data.py       # chart-ready JSON generation (Chart.js/D3)
├── mcp_client/
│   └── client.py           # JSON-RPC MCP client for ontomcp subprocess
├── tests/                  # Unit tests for benchmark framework
├── data/                   # Downloaded datasets (currently empty)
└── results/                # Benchmark output (JSON + comparison.md)
```

## Running benchmarks

### Content coverage (instant, no API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/content_coverage.py --verbose --ttl-dir ~/.ontoskills/packages --json benchmark/results/content_coverage.json
```

### SWE-bench (requires API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark swebench --mode both --max-tasks 25 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results -v
```

### GAIA (requires HF auth — currently broken)
```bash
huggingface-cli login  # must do this first
python benchmark/run.py --benchmark gaia --mode both --model glm-5.1 ...
```

### SkillsBench (Docker-based deterministic evaluation)
```bash
# Prerequisites: clone the SkillsBench repo and have podman/docker available
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark skillsbench --mode both --max-tasks 10 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v
```

SkillsBench uses deterministic Docker evaluation:
1. Agent generates a Python solution script
2. Script is executed inside the task's Docker container (via podman)
3. Task's pytest test suite verifies the output files
4. Fractional scoring from CTRF report (passed/total tests) with binary reward.txt fallback

6 tasks are skipped: 5 exotic base images (bugswarm, suricata, oss-fuzz, erlang) + 1 Podman/BuildKit incompatibility (organize-messy-files).

#### Agent design for SkillsBench

**Traditional agent**: SKILL.md content included directly in the user prompt (raw markdown).
No tools — the agent sees all skill documentation in one shot and generates code.

**OntoSkills agent**: Skills loaded via MCP prefetch from compiled TTLs. The user prompt
contains only the task instruction + Dockerfile metadata (89% smaller). Skill knowledge
(structured nodes with types, severity, context) is injected into the system prompt via
`get_skill_context`. No tools needed — single-turn code generation.

This tests OntoSkills' core advantage: **structured skill knowledge via MCP vs. raw SKILL.md**.

The MCP server uses a SkillsBench-only ontology root (`/tmp/skillsbench_ontology/`) containing
only the 218 SkillsBench TTLs (vs. 626 total). This reduces MCP startup from 10s to 1.8s and
query time from 3.8s to 0.27s per skill.

## Known issues

### SWE-bench wrapper: custom run-loop required
The SWE-bench wrapper patches `agent.run_turn` to intercept file_read/file_edit. It does NOT use `BaseAgent.run()` — it has a custom loop because `BaseAgent.run()` double-appends messages when `run_turn` also appends. See `swebench.py:run_task()` for the custom loop.

### Content coverage: core.ttl must be loaded
The knowledge yield Level 2 SPARQL uses `rdfs:subClassOf*` property paths to resolve leaf types (e.g., `oc:AntiPattern`) to top-level dimensions (e.g., `oc:NormativeRule`). This requires `core.ttl` loaded in the graph. The file is at `ontoskills/core.ttl` in the project root, NOT in `~/.ontoskills/packages/`.

## Test verification

Run before any changes:
```bash
cd /home/marcello/Documenti/onto/ontoskills/core
python -m pytest tests/ -q
```

Run benchmark tests:
```bash
cd /home/marcello/Documenti/onto/ontoskills
python -m pytest benchmark/tests/ -q
```

Run smoke test after compilation:
```bash
python benchmark/smoketest.py
```

## Prefetch optimization

OntoSkillsAgent supports `prefetch=True` mode:
1. Before the first API call, calls MCP `search` + `get_skill_context`
2. Compacts the verbose MCP JSON into lean markdown-like text
3. Injects into system prompt — model has knowledge from turn 1
4. Removes tool schemas when knowledge is pre-loaded (no tool calls needed)

Result: OntoSkills at **0.86x tokens** vs Traditional (input is 0.40x), with better quality (4.6/5 vs 3.7/5).

## MCP response compaction

All MCP tool responses are compacted in real-time to minimize token usage:

- **search**: 90% reduction — keeps only skill_id, intents, trust_tier
- **get_skill_context**: 79% reduction — formatted as markdown with knowledge nodes sorted by priority
- **evaluate_execution_plan**: 96% reduction — plan steps + warnings only
- **query_epistemic_rules**: 79% reduction — directive content with context and severity

Compaction is applied in `OntoSkillsAgent.run_turn()` via `_compact_tool_result()` which dispatches
to tool-specific compactors (`_compact_search`, `_compact_epistemic_rules`, `_compact_plan`).

Additionally, the ontomcp server (Rust) strips null fields, empty Vecs, URIs, and unavailable
payloads from JSON responses via `#[serde(skip_serializing_if)]` annotations in `catalog.rs`.

## Traditional agent design

The TraditionalAgent works like Claude Code:
- System prompt contains a **skill registry** with all 425 skill names + descriptions (~28K tokens)
- Model has a `read_skill` tool to load full SKILL.md content on demand
- Multi-turn loop: model reads relevant skills then answers
- Both GAIA and SWE-bench wrappers delegate `read_skill` to `agent._resolve_skill()`

## ClaudeCodeAgent

Uses the Claude Code CLI in `--print --bare --output-format json` mode for realistic evaluation.

Two modes:
- `traditional` — SKILL.md files in `.claude/skills/`, no MCP
- `ontoskills` — MCP config for ontomcp + ontomcp-driver SKILL.md in `.claude/skills/`

Key files: `benchmark/agents/claudecode.py`, `benchmark/agents/utils.py`

## Current benchmark results (2026-04-28, SkillsBench 10-task)

### SkillsBench (Claude Code CLI, seed=7, glm-5.1, 10 tasks)

#### Traditional (skills in .claude/skills/) — 4/10 (40%), avg_reward=0.40
| Task | Result |
|------|--------|
| reserves-at-risk-calc (financial) | FAIL (0/5 tests) |
| offer-letter-generator (docx) | PASS (4/4 tests) |
| lab-unit-harmonization (healthcare) | FAIL (0/8 tests) |
| travel-planning | PASS (11/11 tests) |
| paper-anonymizer (PDF) | FAIL (0/6 tests) |
| flood-risk-analysis (data) | FAIL (0/2 tests) |
| 3d-scan-calc (engineering) | PASS (2/2 tests) |
| exceltable-in-ppt (Office) | PASS (8/8 tests) |
| fix-visual-stability (web) | FAIL (0/2 tests) |
| gh-repo-analytics (devops) | FAIL (0/8 tests) |

#### OntoSkills MCP (ontomcp-driver skill + MCP tools) — 5/10 (50%), avg_reward=0.52
| Task | Result |
|------|--------|
| reserves-at-risk-calc (financial) | PARTIAL (1/5 tests) |
| offer-letter-generator (docx) | PASS (4/4 tests) |
| lab-unit-harmonization (healthcare) | FAIL (0/8 tests) |
| travel-planning | PASS (11/11 tests) |
| paper-anonymizer (PDF) | PASS (6/6 tests) |
| flood-risk-analysis (data) | FAIL (0/2 tests) |
| 3d-scan-calc (engineering) | PASS (2/2 tests) |
| exceltable-in-ppt (Office) | PASS (8/8 tests) |
| fix-visual-stability (web) | FAIL (0/2 tests) |
| gh-repo-analytics (devops) | FAIL (0/8 tests) |

**Delta: +25% pass rate (50% vs 40%), +30% avg reward (0.52 vs 0.40)**

Key MCP wins: paper-anonymizer 0→6/6, reserves-at-risk-calc 0→1/5.
Both failed: lab-unit-harmonization (timeout), flood-risk-analysis (HTTP 404),
fix-visual-stability (timeout), gh-repo-analytics (gh not authenticated).

### GAIA
_Results pending — run with Claude Code mode._

### SWE-bench
_Results pending — run with Claude Code mode._

### Compiler bug (unrelated to benchmark)
11 skills across 9 tasks failed to compile to TTL. Root cause: `ontocore compile`
with `-o` flag resolves `state_dir` incorrectly, creating `/state` instead of
relative path. The 11 missing skills are:
civ6lib, map-optimization-strategy, sqlite-map-parser, pymatgen, lean4-memories,
gemini-video-understanding, senior-data-scientist, gmail-skill, threejs,
data-reconciliation.

## Chart data output

All benchmark runs produce `chart_data.json` alongside `results.json` and `score.json`. This file contains per-task metrics in a format suitable for Chart.js/D3 visualization on the OntoSkills website.

