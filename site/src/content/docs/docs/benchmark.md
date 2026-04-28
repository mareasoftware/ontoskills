---
title: Benchmark Results
description: OntoSkills MCP vs traditional skills — deterministic evaluation results
sidebar:
  order: 15.5
---

Benchmarks measure whether structured knowledge delivered via MCP tools improves agent task completion compared to raw markdown skill files.

---

## SkillsBench

Docker-based deterministic evaluation of code generation tasks.

### Methodology

- Agent: Claude Code CLI (`--print --bare` mode)
- Agent generates a Python solution script
- Script runs inside the task's Docker container (via podman)
- Task's pytest test suite verifies output files (deterministic scoring)
- 9 tasks skipped (uncompiled skills), 6 tasks skipped (exotic base images + BuildKit)
- Model: glm-5.1, seed=7, 10 tasks per mode

### Results (seed=7, glm-5.1, Claude Code, 10 tasks)

| Task | Traditional | OntoSkills MCP |
|------|------------|----------------|
| reserves-at-risk-calc (financial) | 0/5 FAIL | **1/5 PARTIAL** |
| offer-letter-generator (docx) | 4/4 PASS | 4/4 PASS |
| lab-unit-harmonization (healthcare) | 0/8 FAIL | 0/8 FAIL |
| travel-planning | 11/11 PASS | 11/11 PASS |
| paper-anonymizer (PDF) | 0/6 FAIL | **6/6 PASS** |
| flood-risk-analysis (data) | 0/2 FAIL | 0/2 FAIL |
| 3d-scan-calc (engineering) | 2/2 PASS | 2/2 PASS |
| exceltable-in-ppt (Office) | 8/8 PASS | 8/8 PASS |
| fix-visual-stability (web) | 0/2 FAIL | 0/2 FAIL |
| gh-repo-analytics (devops) | 0/8 FAIL | 0/8 FAIL |

| Metric | Traditional | OntoSkills MCP | Delta |
|--------|------------|----------------|-------|
| Pass rate | 40% | **50%** | +25% |
| Avg reward | 0.40 | **0.52** | +30% |

### How it works

**Traditional mode** — The agent receives a `SKILL.md` file placed in `.claude/skills/`. It reads the raw markdown and must interpret instructions, heuristics, and anti-patterns from unstructured text. All knowledge is accessed through file reading.

**OntoSkills MCP mode** — The agent has access to OntoMCP tools (`search`, `get_skill_context`, `evaluate_execution_plan`, `query_epistemic_rules`). It queries structured OWL 2 ontologies, receiving knowledge nodes, epistemic rules, and execution plan evaluations. An `ontomcp-driver` skill teaches the agent how to use the MCP tools effectively.

---

## GAIA

Question-answering with file attachments (PDF, DOCX, XLSX, etc.).

> Results from the API-based agent exist. Claude Code mode results coming soon.

---

## SWE-bench

Repository patching — agent generates git diffs to fix real GitHub issues.

> Results from the API-based agent exist. Claude Code mode results coming soon.
