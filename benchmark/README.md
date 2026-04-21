# OntoSkills Benchmarks

Benchmark suite comparing OntoSkills (SPARQL) vs traditional LLM skill reading.

## Quick Start

```bash
# Run with real skill directories
python run.py --skills-dir /path/to/skills --ttl-dir /path/to/ttls

# Only OntoMCP (no API key needed)
python run.py --ttl-dir /path/to/ttls --ontomcp-only

# Only traditional (needs ANTHROPIC_API_KEY)
python run.py --skills-dir /path/to/skills --traditional-only

# Custom iterations and runs
python run.py --skills-dir /path/to/skills --ttl-dir /path/to/ttls --iterations 100 --runs 3
```

## Structure

```
benchmark/
├── run.py                   # Main runner — orchestrates both benchmarks
├── config.py                # Model pricing, context limits, task definitions
├── compare.py               # Generate Markdown comparison report
├── ontomcp-bench/           # Rust SPARQL benchmark
│   ├── Cargo.toml
│   └── src/main.rs
├── traditional-bench/       # Python LLM benchmark (Anthropic only)
│   ├── bench.py
│   └── requirements.txt
└── results/                 # Output (gitignored)
    ├── ontomcp-bench.json
    ├── traditional-bench.json
    └── comparison.md
```

## What it measures

### OntoSkills (Rust SPARQL)
- **Latency**: sub-ms query times for each SPARQL operation
- **Queries**: search by intent, search by type, get context, epistemic rules, planning, full scan
- **Iterations**: 1000 per query (configurable via `--iterations`)
- **Accuracy**: queries are materialized (solutions consumed) to measure full execution, not lazy setup

### Traditional (LLM reads files)
- **Latency**: wall-clock time for each skill-related question
- **Tokens**: exact count via `client.count_tokens()`, input + output per query
- **Cost**: computed for 6 models (Claude Opus/Sonnet, GPT-5.4/mini, Gemini Pro/Flash)
- **Determinism**: same question N times, count unique answers
- **Context overflow**: flagged when prompt tokens + reserved output tokens (1024) exceed context window
- **Rate limit resilience**: exponential backoff retry on `anthropic.RateLimitError`
- **Runs**: 5 per task (configurable via `--runs`)

### Tasks compared

| Task | OntoSkills | Traditional |
|------|-----------|-------------|
| Find skill by intent | SPARQL `search` | LLM reads all files, answers |
| Get skill context | SPARQL `get_skill_context` | LLM reads all files, answers |
| Plan execution | SPARQL `evaluate_execution_plan` | LLM reads all files, plans |
| Check dependencies | SPARQL full scan | LLM reads all files, answers |

### Cost comparison models

Only Anthropic models are called via API. Other models are price-comparison only (same token counts, different pricing):

| Model | Input ($/MTok) | Output ($/MTok) |
|-------|----------------|-----------------|
| Claude Opus 4.6 | $5.00 | $25.00 |
| Claude Sonnet 4.6 | $3.00 | $15.00 |
| GPT-5.4 | $2.50 | $15.00 |
| GPT-5.4 mini | $0.75 | $4.50 |
| Gemini 3.1 Pro (≤200K tokens) | $2.00 | $12.00 |
| Gemini 3.1 Pro (>200K tokens) | $4.00 | $18.00 |
| Gemini 3.1 Flash | $0.75 | $4.50 |

## Prerequisites

- Rust toolchain (for `ontomcp-bench`)
- Python 3.10+ with `anthropic` package (for `traditional-bench`)
- `ANTHROPIC_API_KEY` env var (for traditional benchmark and skeleton LLM)
- `libclang-dev` package (for oxrocksdb-sys compilation)

## DocGraph Coverage Benchmark

Measures how much of each SKILL.md is captured as typed RDF content blocks. Target: ≥95% line-level coverage across 30 real skills (14 superpowers + 16 Anthropic).

### What it measures

- **Line-level coverage**: percentage of non-blank lines that fall within an extracted `FlatBlock`'s line range
- **Block type coverage**: verifies all expected block types (heading, paragraph, code_block, bullet_list, etc.) appear across the skill corpus

### Usage

```bash
# Verbose per-skill report (no API key needed for flat extraction only)
python benchmark/docgraph_coverage.py --verbose

# With skeleton LLM enhancement (needs API key)
ANTHROPIC_API_KEY=sk-ant-... python benchmark/docgraph_coverage.py --verbose

# JSON output for CI
python benchmark/docgraph_coverage.py --json results/coverage.json

# Custom target
python benchmark/docgraph_coverage.py --target 90
```

### Skill directories

By default, `benchmark/docgraph_coverage.py` reads skills from `./.agents/skills/`. Override with:
- `DOCGRAPH_SKILLS_DIR` — path to the skills directory to analyze
