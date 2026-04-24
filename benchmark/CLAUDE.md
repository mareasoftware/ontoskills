# OntoSkills Benchmark

## Prerequisites

### Environment variables
- `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` — required for both agents
- `ANTHROPIC_BASE_URL` — set to `https://api.z.ai/api/anthropic` (proxy)
- Model ID: `glm-5.1` (via proxy, NOT a standard Claude model)

### Python dependencies
```
datasets    — HuggingFace dataset loading (installed)
anthropic   — API client (installed)
rdflib      — TTL parsing for content coverage (installed)
```

### NOT available
- `tau2_bench` — package does NOT exist on PyPI (`tau2` is an unrelated physics package). Tau2-bench wrapper will raise ImportError at runtime. Skip it.
- `gaia-benchmark/GAIA` — gated dataset on HuggingFace. Requires `huggingface-cli login` first. NOT authenticated currently.

### Binary prerequisites
- `ontomcp` at `~/.ontoskills/bin/ontomcp` — Rust MCP server, rebuild from `mcp/` if outdated
- Compiled TTLs at `~/.ontoskills/packages/` — 840 files (408 skills + sub-skills), 11 author packages

## Architecture

```
benchmark/
├── run.py                  # Main orchestrator (CLI entry point)
├── content_coverage.py     # Parser coverage + knowledge yield (no API calls)
├── config.py               # Model pricing, benchmark definitions
├── agents/
│   ├── base.py             # BaseAgent with Anthropic API, run-loop, retry
│   ├── traditional.py      # Stuffs ALL SKILL.md into system prompt (no tools)
│   └── ontoskills.py       # 4 MCP tools (search, get_skill_context, etc.)
├── wrappers/
│   ├── gaia.py             # GAIA: Q&A with file attachments
│   ├── swebench.py         # SWE-bench: repo checkout + diff patch generation
│   └── tau2bench.py        # Tau2: will fail at runtime (no package)
├── reporting/
│   ├── metrics.py          # compute_comparison()
│   └── comparison.py       # generate_comparison_report()
├── mcp_client/
│   └── client.py           # JSON-RPC MCP client for ontomcp subprocess
├── data/                   # Downloaded datasets (currently empty)
└── results/                # Benchmark output (JSON + comparison.md)
```

## Running benchmarks

### Content coverage (instant, no API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/content_coverage.py --verbose --ttl-dir ~/.ontoskills/packages --json benchmark/results/content_coverage.json
```

### SWE-bench (requires API)
```bash
ANTHROPIC_API_KEY="$ANTHROPIC_AUTH_TOKEN" \
python benchmark/run.py --benchmark swebench --mode both --max-tasks 10 --model glm-5.1 \
  --skills-dir .agents/skills --output-dir benchmark/results -v
```

### GAIA (requires HF auth — currently broken)
```bash
huggingface-cli login  # must do this first
python benchmark/run.py --benchmark gaia --mode both --model glm-5.1 ...
```

## Known issues

### Traditional agent context overflow
The traditional agent concatenates ALL SKILL.md files into one system prompt. With 408 skills this exceeds 200k tokens, causing:
- Empty answers, 0 input/output tokens
- The model can't respond meaningfully

**Fix**: Use `--skills-dir` pointing to a subset of skills (1-10), not the full `.agents/skills/` directory. Or create a per-package benchmark mode.

### SWE-bench wrapper: custom run-loop required
The SWE-bench wrapper patches `agent.run_turn` to intercept file_read/file_edit. It does NOT use `BaseAgent.run()` — it has a custom loop because `BaseAgent.run()` double-appends messages when `run_turn` also appends. See `swebench.py:run_task()` for the custom loop.

### Content coverage: core.ttl must be loaded
The knowledge yield Level 2 SPARQL uses `rdfs:subClassOf*` property paths to resolve leaf types (e.g., `oc:AntiPattern`) to top-level dimensions (e.g., `oc:NormativeRule`). This requires `core.ttl` loaded in the graph. The file is at `ontoskills/core.ttl` in the project root, NOT in `~/.ontoskills/packages/`.

### `trust_remote_code` deprecation
HuggingFace datasets no longer supports `trust_remote_code=True`. The SWE-bench wrapper has been fixed to not pass it. GAIA wrapper still passes it — will get a warning but works.

## Per-package benchmark (TODO)

User wants realistic benchmarks where agents load 1-5 skills per task, not all 400+. Priority packages:
- **superpowers** (obra, 14 skills) — TDD, debugging, planning, git worktrees
- **claude-office-skills** (anthropics subset) — xlsx, pptx, pdf, docx manipulation

Implementation needed:
- New wrapper or mode that selects relevant skills per task
- Traditional agent loads only matching SKILL.md files
- OntoSkills agent uses MCP search (already works this way)

## Test verification

Run before any changes:
```bash
cd /home/marcello/Documenti/onto/ontoskills/core
python -m pytest tests/ -q
```

Run smoke test after compilation:
```bash
python benchmark/smoketest.py
```

## Current benchmark results (2026-04-24)

- Content coverage: 100% parser, 5298 epistemic + 1581 operational nodes across 840 skills
- SWE-bench (5 tasks, ontoskills only): 14.8 avg tool calls, 4/5 patches generated, ~$0.34/task (Sonnet pricing)
- Traditional agent: broken with full skill set (context overflow)
