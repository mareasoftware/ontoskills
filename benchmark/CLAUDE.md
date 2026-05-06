# OntoSkills Benchmark

## Prerequisites

### Environment variables
- `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` — required for both agents
- `ANTHROPIC_BASE_URL` — set to `https://api.z.ai/api/anthropic` (proxy)
- Model ID: `glm-5.1` (via proxy, NOT a standard Claude model)

### Python dependencies
```
benchflow   — BenchFlow SDK (container lifecycle, retry, scoring)
harbor      — Harbor (Docker environment management, verifier)
anthropic   — API client
rdflib      — TTL parsing for content coverage
datasets    — HuggingFace dataset loading
```

### NOT available
- `gaia-benchmark/GAIA` — gated dataset on HuggingFace. Requires `huggingface-cli login` first.

### Binary prerequisites
- `claude` binary at `~/.local/share/claude/versions/2.1.128` — standalone Claude Code CLI
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server
- Compiled TTLs at `~/.ontoskills/packages/` — TTL files compiled from skills
- SkillsBench repo at `~/.ontoskills/skillsbench` — `git clone --depth 1 https://github.com/benchflow-ai/skillsbench ~/.ontoskills/skillsbench`
- `docker` (or `podman` with docker alias) — container runtime

## Architecture

```
benchmark/
├── run.py                  # Main orchestrator (CLI entry point)
├── state.py                # BenchmarkState — resume, incremental save
├── content_coverage.py     # Parser coverage + knowledge yield (no API calls)
├── config.py               # Model pricing, benchmark definitions
├── agents/
│   ├── base.py             # BaseAgent with Anthropic API, run-loop, retry
│   └── utils.py            # Shared utilities (extract_python_code)
├── wrappers/
│   ├── gaia.py             # GAIA: Q&A with file attachments
│   ├── perpackage.py       # Per-package: run selected packages only
│   ├── skillsbench.py      # SkillsBench: ACP + ACP-MCP via BenchFlow Trial
│   ├── swebench.py         # SWE-bench: repo checkout + diff patch generation
│   └── tau2bench.py        # tau2-bench: agent benchmarking wrapper
├── reporting/
│   ├── metrics.py          # compute_comparison()
│   ├── comparison.py       # generate_comparison_report()
│   └── chart_data.py       # chart-ready JSON generation
├── mcp_client/
│   └── client.py           # JSON-RPC MCP client for ontomcp subprocess
├── tests/                  # Unit tests for benchmark framework
├── data/                   # Downloaded datasets
└── results/                # Benchmark output (JSON + comparison.md)
```

## Running benchmarks

### SkillsBench (BenchFlow-aligned Docker evaluation)

The agent runs inside the container via the native Claude Code CLI (not ACP).
BenchFlow Trial handles Docker lifecycle; the Claude binary is uploaded and
run via ``env.exec()``. The only difference between modes is how skills are
delivered.

```bash
# Prerequisites: clone the SkillsBench repo
git clone --depth 1 https://github.com/benchflow-ai/skillsbench ~/.ontoskills/skillsbench

# Traditional mode — SKILL.md files in ~/.claude/skills/
python benchmark/run.py --mode acp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# MCP mode — ontomcp inside container
python benchmark/run.py --mode acp-mcp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# Baseline — no skills
python benchmark/run.py --mode baseline --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# Sequential wrapper (all 3 modes)
bash benchmark/run_sequential.sh
```

### SkillsBench methodology

All modes use BenchFlow Trial for the Docker lifecycle, aligned with
[BenchFlow](https://github.com/benchflow-ai/benchflow) /
[SkillsBench](https://github.com/benchflow-ai/skillsbench). The agent is
the native Claude Code CLI binary (not ACP), uploaded into each container:

1. **Container lifecycle**: BenchFlow `Trial` builds the Docker image and
   starts the container.
2. **Agent binary upload**: The standalone Claude Code binary (238 MB ELF)
   is uploaded to `/usr/local/bin/claude`.
3. **Skill delivery**:
   - `acp` (Traditional): SKILL.md files deployed to `~/.claude/skills/`
     via BenchFlow's skill deployment infrastructure.
   - `acp-mcp` (MCP): ontomcp binary + TTLs + `.mcp_config.json` injected.
   - `baseline`: No skills.
4. **Agent execution**: `claude -p <instruction> --output-format json`
   is run inside the container via `env.exec()`.
5. **Verification**: Harbor Verifier runs `tests/test.sh` (pytest) inside the
   container and reads CTRF report for fractional scoring.
6. **Retries**: 5 per task with exponential backoff.

#### CLI flags

- `--mode {baseline,acp,acp-mcp,both,all5}` — Agent mode (default: both)
  - `baseline`: no skills — measures raw agent performance
  - `acp`: traditional SKILL.md delivery
  - `acp-mcp`: MCP delivery via ontomcp
  - `both`: runs acp + acp-mcp sequentially
  - `all5`: task-first iteration — for each task runs all 5 cases, then prunes Docker
- `--attempts N` — Clean retries per task (default: 5)
- `--workers N` — Parallel Docker workers (default: 2)
- `--resume` — Resume from previous state file (default: True)
- `--force-restart` — Ignore existing state and start fresh
- `--state-file PATH` — Custom state file path
- `--no-skill-hints` — Omit skill names from prompts (tests discovery mechanism)
- `--only-tasks id1,id2` — Run specific task IDs only
- `--skip-first N` — Skip first N tasks (combine with previous results)

#### Production-realistic benchmark (3 runs)

| Run | Mode    | Skills   | Hints | Tests            |
|-----|---------|----------|-------|------------------|
| 1   | baseline| None     | No    | Baseline (agent only) |
| 2   | acp     | SKILL.md | Yes   | Knowledge quality |
| 3   | acp-mcp | ontomcp  | Yes   | Knowledge quality |

Note: Baseline needs `skill_nudge=""` and no skills_dir. This measures
raw agent performance without any skill delivery.

#### Incremental execution

```bash
# Start with 15 tasks
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 15 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# Later, extend to 25 (resumes from saved state):
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5 --resume
```

### Content coverage (instant, no API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/content_coverage.py --verbose --ttl-dir ~/.ontoskills/packages \
  --json benchmark/results/content_coverage.json
```

### SWE-bench (requires API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark swebench --mode both --max-tasks 25 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results -v
```

## Known issues

### SWE-bench wrapper: custom run-loop required
The SWE-bench wrapper patches `agent.run_turn` to intercept file_read/file_edit. It does NOT use `BaseAgent.run()` — it has a custom loop.

### Content coverage: core.ttl must be loaded
The knowledge yield Level 2 SPARQL uses `rdfs:subClassOf*` property paths. Requires `core.ttl` at `ontoskills/core.ttl`.

## Test verification

```bash
python -m pytest benchmark/tests/ -q
```

## ClaudeCodeAgent (removed)

The legacy host-based ClaudeCodeAgent has been removed. SkillsBench now uses
the native Claude Code CLI binary uploaded directly into Docker containers,
run via ``env.exec()`` — no ACP required.

The binary path is hardcoded: ``~/.local/share/claude/versions/2.1.128``
(238 MB standalone ELF). Update ``_CLAUDE_BIN_PATH`` in
``benchmark/wrappers/skillsbench.py`` when upgrading Claude Code.

## MCP response compaction

All MCP tool responses use compact format by default (88% token reduction).
Compaction happens server-side in Rust (`mcp/src/compact.rs`).

`NODE_BUDGET_CHARS` (12000) limits knowledge node content in compact output to
~3K tokens, preventing overwhelming the agent with low-priority nodes.
