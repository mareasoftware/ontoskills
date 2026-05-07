# OntoSkills Benchmarks

Benchmark suite comparing **OntoSkills MCP** vs **Traditional SKILL.md** skill delivery, using deterministic evaluation inside Docker containers via [BenchFlow](https://github.com/benchflow-ai/benchflow) ACP.

## Benchmarks

### SkillsBench (primary)

Deterministic code-generation benchmark. The agent receives a task, generates a Python solution, and a pytest test suite scores the result inside the task's Docker container.

- **Dataset**: [SkillsBench](https://github.com/benchflow-ai/skillsbench) tasks (70+ available)
- **Evaluation**: [BenchFlow](https://github.com/benchflow-ai/benchflow) Trial + [Harbor](https://github.com/benchflow-ai/harbor) Verifier
- **Metric**: Fractional score = `tests_passed / tests_total` per task (CTRF report)
- **Agent mode**: ACP — agent runs inside container via BenchFlow Trial

Both modes are **100% SkillsBench/BenchFlow aligned**: the agent runs inside the container via ACP. The only difference is how skills are delivered:

- **`acp` (Traditional)**: SKILL.md files injected into the Dockerfile
- **`acp-mcp` (MCP)**: ontomcp binary + TTLs + `.mcp.json` injected into the container

#### 5-case experimental design

| Run | Mode    | Skills   | Hints | Tests            |
|-----|---------|----------|-------|------------------|
| 1   | acp     | None     | No    | Baseline (agent only) |
| 2   | acp     | SKILL.md | Yes   | Knowledge quality |
| 3   | acp-mcp | ontomcp  | Yes   | Knowledge quality |
| 4   | acp     | SKILL.md | No    | Discovery         |
| 5   | acp-mcp | ontomcp  | No    | Discovery         |

- **Baseline (Run 1)**: Raw agent with no skills — measures base capability
- **Knowledge quality (Runs 2-3)**: Skills hinted in prompt — measures how well knowledge is delivered
- **Discovery (Runs 4-5)**: No skill hints — measures whether the agent can find skills on its own

### GAIA (API-mode, not ACP)

General AI Assistant benchmark. Agents answer questions with file attachments.

- **Dataset**: `gaia-benchmark/GAIA` (HuggingFace)
- **Metric**: Exact-match accuracy
- **Agent mode**: API-mode (Anthropic direct), not ACP
- **Status**: Secondary benchmark, not BenchFlow-aligned

### SWE-bench (API-mode, not ACP)

Software engineering benchmark. Agents produce unified-diff patches.

- **Dataset**: `princeton-nlp/SWE-bench_Verified` (HuggingFace)
- **Metric**: Resolve rate (external harness)
- **Agent mode**: API-mode (Anthropic direct), not ACP
- **Status**: Secondary benchmark, not BenchFlow-aligned

## Quick Start

```bash
# Prerequisites: clone SkillsBench repo
git clone --depth 1 https://github.com/benchflow-ai/skillsbench ~/.ontoskills/skillsbench

# Run ACP mode (Traditional)
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# Run ACP-MCP mode (OntoSkills)
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# Run both modes for comparison
python benchmark/run.py --benchmark skillsbench --mode both --max-tasks 25 \
  --model glm-5.1 --output-dir benchmark/results \
  --skillsbench-repo ~/.ontoskills/skillsbench -v --attempts 5

# No-skill-hints variant (test discovery mechanism)
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 \
  --no-skill-hints ...

# Incremental: start with 15 tasks, extend to 25 later
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 15 ...
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 --resume ...
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--benchmark` | `skillsbench` | `skillsbench`, `gaia`, `swebench`, or `all` |
| `--mode` | `both` | `acp`, `acp-mcp`, or `both` |
| `--skills-dir` | `benchmark/skills/` | SKILL.md files for traditional agent |
| `--ttl-dir` | `~/.ontoskills/packages` | TTL ontology packages for OntoSkills agent |
| `--ontomcp-bin` | `~/.ontoskills/bin/ontomcp` | Path to ontomcp binary |
| `--model` | `glm-5.1` | Model ID for the agent |
| `--max-tasks` | all | Limit tasks per benchmark |
| `--attempts` | `5` | Clean retries per task (BenchFlow RetryConfig) |
| `--workers` | `2` | Parallel Docker workers |
| `--resume` | enabled | Resume from previous state file |
| `--force-restart` | off | Ignore existing state, start fresh |
| `--state-file` | auto | Custom state file path |
| `--no-skill-hints` | off | Omit skill names from prompts (discovery test) |
| `--only-tasks` | all | Run specific task IDs only (comma-separated) |
| `--skip-first` | `0` | Skip first N tasks |
| `--output-dir` | `benchmark/results/` | Where to write results |
| `--skillsbench-repo` | required | Path to cloned SkillsBench repo |
| `-v` | off | Verbose logging |

## Structure

```
benchmark/
├── run.py                    # Main CLI orchestrator
├── state.py                  # BenchmarkState — resume, incremental save
├── content_coverage.py       # Parser coverage + knowledge yield (no API calls)
├── config.py                 # Model pricing, benchmark definitions
├── agents/
│   ├── base.py               # BaseAgent with Anthropic API, run-loop, retry
│   ├── claudecode.py         # ClaudeCodeAgent: legacy host-based CLI agent
│   ├── traditional.py        # Skill registry + read_skill tool (API mode)
│   ├── ontoskills.py         # Single mcp__onto__skill MCP tool in API mode
│   └── utils.py              # Shared utilities (extract_python_code)
├── wrappers/
│   ├── skillsbench.py        # SkillsBench: ACP + ACP-MCP via BenchFlow Trial
│   ├── gaia.py               # GAIA: Q&A with file attachments (API mode)
│   ├── perpackage.py         # Per-package: run selected packages only
│   ├── swebench.py           # SWE-bench: repo checkout + diff patch (API mode)
│   └── tau2bench.py          # tau2-bench: agent benchmarking wrapper
├── reporting/
│   ├── metrics.py            # compute_comparison()
│   ├── comparison.py         # generate_comparison_report()
│   └── chart_data.py         # chart-ready JSON generation
├── mcp_client/
│   └── client.py             # JSON-RPC MCP client for ontomcp subprocess
├── tests/                    # Unit tests for benchmark framework
├── data/                     # Downloaded datasets
└── results/                  # Benchmark output (JSON + comparison.md)
```

## What Gets Measured

For each task and agent mode:

- **Quality**: Fractional score = `tests_passed / tests_total`
- **Tokens**: Input, output, and total tokens per task
- **Latency**: Wall-clock time per task
- **Cost**: Projected cost using `config.MODEL_PRICING`
- **Retries**: How many attempts were needed

When multiple modes are run, a comparison report is generated with:

1. **Quality** — score delta between modes
2. **Efficiency** — tokens and latency comparison
3. **Cost** — cost projections
4. **Aggregate** — weighted averages, overall improvement

## Prerequisites

- Python 3.10+ with `anthropic`, `datasets`, `benchflow`, `harbor`, `rdflib` packages
- `ANTHROPIC_API_KEY` env var (required for both agents)
- `ontomcp` binary at `~/.ontoskills/bin/ontomcp` (for MCP mode)
- TTL ontology packages at `~/.ontoskills/packages/` (for MCP mode)
- Docker (or Podman with docker alias) for container-based evaluation
- Cloned SkillsBench repo for task definitions

## Content Coverage Benchmark

Separate tool that measures how much of each SKILL.md is captured as typed RDF content blocks. Runs instantly with no API calls.

```bash
python benchmark/content_coverage.py --verbose
```

Target: 95%+ line-level coverage across real skills.

## Running Tests

```bash
python -m pytest benchmark/tests/ -q
```
