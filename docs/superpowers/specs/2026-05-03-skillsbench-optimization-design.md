# SkillsBench Benchmark Optimization

**Date**: 2026-05-03
**Status**: Design approved
**Branch**: `feat/mcp-benchmark-improvements`

## Overview

Three optimizations to the SkillsBench benchmark system:

1. **Resume per-attempt** — Stop and restart benchmarks without losing completed work
2. **Task overlap (pipelining)** — Run multiple tasks in parallel via a worker pool
3. **MCP via ACP** — Mount ontomcp inside the container so MCP mode is also 100% SkillsBench-aligned

All three are independent features that compose together.

## 1. Resume per-attempt

### State file

`benchmark_state.json` in the output directory. Written after every single attempt (not after task completion).

```json
{
  "run_id": "acp-hints-2026-05-03",
  "mode": "acp",
  "skill_hints": true,
  "max_tasks": 25,
  "seed": 42,
  "shuffle": true,
  "total_tasks": 25,
  "started_at": "2026-05-03T18:00:00",
  "tasks": {
    "earthquake-plate-calculation": {
      "status": "completed",
      "best_reward": 1.0,
      "best_result": {"reward": 1.0, "rewards": {...}, "n_tool_calls": 6, ...},
      "attempts_completed": 2,
      "max_attempts": 5,
      "attempts": [
        {"attempt": 1, "reward": 0.0, "duration_ms": 180000},
        {"attempt": 2, "reward": 1.0, "duration_ms": 150000}
      ]
    },
    "sales-pivot-analysis": {
      "status": "in_progress",
      "best_reward": 0.0,
      "best_result": {...},
      "attempts_completed": 2,
      "max_attempts": 5,
      "attempts": [
        {"attempt": 1, "reward": 0.0, "duration_ms": 200000},
        {"attempt": 2, "reward": 0.0, "duration_ms": 190000}
      ]
    }
  }
}
```

### Resume logic

On startup, if `benchmark_state.json` exists:
1. Check `run_id` + `mode` + `skill_hints` match — if not, start fresh
2. Load task list with same `seed` + `shuffle` + `max_tasks` for deterministic order
3. For each task in the list:
   - Not in state → run from attempt 1
   - `status == "completed"` or `best_reward >= 1.0` → skip entirely
   - `status == "in_progress"` → resume from `attempts_completed + 1`, keeping previous attempt results
4. After all tasks, produce final results from accumulated state

### State file API

```python
class BenchmarkState:
    def __init__(self, path: Path, run_id: str, mode: str, skill_hints: bool): ...

    @classmethod
    def load_or_create(cls, path, run_id, mode, skill_hints, ...) -> "BenchmarkState": ...

    def should_run(self, task_id: str) -> bool:
        """True if this task needs more attempts."""

    def next_attempt(self, task_id: str) -> int:
        """Next attempt number for this task (1-based)."""

    def previous_attempts(self, task_id: str) -> list[dict]:
        """Results from previous attempts for this task."""

    def record_attempt(self, task_id: str, result: dict) -> None:
        """Record a completed attempt. Writes state to disk immediately."""

    def mark_completed(self, task_id: str) -> None:
        """Mark task as fully completed (passed or max attempts exhausted)."""

    def is_fully_done(self) -> bool:
        """All tasks completed."""

    def get_results(self) -> list[dict]:
        """Best result per task, for final scoring."""
```

### Integration points

- `run_benchmark_acp()` — before each task, check `state.should_run()`. After each attempt, `state.record_attempt()`.
- `run_benchmark_claudecode()` — same pattern.
- CLI flag: `--resume` (default: auto-detect from existing state file). `--force-restart` to ignore state.
- `--state-file` to specify custom state path (default: `{output_dir}/benchmark_state.json`).

## 2. Task overlap (worker pool)

### Architecture

A pool of N async workers, each running an independent ACP Trial. Workers pick the next available task from a shared queue.

