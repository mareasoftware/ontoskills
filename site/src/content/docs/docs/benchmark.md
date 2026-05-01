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
| Tasks | 23 (seed=7), from a pool of 70+ eligible tasks |
| Attempts | 3 per task (multi-turn with Docker execution feedback) |
| Scoring | Docker + pytest CTRF report, best of 3 attempts |

### Agent modes

**Traditional** — Skill documentation placed in `.claude/skills/` as SKILL.md files. The agent uses Claude Code's native file reading to discover and load skills — exactly how skills work in production.

**OntoSkills MCP** — Skills compiled to OWL 2 ontologies, served via **OntoMCP**. The agent discovers and loads skill knowledge through a single `ontoskill` tool call, receiving structured, prioritized context with interconnections between knowledge elements.

Both modes use the same Claude Code agent, the same model, the same prompts. The only difference is **how skill knowledge is delivered**.

## Results

<BenchmarkApp />

### Key findings

- **OntoSkills leads in pass rate**: 60.9% (14/23) vs 40.0% (10/25) — structured knowledge helps agents solve more tasks correctly
- **OntoSkills has higher avg reward**: 0.93x vs 0.40x — structured delivery dramatically improves task completion
- **OntoSkills uses fewer input tokens** — structured delivery is more compact
- **Intra-skill links** — anti-patterns now point to correct alternatives, constraints link to the workflow steps they apply to

### Per-task highlights

Results shown below are from the initial benchmark run. A re-run with improved knowledge delivery (intra-skill links, fixed caching) is in progress.

### Why structured knowledge wins

Traditional SKILL.md files mix instructions, examples, caveats, and anti-patterns in unstructured text. The agent must parse everything at once with no indication of what's critical.

OntoSkills delivers knowledge as **typed nodes with severity ratings and interconnections**:
- `CRITICAL` rules highlighted first
- Anti-patterns with explicit `rationale` explaining *why* — plus `→ Correct:` links pointing to the right approach
- Constraints linked to the workflow steps they apply to (`→ Applies to:`)
- Curated, prioritized view instead of a wall of text
- Token-efficient compact format that deduplicates content already captured by knowledge nodes

The token efficiency advantage compounds: the agent spends fewer turns reading documentation and more turns writing correct code. With multi-turn feedback (Docker test results), this means more fix iterations within the same token budget.

### Infrastructure note

1 task (`flink-query`) always fails for both modes due to a Java/Flink container that has no Python interpreter. This is an infrastructure limitation, not a knowledge quality issue.

## Limitations

- **Sample size**: 23 tasks from 70+ pool. Results should be confirmed with larger runs.
- **Single model**: All results use glm-5.1 via API proxy. Other models may differ.
- **Single benchmark**: SkillsBench tests code generation. Other benchmarks planned.
- **Seed-dependent**: Task selection varies by seed. We report seed=7 for reproducibility.

## What's next

- **Re-run with fixed cache** — benchmark re-run with all skills properly compiled and loaded
- **Intra-skill link evaluation** — measuring the impact of derivedFromSection, correctAlternative, and appliesToStep links on agent performance
- **Case B** (without hints) — testing skill discovery rather than knowledge quality
- **Test-first prompting** — injecting test specifications into the prompt
- **GAIA** evaluation (Q&A with file attachments)
- **SWE-bench** evaluation (repository patching)

---

> All benchmark code is open source. Run it yourself: `python benchmark/run.py --benchmark skillsbench --mode claudecode --max-tasks 25 --model glm-5.1 --seed 7`
