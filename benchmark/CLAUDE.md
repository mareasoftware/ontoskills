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
├── content_coverage.py     # Parser coverage + knowledge yield (no API calls)
├── config.py               # Model pricing, benchmark definitions
├── agents/
│   ├── base.py             # BaseAgent with Anthropic API, run-loop, retry
│   ├── claudecode.py       # ClaudeCodeAgent: CLI-based agent (--print --bare mode)
│   ├── traditional.py      # Skill registry + read_skill tool (API mode)
│   ├── ontoskills.py       # Single ontoskill MCP tool (API mode)
│   └── utils.py            # Shared utilities (extract_python_code)
├── wrappers/
│   ├── gaia.py             # GAIA: Q&A with file attachments
│   ├── perpackage.py       # Per-package: run selected packages only
│   ├── skillsbench.py      # SkillsBench: BenchFlow Trial + claude -p
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

```bash
# Prerequisites: clone the SkillsBench repo
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

# Traditional hybrid (SKILL.md files via claude -p)
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 \
  --model glm-5.1 --skills-dir .agents/skills --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v --attempts 5

# OntoSkills MCP hybrid (ontomcp server via claude -p)
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark skillsbench --mode claudecode-mcp --max-tasks 25 \
  --model glm-5.1 --skills-dir .agents/skills --output-dir benchmark/results \
  --skillsbench-repo /tmp/skillsbench_full -v --attempts 5

# No-skill-hints variants (test discovery mechanism)
python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 \
  --no-skill-hints ... # Traditional, no hints
python benchmark/run.py --benchmark skillsbench --mode claudecode-mcp --max-tasks 25 \
  --no-skill-hints ... # MCP, no hints
```

### SkillsBench methodology

Both modes use the **hybrid approach**: BenchFlow Trial for container lifecycle,
host `claude -p` for agent execution. Aligned with official
[BenchFlow](https://github.com/benchflow-ai/benchflow) /
[SkillsBench](https://github.com/benchflow-ai/skillsbench) evaluation:

1. **Container lifecycle**: BenchFlow `Trial` builds the Docker image and starts
   the container.
2. **Agent execution**: Claude Code CLI (`claude -p`) runs on the host with
   task files copied to a temp working directory.
3. **Solution upload**: The agent's `solution.py` is uploaded to the container
   via `trial.env.upload_file()` and executed with `python3`.
4. **Verification**: Harbor Verifier runs `tests/test.sh` (pytest) inside the
   container and reads CTRF report for fractional scoring.
5. **Retries**: BenchFlow `RetryConfig` with exponential backoff, clean retries
   (fresh work dir, no Docker feedback), timeout exclusion.

**Comparison is fair**: both modes use identical container management (BenchFlow
Trial), identical agent execution (claude -p), and identical verification
(Harbor Verifier). The only difference is **how skills are delivered**:
- `claudecode` (Traditional): SKILL.md files in `.claude/skills/`
- `claudecode-mcp` (MCP): Skills via ontomcp MCP tools

12 tasks are skipped: exotic base images, multi-container setups, and
BuildKit heredoc incompatibility with Podman.

#### CLI flags

- `--attempts N` — Clean retries per task (default: 5, matches SkillsBench)
- `--no-skill-hints` — Omit skill names from prompts (tests discovery mechanism)
- `--only-tasks id1,id2` — Run specific task IDs only
- `--skip-first N` — Skip first N tasks (combine with previous results)
- `--workers N` — Parallel Docker verification workers (default: 3)

#### Production-realistic benchmark (4 runs)

| Run | Mode          | Hints | Tests            |
|-----|---------------|-------|------------------|
| 1   | claudecode    | Yes   | Knowledge quality |
| 2   | claudecode-mcp| Yes   | Knowledge quality |
| 3   | claudecode    | No    | Discovery         |
| 4   | claudecode-mcp| No    | Discovery         |

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

## ClaudeCodeAgent

Uses the Claude Code CLI in `--print --bare --output-format json` mode.

Two modes:
- `traditional` — SKILL.md files in `.claude/skills/`, no MCP
- `ontoskills` — MCP config for ontomcp + ontomcp-driver SKILL.md in `.claude/skills/`

The MCP server uses a SkillsBench-only ontology root (`/tmp/skillsbench_ontology/`)
containing only the SkillsBench TTLs for faster loading.

## MCP response compaction

All MCP tool responses use compact format by default (88% token reduction).
Compaction happens server-side in Rust (`mcp/src/compact.rs`).

`NODE_BUDGET_CHARS` (12000) limits knowledge node content in compact output to
~3K tokens, preventing overwhelming the agent with low-priority nodes.