```
Worker 1: [task 1 trial.run()] → [task 3 trial.run()] → [task 5 ...]
Worker 2: [task 2 trial.run()] → [task 4 trial.run()] → [task 6 ...]
           ↕ parallel            ↕ parallel
```

Each worker:
1. Takes next task from queue
2. Runs full `trial.run()` (build → agent → verify → cleanup)
3. Records result via `BenchmarkState.record_attempt()`
4. If reward < 1.0 and more attempts available, puts task back in queue for retry
5. Takes next task

### Implementation

```python
async def run_benchmark_pooled(
    self,
    *,
    workers: int = 2,
    max_attempts: int = 5,
    state: BenchmarkState,
    trial_runner: Callable,  # _run_acp_trial or _run_acp_mcp_trial
) -> list[dict]:
    """Run benchmark with N parallel workers."""

    # Build task queue: each entry is (task_id, task, attempt_number)
    queue: asyncio.Queue[tuple[str, dict, int]] = asyncio.Queue()
    for task in tasks:
        if state.should_run(task["task_id"]):
            attempt = state.next_attempt(task["task_id"])
            for a in range(attempt, max_attempts + 1):
                # Only enqueue first needed attempt; retries added by workers
                if a == attempt:
                    queue.put_nowait((task["task_id"], task, a))
                    break

    async def worker(worker_id: int):
        while not queue.empty():
            task_id, task, attempt = await queue.get()
            result = await trial_runner(task, ...)
            state.record_attempt(task_id, result)

            if result["reward"] >= 1.0:
                state.mark_completed(task_id)
            elif attempt < max_attempts:
                # Schedule retry
                queue.put_nowait((task_id, task, attempt + 1))
            else:
                state.mark_completed(task_id)  # exhausted attempts

    await asyncio.gather(*[worker(i) for i in range(workers)])
    return state.get_results()
```

### Retry scheduling

Retries use BenchFlow's `RetryConfig.backoff_delay()` — the worker sleeps before putting the task back in the queue. This prevents immediate retries that would compete with other tasks.

### Resource considerations

- Each worker needs its own Docker container (~500MB RAM, 1 CPU)
- Default 2 workers = 2 containers simultaneously
- `--workers N` flag controls parallelism
- API rate limiting: more workers = more concurrent API calls. Start with 2.

### Interaction with resume

Worker pool and resume compose naturally:
- On resume, `BenchmarkState` knows which tasks are done/in-progress
- Workers only pick tasks that `state.should_run()` returns True for
- A previously interrupted task resumes from the correct attempt number

## 3. MCP via ACP

### Approach

Inject ontomcp binary + TTL files + `.mcp_config.json` into the container between `trial.start()` and `trial.install_agent()`. The ACP agent (claude-agent-acp, based on Claude Code) discovers MCP tools via `.mcp_config.json` in its working directory.

### Trial lifecycle (MCP mode)

```
trial.setup()           → build Docker image (with skills injected)
trial.start()           → start container
  ↓ MCP INJECTION ↓
  env.upload_file(ontomcp, "/usr/local/bin/ontomcp")   → binary
  env.exec("chmod +x /usr/local/bin/ontomcp")          → make executable
  env.upload_dir(ttl_dir, "/opt/ontoskills/packages/") → TTL files
  env.upload_file(config, "$WORKDIR/.mcp_config.json") → MCP config
trial.install_agent()   → npm install claude-agent-acp
trial.connect()         → ACP JSON-RPC connect
trial.execute()         → agent runs, discovers MCP tools
trial.verify()          → pytest
trial.cleanup()         → stop container
```

### New method

```python
async def _run_acp_mcp_trial(self, task, *, skill_nudge="name") -> dict:
    """ACP Trial with MCP tools injected into the container."""
    trial = await Trial.create(config)
    try:
        await trial.setup()
        await trial.start()

        # Inject ontomcp + TTL + .mcp_config.json
        await self._inject_mcp_into_container(trial.env, task)

        # Resume normal ACP lifecycle from install_agent onward
        await trial.install_agent()
        await trial.connect()
        await trial.execute()
        result = await trial.verify()
        return result
    finally:
        await trial.cleanup()
```

