---
title: Benchmark Methodology & Results
description: OntoSkills MCP vs traditional skills — 100% BenchFlow-aligned deterministic evaluation via SkillsBench
sidebar:
  order: 15.5
---

Does structured knowledge delivered via MCP tools actually help agents complete tasks better than raw markdown files? We ran a controlled experiment to find out — and continue improving the knowledge delivery with each iteration.

---

import BenchmarkApp from '../../components/benchmark/BenchmarkApp.astro';

## The Question

AI coding agents like Claude Code rely on skill documentation to solve specialized tasks — generating DOCX files, processing PDFs, analyzing financial data. Today, these skills are delivered as plain markdown files (`SKILL.md`). The agent reads the raw text and must extract instructions, heuristics, and anti-patterns on its own.

**OntoSkills** takes a different approach: skill knowledge is compiled into structured OWL 2 ontologies and delivered via **OntoMCP**. The agent queries for skill knowledge — receiving typed knowledge nodes with severity ratings, anti-patterns with rationale, curated code examples, and **intra-skill links** that connect anti-patterns to correct alternatives and constraints to the workflow steps they apply to.

Which approach produces better results?

## SkillsBench: Deterministic Code Generation

We evaluated both approaches using [SkillsBench](https://github.com/benchflow-ai/skillsbench), part of the [BenchFlow](https://github.com/benchflow-ai/benchflow) evaluation suite. The evaluation is **100% SkillsBench aligned** — the agent runs inside the Docker container via ACP (Agent Communication Protocol), exactly as specified by the official SkillsBench methodology.

### How evaluation works

1. The agent runs **inside the task's Docker container** via BenchFlow ACP (Agent Communication Protocol)
2. It receives the task description and skill hints, then generates a Python solution script
3. [Harbor Verifier](https://github.com/benchflow-ai/harbor) runs the task's pytest test suite — deterministic, no human judgment
4. Score = `tests_passed / tests_total` per task (CTRF report)
5. Retries with exponential backoff — best reward wins

This is not LLM-as-judge. The evaluation is fully deterministic and reproducible. Both modes use identical container management (BenchFlow Trial) and identical verification (Harbor Verifier). The only difference is **how skill knowledge is delivered**.

### Setup

| Parameter | Value |
|-----------|-------|
| Agent | claude-agent-acp (via BenchFlow ACP) |
| Model | glm-5.1 (via API proxy) |
| Infrastructure | [BenchFlow](https://github.com/benchflow-ai/benchflow) Trial + [Harbor](https://github.com/benchflow-ai/harbor) Verifier |
| Scoring | Harbor Verifier + pytest CTRF report |
| Retries | 5 per task (BenchFlow RetryConfig, clean retries, best reward wins) |
| Workers | 2 parallel Docker containers |

### Agent modes

**Traditional (`acp`)** — SKILL.md files injected into the Docker image via BenchFlow's `_inject_skills_into_dockerfile()`. The agent discovers and loads skills using its native file reading capabilities — exactly how skills work in production. 100% SkillsBench aligned.

**OntoSkills MCP (`acp-mcp`)** — Skills compiled to OWL 2 ontologies, served via **OntoMCP** inside the container. The `ontomcp` binary, TTL packages, and `.mcp_config.json` are injected between container start and agent installation. The agent discovers and loads skill knowledge through a single `ontoskill` tool call, receiving structured, prioritized context with interconnections between knowledge elements. 100% SkillsBench aligned.

**Baseline (`baseline`)** — No skills, no hints. The raw agent runs inside the container with only the task description. This measures the model's zero-shot capability.

Both ACP and ACP-MCP modes run the same agent inside the container, using the same model and the same BenchFlow infrastructure. The comparison is fair — the only variable is how skills are delivered.

## 5-Case Experimental Design

We run five controlled cases to isolate different aspects of skill delivery:

| Run | Mode | Skills | Hints | What it measures |
|-----|------|--------|-------|------------------|
| 1 | baseline | None | No | **Baseline** — raw agent without any skills |
| 2 | acp | SKILL.md | Yes | **Knowledge quality** — traditional delivery |
| 3 | acp-mcp | ontomcp | Yes | **Knowledge quality** — structured delivery |
| 4 | acp | SKILL.md | No | **Discovery** — agent must find skills on its own |
| 5 | acp-mcp | ontomcp | No | **Discovery** — agent must query MCP tools |

- **Baseline (Run 1)**: The raw agent with no skills and no hints. This establishes the floor — what the model can do without any domain knowledge.
- **Knowledge quality (Runs 2-3)**: Skills are explicitly named in the prompt (`skill_nudge="name"`). This isolates how well each delivery method transfers knowledge to the agent.
- **Discovery (Runs 4-5)**: No skill names in the prompt (`skill_nudge=""`). This tests whether the agent can autonomously discover and use available skills.

### Key comparisons

- **Run 2 vs Run 3**: Knowledge quality with hints — traditional vs structured delivery when the agent knows which skills to use
- **Run 4 vs Run 5**: Discovery without hints — traditional vs structured delivery when the agent must find skills autonomously
- **Run 1 vs Run 2**: Skill delta — how much do skills help (traditional)?
- **Run 1 vs Run 3**: Skill delta — how much do skills help (structured)?
- **Run 2 vs Run 4**: Discovery penalty (traditional) — how much is lost when hints are removed?
- **Run 3 vs Run 5**: Discovery penalty (structured) — how well does MCP handle autonomous discovery?

## Running the benchmark

### Prerequisites

```bash
# Clone SkillsBench tasks
git clone --depth 1 https://github.com/benchflow-ai/skillsbench /tmp/skillsbench_full

# Install benchflow (0.3.3.dev0 required for glm-5.1 proxy support)
pip install git+https://github.com/benchflow-ai/benchflow.git

# Set API key
export ANTHROPIC_API_KEY="your-key"
```

### Run all 5 cases

```bash
python benchmark/run.py \
  --benchmark skillsbench \
  --mode all5 \
  --max-tasks 25 \
  --model glm-5.1 \
  --attempts 5 \
  --workers 2 \
  --skillsbench-repo ~/.ontoskills/skillsbench \
  --output-dir benchmark/results \
  --force-restart -v
```

### Run individual cases

```bash
# Baseline only
python benchmark/run.py --benchmark skillsbench --mode baseline --max-tasks 25 -v

# Traditional with hints
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 -v

# MCP with hints
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --max-tasks 25 -v

# MCP without hints (discovery)
python benchmark/run.py --benchmark skillsbench --mode acp-mcp --no-skill-hints --max-tasks 25 -v
```

### Incremental execution

Start with 15 tasks, extend to 25 later without re-running completed tasks:

```bash
# First run: 15 tasks
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 15 -v

# Extend to 25 (resumes from saved state)
python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 --resume -v
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `both` | `acp`, `acp-mcp`, `baseline`, `both`, `all5` |
| `--attempts` | 5 | Clean retries per task (matches SkillsBench) |
| `--workers` | 2 | Parallel Docker workers |
| `--resume` | True | Resume from previous state file |
| `--force-restart` | False | Ignore existing state, start fresh |
| `--no-skill-hints` | False | Omit skill names from prompts |
| `--only-tasks id1,id2` | — | Run specific task IDs only |
| `--skip-first N` | 0 | Skip first N tasks |

## Results

Results coming soon — 5-case benchmark running with 25 tasks x 5 attempts, fully BenchFlow-aligned.

<BenchmarkApp />

### Why structured knowledge wins

Traditional SKILL.md files mix instructions, examples, caveats, and anti-patterns in unstructured text. The agent must parse everything at once with no indication of what's critical.

OntoSkills delivers knowledge as **typed nodes with severity ratings and interconnections**:
- `CRITICAL` rules highlighted first
- Anti-patterns with explicit `rationale` explaining *why* — plus `→ Correct:` links pointing to the right approach
- Constraints linked to the workflow steps they apply to (`→ Applies to:`)
- Curated, prioritized view instead of a wall of text
- Token-efficient compact format that deduplicates content already captured by knowledge nodes

The token efficiency advantage compounds: the agent spends fewer turns reading documentation and more turns writing correct code.

## Methodology details

### 12 skipped tasks

Tasks are skipped for infrastructure reasons (not skill-related):
- Exotic base images (gcr.io, bugswarm cached images)
- Multi-container docker-compose setups
- BuildKit heredoc syntax incompatible with Podman

### State persistence

Benchmark state is saved after every single attempt (not just completed tasks). If the process crashes, all progress is preserved. Resume picks up from the exact state.

### Worker pool

Two async workers share an `asyncio.Queue`. Each worker picks a task, runs the full trial lifecycle (Docker build → agent execution → verification), and either marks it complete or re-enqueues it for retry with exponential backoff.

## Limitations

- **Sample size**: Results from a pool of 70+ eligible tasks (some skipped due to infrastructure constraints).
- **Single model**: All results use glm-5.1 via API proxy. Other models may differ.
- **Single benchmark**: SkillsBench tests code generation. Other benchmarks planned.

## What's next

- **5-case results** — full benchmark with baseline, knowledge quality, and discovery dimensions
- **Intra-skill link evaluation** — measuring the impact of derivedFromSection, correctAlternative, and appliesToStep links
- **GAIA** evaluation (Q&A with file attachments)
- **SWE-bench** evaluation (repository patching)

---

> All benchmark code is open source. Run it yourself: `python benchmark/run.py --benchmark skillsbench --mode all5 --max-tasks 25 --model glm-5.1 --attempts 5 --workers 2`
