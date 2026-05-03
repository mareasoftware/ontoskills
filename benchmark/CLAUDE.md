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
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server
- Compiled TTLs at `~/.ontoskills/packages/` — TTL files compiled from skills
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
│   ├── claudecode.py       # ClaudeCodeAgent: legacy host-based CLI agent
│   ├── traditional.py      # Skill registry + read_skill tool (API mode)
│   ├── ontoskills.py       # Single ontoskill MCP tool in API mode
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

Both modes are **100% SkillsBench aligned**: the agent runs inside the
container via BenchFlow ACP. The only difference is how skills are delivered.

```bash
# Prerequisites: clone the SkillsBench repo
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

# ACP mode — Traditional (SKILL.md files injected into Dockerfile)
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v --attempts 5

# ACP-MCP mode — OntoSkills (ontomcp inside container)
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v --attempts 5

# Both modes (comparison)
python benchmark/run.py --benchmark skillsbench --mode both --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v --attempts 5

# No-skill-hints variants (test discovery mechanism)
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 \
  --no-skill-hints ...
```

### SkillsBench methodology

Both modes use BenchFlow Trial for the complete lifecycle inside the
container, aligned with official
[BenchFlow](https://github.com/benchflow-ai/benchflow) /
[SkillsBench](https://github.com/benchflow-ai/skillsbench) evaluation:

1. **Container lifecycle**: BenchFlow `Trial` builds the Docker image and
   starts the container.
2. **Agent execution**: Agent runs inside the container via ACP.
3. **Skill delivery**:
   - `acp` (Traditional): SKILL.md files injected into Dockerfile
   - `acp-mcp` (MCP): ontomcp binary + TTLs + `.mcp_config.json` injected
4. **Verification**: Harbor Verifier runs `tests/test.sh` (pytest) inside the
   container and reads CTRF report for fractional scoring.
5. **Retries**: BenchFlow `RetryConfig` with exponential backoff, clean retries,
   timeout exclusion.

**Comparison is fair**: both modes use identical container management (BenchFlow
Trial) and identical verification (Harbor Verifier). The only difference is
**how skills are delivered**.

12 tasks are skipped: exotic base images, multi-container setups, and
BuildKit heredoc incompatibility with Podman.

#### CLI flags

- `--mode {acp,acp-mcp,both}` — Agent mode (default: both)
- `--attempts N` — Clean retries per task (default: 5, matches SkillsBench)
- `--workers N` — Parallel Docker workers (default: 2)
- `--resume` — Resume from previous state file (default: True)
- `--force-restart` — Ignore existing state and start fresh
- `--state-file PATH` — Custom state file path
- `--no-skill-hints` — Omit skill names from prompts (tests discovery mechanism)
- `--only-tasks id1,id2` — Run specific task IDs only
- `--skip-first N` — Skip first N tasks (combine with previous results)

#### Production-realistic benchmark (4 runs)

| Run | Mode    | Hints | Tests            |
|-----|---------|-------|------------------|
| 1   | acp     | Yes   | Knowledge quality |
| 2   | acp-mcp | Yes   | Knowledge quality |
| 3   | acp     | No    | Discovery         |
| 4   | acp-mcp | No    | Discovery         |

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

## ClaudeCodeAgent (legacy)

Legacy host-based agent using the Claude Code CLI in `--print --bare --output-format json` mode.
No longer used by SkillsBench (replaced by ACP mode), kept for backward compatibility.

Only supports `ontoskills` mode (MCP config for ontomcp). The `traditional` mode has been
removed — use `--mode acp` instead.

## MCP response compaction

All MCP tool responses use compact format by default (88% token reduction).
Compaction happens server-side in Rust (`mcp/src/compact.rs`).

`NODE_BUDGET_CHARS` (12000) limits knowledge node content in compact output to
~3K tokens, preventing overwhelming the agent with low-priority nodes.
