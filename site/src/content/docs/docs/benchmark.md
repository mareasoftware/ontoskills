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

**OntoSkills** takes a different approach: skill knowledge is compiled into structured OWL 2 ontologies and delivered via MCP tools. The agent queries `search`, `get_skill_context`, `evaluate_execution_plan`, and `query_epistemic_rules` — receiving typed knowledge nodes with severity ratings, epistemic rules, and execution plan evaluations.

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
| Tasks | 10 (seed=7), from a pool of 70+ eligible tasks |
| Scoring | Docker + pytest CTRF report |

### Agent modes

**Traditional** — Skill documentation placed in `.claude/skills/` as SKILL.md files. The agent uses Claude Code's native file reading to discover and load skills — exactly how skills work in production.

**OntoSkills MCP** — Skills compiled to OWL 2 ontologies, served via OntoMCP. The agent discovers skills through MCP tools (`search`, `get_skill_context`). An `ontomcp-driver` skill teaches the agent the optimal workflow for querying the ontology.

Both modes use the same Claude Code agent, the same model, the same prompts. The only difference is **how skill knowledge is delivered**.

## Results

<BenchmarkApp />

### Key findings

- **OntoSkills MCP passes more tasks**: 50% vs 40% overall, 83% vs 67% on skill-knowledge tasks (excluding infrastructure failures)
- **OntoSkills uses fewer tokens**: 15% fewer input tokens, 35% fewer output tokens — structured knowledge is more compact
- **OntoSkills costs less**: $2.92 vs $3.97 total (-26%) due to lower token usage
- **Biggest win**: paper-anonymizer (PDF processing) — Traditional failed completely, OntoSkills passed all 6 tests

### Infrastructure failures

4 of 10 tasks failed for **both modes** due to infrastructure issues unrelated to skill quality:
- `gh-repo-analytics` — GitHub CLI not authenticated inside container
- `flood-risk-analysis` — external HTTP endpoint returned 404
- `lab-unit-harmonization` / `fix-visual-stability` — agent timeouts

These are excluded from the skill-knowledge comparison above.

## Why structured knowledge wins

Traditional SKILL.md files mix instructions, examples, caveats, and anti-patterns in unstructured text. The agent must parse everything at once, with no indication of what's critical vs. optional.

OntoSkills delivers knowledge as **typed nodes with severity ratings**:
- `CRITICAL` rules are highlighted first
- Anti-patterns come with explicit `rationale` explaining *why* to avoid them
- Execution plan evaluation catches common mistakes before coding begins
- The agent gets a curated, prioritized view rather than a wall of text

This is especially valuable for complex domains like PDF processing (paper-anonymizer) where the difference between correct and incorrect output depends on subtle configuration details.

## Limitations

- **Sample size**: 10 tasks from a pool of 70+. Results should be confirmed with larger runs.
- **Single model**: All results use glm-5.1 via API proxy. Performance may differ with other models.
- **Single benchmark**: SkillsBench tests code generation. Other benchmarks (GAIA for Q&A, SWE-bench for repo patching) are planned.
- **Seed-dependent**: Task selection varies by seed. We report seed=7 for reproducibility.

## What's next

- **25-task run** in progress for stronger statistical significance
- **GAIA** evaluation (Q&A with file attachments) — requires HuggingFace authentication
- **SWE-bench** evaluation (repository patching) — planned with updated models

---

> All benchmark code is open source. Run it yourself: `python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 --model glm-5.1 --seed 7`
