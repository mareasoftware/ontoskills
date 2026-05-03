---
title: Benchmark Results
description: OntoSkills MCP vs traditional skills — deterministic evaluation results from SkillsBench
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

We evaluated both approaches using [SkillsBench](https://github.com/benchflow-ai/skillsbench), part of the [BenchFlow](https://github.com/benchflow-ai/benchflow) evaluation suite.

### How evaluation works

1. The agent runs **inside the task's Docker container** via BenchFlow ACP (Agent Communication Protocol)
2. It receives the task description and generates a Python solution script
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

### Agent modes

**Traditional (`acp`)** — SKILL.md files injected into the Docker image. The agent discovers and loads skills using its native file reading capabilities — exactly how skills work in production.

**OntoSkills MCP (`acp-mcp`)** — Skills compiled to OWL 2 ontologies, served via **OntoMCP** inside the container. The `ontomcp` binary, TTL packages, and `.mcp_config.json` are injected into the Docker image. The agent discovers and loads skill knowledge through a single `ontoskill` tool call, receiving structured, prioritized context with interconnections between knowledge elements.

Both modes run the same agent inside the container, using the same model and the same BenchFlow infrastructure.

## 5-Case Experimental Design

We run five controlled cases to isolate different aspects of skill delivery:

| Run | Mode | Skills | Hints | What it measures |
|-----|------|--------|-------|------------------|
| 1 | acp | None | No | **Baseline** — raw agent without any skills |
| 2 | acp | SKILL.md | Yes | **Knowledge quality** — traditional delivery |
| 3 | acp-mcp | ontomcp | Yes | **Knowledge quality** — structured delivery |
| 4 | acp | SKILL.md | No | **Discovery** — agent must find skills on its own |
| 5 | acp-mcp | ontomcp | No | **Discovery** — agent must query MCP tools |

- **Baseline (Run 1)**: The raw agent with no skills and no hints. This establishes the floor — what the model can do without any domain knowledge.
- **Knowledge quality (Runs 2-3)**: Skills are explicitly named in the prompt. This isolates how well each delivery method transfers knowledge to the agent.
- **Discovery (Runs 4-5)**: No skill names in the prompt. This tests whether the agent can autonomously discover and use available skills.

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

> All benchmark code is open source. Run it yourself: `python benchmark/run.py --benchmark skillsbench --mode acp --max-tasks 25 --model glm-5.1 --attempts 5`
