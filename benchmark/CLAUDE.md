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
```

### NOT available
- `gaia-benchmark/GAIA` — gated dataset on HuggingFace. Requires `huggingface-cli login` first. NOT authenticated currently.

### Binary prerequisites
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server, rebuild from `mcp/` if outdated
- Compiled TTLs at `~/.ontoskills/packages/` — 1058 TTL files (640 skills + sub-skills), 11 author packages

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
│   ├── ontoskills.py       # Single ontoskill MCP tool (find or load skill by name/query)
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
├── data/                   # Downloaded datasets
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

**Traditional agent**: Skill registry in system prompt + `read_skill` tool for on-demand loading.
Multi-turn: model reads skills, then generates code.

**OntoSkills agent**: Single `ontoskill(q, top_k)` MCP tool. Model discovers or loads skill
knowledge via tool calls during the conversation. Structured TTL knowledge (types, severity,
context) is returned in compact format (~52 token schema vs read_skill's ~62).

This tests OntoSkills' core advantage: **structured skill knowledge via MCP vs. raw SKILL.md**.

#### CLI flags

- `--no-skill-hints` — Omit skill names from prompts. Agents must discover skills on their own
  (tests discovery mechanism vs knowledge quality).

#### Production-realistic benchmark (4 runs)

| Run | Agent       | Hints | Tests            |
|-----|-------------|-------|------------------|
| 1   | Traditional | Yes   | Knowledge quality |
| 2   | MCP         | Yes   | Knowledge quality |
| 3   | Traditional | No    | Discovery         |
| 4   | MCP         | No    | Discovery         |

The MCP server uses a SkillsBench-only ontology root (`/tmp/skillsbench_ontology/`) containing
only the 218 SkillsBench TTLs (vs. 840 total). This reduces MCP startup from 10s to 1.8s and
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

OntoSkillsAgent supports `prefetch=True` mode (API-mode only):
1. Before the first API call, calls MCP `ontoskill` for each skill ID
2. Compacts the MCP response into lean markdown text
3. Injects into system prompt — model has knowledge from turn 1
4. Removes tool schemas when knowledge is pre-loaded (no tool calls needed)

In CLI mode (production-realistic), the agent uses tool calls directly — no prefetch.

## MCP response compaction

All MCP tool responses use compact format by default (88% token reduction). The single `ontoskill`
tool handles both exact skill lookup and semantic search:

- `ontoskill("geospatial-analysis")` → loads that skill's context (compact markdown)
- `ontoskill("how to parse PDF files")` → searches for matching skills

Compaction happens server-side in the Rust MCP server (`mcp/src/compact.rs`). The `content[0].text`
field contains compact markdown text. Full JSON is preserved in `structuredContent` (zero knowledge
loss).

Internal tools (search, get_skill_context, etc.) are kept in the handler for backward compatibility
with `prefetch_knowledge` but are NOT exposed in tool definitions.

## Traditional agent design

The TraditionalAgent works like Claude Code:
- System prompt contains a **skill registry** with all skill names + descriptions (~27K tokens)
- Model has a `read_skill` tool to load full SKILL.md content on demand
- Multi-turn loop: model reads relevant skills then answers
- Both GAIA and SWE-bench wrappers delegate `read_skill` to `agent._resolve_skill()`

## ClaudeCodeAgent

Uses the Claude Code CLI in `--print --bare --output-format json` mode for realistic evaluation.

Two modes:
- `traditional` — SKILL.md files in `.claude/skills/`, no MCP
- `ontoskills` — MCP config for ontomcp + ontomcp-driver SKILL.md in `.claude/skills/`

Key files: `benchmark/agents/claudecode.py`, `benchmark/agents/utils.py`

## Current benchmark results (2026-04-29, SkillsBench 25-task v2)

### SkillsBench (Claude Code CLI, seed=7, glm-5.1, 24 tasks, multi-turn)

**v2 results (with multi-turn feedback + BM25 node ranking + skill_scripts fix):**
- Traditional: 12/24 passed (50.0%), avg_reward=0.562
- OntoSkills MCP: 9/24 passed (37.5%), avg_reward=0.489
- OntoSkills cost: $10.38 vs Traditional $11.53 (-10%)
- OntoSkills tokens: 11% fewer input tokens

**v1→v2 improvement (same seed, same tasks):**
- Traditional: 10/24 (41.7%) → 12/24 (50.0%), avg_reward 0.482 → 0.562 (+17%)
- MCP: 6/24 (25.0%) → 9/24 (37.5%), avg_reward 0.359 → 0.489 (+36%)

**v2 interventions applied:**
1. `skill_scripts/` copied into Docker container (fixes ModuleNotFoundError)
2. BM25 node ranking in compact_context() (top-8 knowledge nodes)
3. Multi-turn execution feedback (3 attempts per task with Docker test results)

**Infrastructure note:** `flink-query` always fails (Java container, no python3). 1 task excluded.

**Honest assessment:** Traditional leads on pass rate (+12.5pp). MCP leads on token efficiency.
Multi-turn feedback helped both modes, but benefited MCP more in relative terms.
The gap narrowed from +16.7pp to +12.5pp. Future improvements: test-first prompting,
task.toml timeouts, Docker pre-build.

### GAIA
_Results pending — run with Claude Code mode._

### SWE-bench
_Results pending — run with Claude Code mode._

### Compiler bug (unrelated to benchmark)
10 skills across 10 tasks failed to compile to TTL. Root cause: `ontocore compile`
with `-o` flag resolves `state_dir` incorrectly, creating `/state` instead of
relative path. The 10 missing skills are:
civ6lib, map-optimization-strategy, sqlite-map-parser, pymatgen, lean4-memories,
gemini-video-understanding, senior-data-scientist, gmail-skill, threejs,
data-reconciliation.

## Chart data output

All benchmark runs produce `chart_data.json` alongside `results.json` and `score.json`. This file contains per-task metrics in a format suitable for Chart.js/D3 visualization on the OntoSkills website.

