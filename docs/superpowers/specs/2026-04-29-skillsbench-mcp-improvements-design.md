# SkillsBench MCP Performance Improvements

**Date:** 2026-04-29
**Status:** Draft
**Branch:** feat/mcp-benchmark-improvements
**Depends on:** OntoMCP Rust server, skillsbench.py wrapper

## Context

SkillsBench 25-task benchmark results (seed=7, glm-5.1):

| Mode | Pass | Avg Reward |
|------|------|------------|
| Traditional | 10/24 (41.7%) | 0.482 |
| OntoSkills MCP | 6/24 (25.0%) | 0.359 |

MCP underperforms Traditional by 16.7pp. Root cause analysis reveals three distinct problems:

1. **Container bug**: 4 MCP failures are `ModuleNotFoundError` — the agent imports from `skill_scripts/` which exists on the host but is never copied into the Docker container.
2. **Knowledge noise**: When query is available, `compact_context()` emits ALL knowledge nodes without relevance filtering. Irrelevant nodes distract the model and waste tokens.
3. **No retry on fixable failures**: Many MCP failures are fixable (wrong path, missing output file, off-by-one). The agent has no opportunity to correct after seeing Docker/test errors.

## Intervention 1: Copy skill_scripts/ into Docker Container

### Problem

`claudecode.py` creates `skill_scripts/<skill-id>/` directories in the host work dir. The agent's CLAUDE.md instructs it to import via `sys.path.insert(0, 'skill_scripts/<id>')`. But `_run_solution()` in `skillsbench.py` only copies:
- `environment/skills/` → container `/root/.claude/skills/` (for SKILL.md files)
- `solution.py` → container `/tmp/agent_solution.py`

It does NOT copy `skill_scripts/`. When solution.py runs inside the container and tries to import from `skill_scripts`, it crashes with `ModuleNotFoundError`.

### Fix

In `skillsbench.py`, `_run_solution()`: after copying the solution script, also copy the `skill_scripts/` directory from the host work dir into the container at `/tmp/skill_scripts/`.

Files: `benchmark/wrappers/skillsbench.py` (~10 lines)

### Impact

Fixes 4 MCP failures: `travel-planning` (search_cities), `pg-essay-to-audiobook` (requests), `energy-ac-optimal-power-flow` (numpy), `seismic-phase-picking` (numpy). Note: some of these "missing modules" may also be missing from the container's Python environment — the fix ensures the scripts are available but can't install packages the container doesn't have.

## Intervention 2: BM25 Node Ranking in compact_context()

### Problem

`compact_context()` in `mcp/src/compact.rs` emits all knowledge nodes for a skill, sorted by `step_order` then `kind_priority`. For skills with 10-12 nodes, many are irrelevant to the specific task. The model wastes context window on irrelevant knowledge.

### Design

Build a second BM25 index over individual knowledge nodes at server startup:

**Index construction** (`bm25_engine.rs`):
- New `NodeBm25Engine` struct
- For each skill, index each knowledge node as a separate document
- Document text = `directive_content` + `applies_to_context` + `rationale`
- Uses same `bm25` crate as the existing skill-level BM25 engine

**Ranking in compact_context()** (`compact.rs`):
- `compact_context()` gains `query: Option<&str>` + `node_engine: Option<&NodeBm25Engine>` parameters
- When both are `Some`: rank the skill's nodes against the query, take top 8 by BM25 score
- Within the top 8, maintain `step_order` + `kind_priority` as tiebreaker
- When either is `None`: current behavior (all nodes, step_order + kind_priority sort)

**Wiring** (`main.rs`):
- `NodeBm25Engine` constructed at startup alongside the existing `Bm25Engine`
- `prefetch_knowledge` passes the query to `compact_context()`
- `get_skill_context` passes `None` (no query available)

**Performance**: ~5,000-7,000 short documents (20-80 words each). BM25 ranking is <1ms. Startup cost <50ms.

Files: `mcp/src/bm25_engine.rs`, `mcp/src/compact.rs`, `mcp/src/main.rs` (~60 lines total)

### Impact

Reduces knowledge noise in MCP responses. Models receive only relevant nodes, reducing distraction. Particularly valuable for complex skills with many nodes where only a subset applies to the current task.

## Intervention 3: Multi-turn Execution Feedback

### Problem

The benchmark pipeline is single-pass: agent generates solution → Docker verifies → score. Rich feedback (solution stderr, test errors, per-test failure messages) is captured but never fed back to the agent. Many failures are fixable with a second attempt.

### Design

Restructure `run_benchmark_claudecode()` to interleave agent execution and Docker verification per-task:

**Loop** (up to 3 attempts per task):
1. Agent generates `solution.py` via `run_with_cli()`
2. Docker runs solution + pytest via `_run_solution()`
3. If `reward >= 1.0`: done, return result
4. If `reward < 1.0` and attempts < 3: build feedback prompt with:
   - `solution_errors` (last 1000 chars)
   - `test_output` (last 1500 chars, truncated pytest output)
   - `test_details` (per-test name + status + message for failed tests)
   - Original task instruction
5. Agent receives feedback prompt and generates a fixed `solution.py`
6. Repeat from step 2

**Feedback prompt** format:
```
Your previous solution failed Docker verification.

### Test Results
{test_details for failed tests}

### Solution Errors
{solution_errors}

### Task (original)
{original instruction}

Fix the solution.py based on the errors above. Write a corrected solution.py.
```

**Budget management**:
- Each attempt gets `max_budget / 3` of the total budget (e.g., $0.67 each for $2.00 total)
- Each attempt gets `timeout / 3` of the total timeout
- If first attempt passes, no additional cost

**Implementation**:
- `run_task_claudecode_with_retry()` new method in `skillsbench.py`
- Calls existing `run_task_claudecode()` for the first attempt
- Calls `_run_solution()` for verification
- Calls `run_with_cli()` with feedback prompt for retries
- Returns the best result across all attempts (highest reward)

Files: `benchmark/wrappers/skillsbench.py` (~60 lines), `benchmark/agents/claudecode.py` (~10 lines)

### Impact

Helps both Traditional and MCP modes equally. Many task failures are fixable (wrong output path, missing file, format mismatch). A second or third attempt with error feedback can recover these.

## Execution Order

1. **Intervention 1** (skill_scripts copy) — 10 lines, fixes 4 MCP failures immediately
2. **Intervention 2** (BM25 node ranking) — 60 lines Rust, improves knowledge quality
3. **Intervention 3** (multi-turn feedback) — 70 lines Python, improves both modes

## Verification

1. `python -m pytest benchmark/tests/ -q` — existing tests pass
2. Run single task benchmark (both modes) — verify skill_scripts are in container
3. Run 5-task benchmark — compare with previous 25-task results
4. Verify BM25 node ranking: check compact output has ≤8 nodes when query provided
5. Verify multi-turn: check that failed tasks get retry attempts in logs
