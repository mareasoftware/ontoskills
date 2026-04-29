---
title: Benchmark Results
description: OntoSkills MCP vs traditional skills — deterministic evaluation results from SkillsBench
sidebar:
  order: 15.5
---

Does structured knowledge delivered via MCP tools actually help agents complete tasks better than raw markdown files? We ran a controlled experiment to find out.

---

import BenchmarkApp from '../../components/benchmark/BenchmarkApp.astro';

## The Question

AI coding agents like Claude Code rely on skill documentation to solve specialized tasks — generating DOCX files, processing PDFs, analyzing financial data. Today, these skills are delivered as plain markdown files (`SKILL.md`). The agent reads the raw text and must extract instructions, heuristics, and anti-patterns on its own.

**OntoSkills** takes a different approach: skill knowledge is compiled into structured OWL 2 ontologies and delivered via MCP tools. The agent uses `prefetch_knowledge` to load structured skill knowledge in one call — receiving typed knowledge nodes with severity ratings, epistemic rules, and execution plan evaluations.

Which approach produces better results?

## SkillsBench: Deterministic Code Generation

We evaluated both approaches using [SkillsBench](https://github.com/benchflow-ai/skillsbench), a benchmark that measures an agent's ability to generate working code for real-world tasks.

### How evaluation works

1. The agent receives a task description and relevant skill documentation
2. It generates a Python solution script
3. The script runs inside the task's **Docker container** (via podman)
4. A **pytest test suite** verifies the output files — deterministic, no human judgment
5. Score = `tests_passed / tests_total` per task

This is not LLM-as-judge. The evaluation is fully deterministic and reproducible.

### Setup

| Parameter | Value |
|-----------|-------|
| Agent | Claude Code CLI (`--print --bare` mode) |
| Model | glm-5.1 (via API proxy) |
| Tasks | 24 (seed=7), from a pool of 70+ eligible tasks |
| Attempts | 3 per task (multi-turn with Docker execution feedback) |
| Scoring | Docker + pytest CTRF report, best of 3 attempts |

### Agent modes

**Traditional** — Skill documentation placed in `.claude/skills/` as SKILL.md files. The agent uses Claude Code's native file reading to discover and load skills — exactly how skills work in production.

**OntoSkills MCP** — Skills compiled to OWL 2 ontologies, served via OntoMCP. The agent discovers skills through MCP tools (`prefetch_knowledge`, `search`, `get_skill_context`). An `ontomcp-driver` skill teaches the agent the optimal workflow for querying the ontology.

Both modes use the same Claude Code agent, the same model, the same prompts. The only difference is **how skill knowledge is delivered**.

## Results

<BenchmarkApp />

### Key findings

- **Traditional leads in pass rate**: 50% (12/24) vs 37.5% (9/24) — raw markdown with multi-turn feedback is highly effective
- **OntoSkills is more efficient**: 11% fewer input tokens, 7% fewer output tokens — structured knowledge is more compact
- **OntoSkills costs less**: $10.38 vs $11.53 total (-10%) due to lower token usage
- **Both benefited from multi-turn**: The 3-attempt feedback loop improved results for both modes (Traditional: 41.7%→50%, MCP: 25%→37.5%)

### Honest analysis

Traditional's higher pass rate comes from the agent having full SKILL.md content available from the start — it can read the entire skill documentation in one shot and cross-reference across files. When multi-turn feedback is added (Docker test results fed back for fix attempts), Traditional agents have enough context to self-correct effectively.

OntoSkills' structured knowledge delivery excels at **token efficiency** — the agent receives prioritized, typed knowledge nodes instead of raw text. However, for this benchmark's code-generation tasks, having complete SKILL.md content proved more useful than having structured but potentially filtered knowledge.

The gap narrowed significantly from the initial run (Traditional +16.7pp advantage → +12.5pp), as OntoSkills benefited more from multi-turn feedback in relative terms (+50% improvement vs +20% for Traditional).

### Infrastructure failures

1 task failed for **both modes** due to infrastructure issues unrelated to skill quality:
- `flink-query` — Java/Flink container has no Python interpreter; the benchmark always runs `python3 /tmp/agent_solution.py`

## Why structured knowledge still matters

While Traditional leads on raw pass rate for code-generation tasks, OntoSkills delivers knowledge more efficiently:

- **Typed nodes with severity ratings** let agents prioritize critical rules
- **Anti-patterns with rationale** explain *why* to avoid specific approaches
- **Execution plan evaluation** catches mistakes before coding begins
- **11% fewer input tokens** translates to significant cost savings at scale

The token efficiency advantage grows with larger skill catalogs — when an agent must navigate hundreds of skills rather than a handful, structured delivery via MCP becomes increasingly valuable.

## Limitations

- **Single model**: All results use glm-5.1 via API proxy. Performance may differ with other models.
- **Single benchmark**: SkillsBench tests code generation. Other benchmarks (GAIA for Q&A, SWE-bench for repo patching) would test different capabilities.
- **Seed-dependent**: Task selection varies by seed. We report seed=7 for reproducibility.
- **BM25 node filtering**: The MCP agent uses BM25-ranked knowledge nodes, which may filter out important context for some tasks.

## What's next

- **Improved node filtering** — tuning BM25 parameters to retain more relevant knowledge
- **Test-first prompting** — injecting test specifications into the prompt for higher first-attempt success
- **GAIA** evaluation (Q&A with file attachments) — requires HuggingFace authentication
- **SWE-bench** evaluation (repository patching) — planned with updated models

---

> All benchmark code is open source. Run it yourself: `python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 --model glm-5.1 --seed 7`