### _inject_mcp_into_container

```python
async def _inject_mcp_into_container(self, env, task: dict) -> None:
    ontomcp_bin = self.ontomcp_bin  # ~/.ontoskills/bin/ontomcp
    ttl_root = self._prepare_skillsbench_ontology_root()  # /tmp/skillsbench_ontology/

    # Upload binary
    await env.upload_file(ontomcp_bin, "/usr/local/bin/ontomcp")
    await env.exec("chmod +x /usr/local/bin/ontomcp")

    # Upload TTL files (tar + extract for efficiency)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as f:
        subprocess.run(["tar", "czf", f.name, "-C", ttl_root, "."])
        await env.upload_file(f.name, "/tmp/ontoskills_ttl.tar.gz")
    await env.exec("mkdir -p /opt/ontoskills/packages && tar xzf /tmp/ontoskills_ttl.tar.gz -C /opt/ontoskills/packages")

    # Write .mcp_config.json
    mcp_config = json.dumps({
        "mcpServers": {
            "ontoskills": {
                "command": "/usr/local/bin/ontomcp",
                "args": ["--ontology-root", "/opt/ontoskills/packages"],
                "type": "stdio"
            }
        }
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(mcp_config)
        tmp = f.name
    # Upload to WORKDIR (where claude-agent-acp will find it)
    await env.upload_file(tmp, ".mcp_config.json")
    os.unlink(tmp)
```

### MCP prompt (skill nudge)

For MCP mode, the nudge uses the ontoskill tool name:

```
Skills available via ontoskill MCP tool: geospatial-analysis. Load them with ontoskill before starting.
```

This is already implemented in `claudecode.py` — just needs to be passed via `BENCHFLOW_SKILL_NUDGE` env var the same way as traditional mode.

### Harbor API consideration

`trial.env` is a Harbor `DockerEnvironment` with:
- `upload_file(host_path, container_path)` — upload a file
- `exec(command, timeout_sec)` — execute a command in the container

If `upload_dir` doesn't exist, use tar approach (pack directory → upload tar → extract).

## Updated mode dispatch

| Mode | Trial lifecycle | Skill delivery | Agent location |
|------|----------------|----------------|----------------|
| `acp` | `trial.run()` | SKILL.md in Dockerfile | Inside container |
| `acp-mcp` | `trial.run()` split + MCP injection | ontomcp MCP tools | Inside container |
| `claudecode` | Removed (replaced by `acp`) | — | — |
| `claudecode-mcp` | Removed (replaced by `acp-mcp`) | — | — |

CLI modes simplify to: `acp`, `acp-mcp`, `both` (runs both).

## Production benchmark (4 cases)

| Run | Mode | Hints | Tests |
|-----|------|-------|-------|
| 1 | `acp` | Yes | Knowledge quality |
| 2 | `acp-mcp` | Yes | Knowledge quality |
| 3 | `acp` | No | Discovery |
| 4 | `acp-mcp` | No | Discovery |

Run with `--workers 2 --attempts 5 --resume`.

## Files to modify

| File | Changes |
|------|---------|
| `benchmark/wrappers/skillsbench.py` | Add `BenchmarkState`, `_run_acp_mcp_trial()`, `_inject_mcp_into_container()`, `run_benchmark_pooled()`. Remove hybrid mode code. |
| `benchmark/run.py` | Update CLI modes (`acp`, `acp-mcp`, `both`). Add `--resume`, `--force-restart`, `--workers`, `--state-file` flags. |
| `benchmark/agents/claudecode.py` | Remove traditional mode (replaced by ACP). Keep MCP mode for reference. |
| `benchmark/CLAUDE.md` | Update documentation |

## Out of scope

- Attempt overlap (too complex with ACP, requires double containers per task)
- Harbor compose file changes (already patched locally)
- Pipeline visualization / dashboard
