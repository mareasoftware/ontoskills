# Design: Production-Realistic Benchmark + Compact MCP Tool

**Date**: 2026-04-30
**Status**: Approved
**Branch**: feat/mcp-benchmark-improvements

## Problem

The current SkillsBench benchmark has two fairness issues:

1. **MCP prefetch is artificial**: MCP agent preloads knowledge outside the API call
   (no tool calls during conversation), while Traditional uses multi-turn tool calls.
   This confounds delivery method with knowledge quality.

2. **MCP tool schemas are bloated**: 4 tools with 23 parameters (~291 tokens) vs
   `read_skill` with 1 parameter (~62 tokens). The schema overhead inflates MCP's
   token usage regardless of knowledge quality.

## Solution

### 1. Single compact MCP tool: `ontoskill`

Replace all 4 MCP tools (`search`, `get_skill_context`, `evaluate_execution_plan`,
`query_epistemic_rules`) with one unified tool:

```json
{
  "name": "ontoskill",
  "description": "Find or load a skill by name or query.",
  "input_schema": {
    "properties": {
      "q": {"type": "string"},
      "top_k": {"type": "integer", "default": 5}
    },
    "required": ["q"]
  }
}
```

**Token cost**: ~52 tokens (under `read_skill`'s ~62 tokens).

**Behavior** (server-side dispatch in Rust):
- `ontoskill("geospatial-analysis")` → exact match → returns skill context
- `ontoskill("how to calculate earthquake distances")` → no exact match → search
- `ontoskill("geospatial-analysis", top_k=3)` → search for related skills

The server tries exact skill_id lookup first. If found, returns compact context
(same as current `get_skill_context`). If not found, performs search (same as
current `search`). This matches human intuition: "give me X" loads it, "how do I
X?" searches.

**Scope**: This change is in `mcp/src/main.rs` (tool schema + dispatch logic).
The internal Rust functions for search and get_skill_context remain unchanged —
only the external interface changes.

### 2. Four benchmark runs via CLI

All runs use `claude --print --bare` (ClaudeCodeAgent, already implemented).

| Run | Agent     | Skill hints | Multi-turn feedback |
|-----|-----------|-------------|---------------------|
| 1   | Traditional | Yes       | 3 attempts, mechanical |
| 2   | MCP        | Yes        | 3 attempts, mechanical |
| 3   | Traditional | No         | 3 attempts, mechanical |
| 4   | MCP        | No          | 3 attempts, mechanical |

**Case A (with hints)**: Prompt includes "use skill geospatial-analysis".
Both agents know which skill to load. Tests knowledge quality in isolation.

**Case B (without hints)**: Prompt contains only the task instruction.
Agents discover skills on their own. Tests discovery mechanism.

**Multi-turn feedback**: Mechanical (current behavior). After Docker verification,
failed tests and errors are fed back to the agent for retry. Budget split 60/25/15
across 3 attempts. No conversational framing.

### 3. CLI flag

Add `--no-skill-hints` to `benchmark/run.py` (via `skillsbench` kwargs).
When set, the prompt omits "Skills for this task: X" and the numbered rule
about loading skills.

## Files to modify

| File | Change |
|------|--------|
| `mcp/src/main.rs` | Replace 4 tools with single `ontoskill` tool + dispatch |
| `mcp/src/compact.rs` | Update tool name references in compactor |
| `benchmark/agents/ontoskills.py` | Update `_TOOL_DEFINITIONS` to single tool |
| `benchmark/agents/claudecode.py` | Support `--no-skill-hints` in prompt |
| `benchmark/wrappers/skillsbench.py` | Pass `skill_hints` flag, modify prompt |

## Not modified

- `run.py` — existing flags sufficient
- `mcp/src/lib.rs`, `mcp/src/ontology.rs` — internal logic unchanged
- TTL compiler, ontomcp core, skill compilation
- Feedback mechanism (mechanical, already correct)
- `benchmark/agents/traditional.py` — no changes needed

## Expected outcome

- **Token parity**: MCP tool schema ~52 tokens vs `read_skill` ~62 tokens
- **Fair comparison**: both agents use tool calls during conversation
- **Two test dimensions**: knowledge quality (Case A) and discovery (Case B)
- **Honest metrics**: reward, tokens, turns, cost measured per-task
