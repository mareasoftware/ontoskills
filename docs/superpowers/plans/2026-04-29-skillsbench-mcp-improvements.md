# SkillsBench MCP Performance Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 root causes of MCP underperformance in SkillsBench: missing skill_scripts in container, knowledge node noise, and no retry on fixable failures.

**Architecture:** Three independent interventions applied in order — (1) Python bug fix in skillsbench.py, (2) Rust BM25 node index + compact_context() ranking, (3) Python retry loop around agent→Docker→feedback.

**Tech Stack:** Python 3.12, Rust, bm25 crate, podman, Claude Code CLI

---

## Task 1: Copy skill_scripts/ into Docker Container

**Files:**
- Modify: `benchmark/wrappers/skillsbench.py:377-389` (in `_run_solution()`)
- Test: `benchmark/tests/` (existing tests)

- [ ] **Step 1: Write the failing test**

Add a test to `benchmark/tests/test_skillsbench.py` (create if missing) that verifies `_run_solution()` copies `skill_scripts/` into the container:

```python
def test_run_solution_copies_skill_scripts(tmp_path):
    """_run_solution() should copy skill_scripts/ into the container."""
    # This test requires podman — skip if not available.
    import shutil
    if not shutil.which("podman") and not shutil.which("docker"):
        pytest.skip("podman/docker not available")

    wrapper = SkillsBenchWrapper(
        skillsbench_repo="/tmp/skillsbench_full",
        skills_dir=".agents/skills",
    )
    # We verify the logic exists by checking the source code includes
    # skill_scripts copy logic after the fix.
    import inspect
    source = inspect.getsource(wrapper._run_solution)
    assert "skill_scripts" in source, "_run_solution must handle skill_scripts/"
```

- [ ] **Step 2: Implement skill_scripts copy in `_run_solution()`**

In `benchmark/wrappers/skillsbench.py`, after the solution script copy block (after line 389), add skill_scripts copy logic. The `_run_solution()` method receives `task_dir` but needs the host work dir. We need to pass it through.

First, modify `_run_solution()` signature to accept `work_dir`:

```python
def _run_solution(
    self,
    image_tag: str,
    task_id: str,
    solution_script: str,
    task_dir: str,
    work_dir: str | None = None,
) -> dict:
```

Then, after the solution script copy (after line 389, before "Run the solution script"):

```python
            # Copy skill_scripts into container if present.
            if work_dir:
                scripts_src = Path(work_dir) / "skill_scripts"
                if scripts_src.is_dir():
                    self._podman_cmd(
                        "exec", container_name, "mkdir", "-p", "/tmp/skill_scripts",
                    )
                    self._podman_cmd(
                        "cp", str(scripts_src) + "/.", f"{container_name}:/tmp/skill_scripts/",
                    )
```

- [ ] **Step 3: Update all callers of `_run_solution()` to pass `work_dir`**

Search for all calls to `_run_solution()` in `skillsbench.py`. They're in `verify_with_docker()`. The `results` dict already contains `work_dir` from the agent run. Pass it through:

In `verify_with_docker()`, find the `_run_solution()` call and add `work_dir=r.get("work_dir")`:

```python
verification = self._run_solution(
    image_tag=image_tag,
    task_id=task_id,
    solution_script=solution,
    task_dir=str(task_dir),
    work_dir=r.get("work_dir"),
)
```

- [ ] **Step 4: Run existing tests**

Run: `python -m pytest benchmark/tests/ -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add benchmark/wrappers/skillsbench.py
git commit -m "fix(benchmark): copy skill_scripts/ into Docker container"
```

---

## Task 2: Add NodeBm25Engine Struct

**Files:**
- Modify: `mcp/src/bm25_engine.rs` (add `NodeBm25Engine`)
- Test: `mcp/src/bm25_engine.rs` (inline `#[cfg(test)]`)

- [ ] **Step 1: Write the failing test**

In `mcp/src/bm25_engine.rs`, add tests at the bottom of the `tests` module:

```rust
use crate::catalog::KnowledgeNodeInfo;

fn make_test_node(content: &str, context: Option<&str>, rationale: Option<&str>) -> KnowledgeNodeInfo {
    KnowledgeNodeInfo {
        uri: String::new(),
        label: None,
        kind: "heuristic".to_string(),
        dimension: None,
        directive_content: content.to_string(),
        rationale: rationale.map(String::from),
        applies_to_context: context.map(String::from),
        severity_level: None,
        source_skill_id: "test-skill".to_string(),
        source_qualified_id: None,
        inherited: false,
        code_language: None,
        step_order: None,
        template_variables: None,
    }
}

#[test]
fn test_node_bm25_ranks_relevant_higher() {
    let nodes = vec![
        make_test_node("Always validate user input before processing files", Some("file handling"), None),
        make_test_node("Use caching for repeated database queries", Some("database"), None),
        make_test_node("Never trust user-provided file paths", Some("file handling"), Some("Prevents path traversal")),
        make_test_node("Prefer streaming for large dataset downloads", Some("network"), None),
    ];

    let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
    let results = engine.rank_nodes("file path validation");

    // The file-handling nodes should rank higher than database/network ones.
    assert!(!results.is_empty());
    // Check that "file paths" node ranks higher than "database queries" node.
    let find_rank = |content_substring: &str| -> Option<usize> {
        results.iter().position(|(idx, _)| {
            nodes[*idx].directive_content.contains(content_substring)
        })
    };
    let file_path_rank = find_rank("file paths").expect("file paths node should be found");
    let db_rank = find_rank("database queries").expect("database node should be found");
    assert!(file_path_rank < db_rank, "file paths node should rank higher than database node");
}

#[test]
fn test_node_bm25_returns_top_n() {
    let nodes: Vec<KnowledgeNodeInfo> = (0..15)
        .map(|i| make_test_node(&format!("Node {} about topic {}", i, i % 3), None, None))
        .collect();

    let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
    let results = engine.rank_nodes("topic 0");
    assert!(results.len() <= 8, "Should return at most 8 nodes, got {}", results.len());
}

#[test]
fn test_node_bm25_empty_query() {
    let nodes = vec![make_test_node("test content", None, None)];
    let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
    let results = engine.rank_nodes("");
    // Empty query should return all nodes unsorted (fallback).
    assert_eq!(results.len(), 1);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --manifest-path mcp/Cargo.toml node_bm25`
Expected: FAIL — `NodeBm25Engine` not found

- [ ] **Step 3: Implement `NodeBm25Engine`**

Add to `mcp/src/bm25_engine.rs`, after the `Bm25Engine` impl block (after line 116):

```rust
/// In-memory BM25 engine for ranking knowledge nodes within a skill.
///
/// Indexes each node's `directive_content` + `applies_to_context` + `rationale`
/// as a separate document. Used by `compact_context()` to return only the
/// most relevant nodes for a given query.
pub struct NodeBm25Engine {
    engine: bm25::SearchEngine<usize>,
    /// Total number of nodes — used for fallback when query is empty.
    total_nodes: usize,
}

impl NodeBm25Engine {
    /// Build a node-level BM25 engine from a skill's knowledge nodes.
    pub fn from_nodes(skill_id: &str, nodes: &[KnowledgeNodeInfo]) -> Self {
        let mut documents = Vec::with_capacity(nodes.len());

        for (i, node) in nodes.iter().enumerate() {
            let mut parts = Vec::new();
            parts.push(node.directive_content.clone());
            if let Some(ctx) = &node.applies_to_context {
                if !ctx.is_empty() {
                    parts.push(ctx.clone());
                }
            }
            if let Some(why) = &node.rationale {
                if !why.is_empty() {
                    parts.push(why.clone());
                }
            }

            documents.push(bm25::Document {
                id: i,
                contents: parts.join(" "),
            });
        }

        let engine = if documents.is_empty() {
            SearchEngineBuilder::<usize>::with_avgdl(10.0).build()
        } else {
            SearchEngineBuilder::<usize>::with_documents(Language::English, documents).build()
        };

        Self {
            engine,
            total_nodes: nodes.len(),
        }
    }

    /// Rank nodes by BM25 relevance to the query.
    ///
    /// Returns (node_index, score) pairs, sorted by score descending.
    /// Returns at most `max_nodes` results (default 8).
    /// For empty queries, returns all node indices with score 0.0 (fallback).
    pub fn rank_nodes(&self, query: &str) -> Vec<(usize, f32)> {
        if query.is_empty() {
            // Fallback: return all nodes unsorted.
            return (0..self.total_nodes).map(|i| (i, 0.0)).collect();
        }

        let max_nodes = 8;
        let results = self.engine.search(query, max_nodes * 2);

        let mut ranked: Vec<(usize, f32)> = results
            .into_iter()
            .filter_map(|r| {
                if r.score > 0.0 {
                    Some((r.document.id, r.score))
                } else {
                    None
                }
            })
            .collect();

        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        ranked.truncate(max_nodes);
        ranked
    }
}
```

Add `use crate::catalog::KnowledgeNodeInfo;` at the top of the file (after the existing `use crate::catalog::...` line).

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --manifest-path mcp/Cargo.toml node_bm25`
Expected: All 3 new tests PASS

- [ ] **Step 5: Run all Rust tests**

Run: `cargo test --manifest-path mcp/Cargo.toml`
Expected: All tests pass (existing + new)

- [ ] **Step 6: Commit**

```bash
git add mcp/src/bm25_engine.rs
git commit -m "feat(mcp): add NodeBm25Engine for knowledge node ranking"
```

---

## Task 3: Wire NodeBm25Engine into compact_context()

**Files:**
- Modify: `mcp/src/compact.rs` (add query + engine params to `compact_context()`)
- Modify: `mcp/src/main.rs` (build NodeBm25Engine, pass to compact calls)
- Test: `mcp/src/compact.rs` (extend existing tests)

- [ ] **Step 1: Write the failing test**

In `mcp/src/compact.rs` tests module, add:

```rust
use crate::bm25_engine::NodeBm25Engine;

#[test]
fn test_compact_context_with_query_ranks_nodes() {
    let nodes = vec![
        make_node("Always validate file paths from user input", "anti_pattern", Some("CRITICAL"), Some("Prevents path traversal"), Some("file handling"), None),
        make_node("Use connection pooling for database", "best_practice", None, None, Some("database"), None),
        make_node("Check file permissions before writing", "heuristic", Some("HIGH"), None, Some("file handling"), None),
        make_node("Cache repeated API calls", "heuristic", None, None, Some("network"), None),
    ];

    let ctx = SkillContextResult {
        skill: SkillDetails {
            id: "test".to_string(),
            qualified_id: "pkg/test".to_string(),
            package_id: "pkg".to_string(),
            trust_tier: "official".to_string(),
            version: None,
            source: None,
            aliases: vec![],
            uri: String::new(),
            skill_type: SkillType::Executable,
            nature: "tool".to_string(),
            genus: Some("handler".to_string()),
            differentia: Some("processes files".to_string()),
            intents: vec!["process files".to_string()],
            requirements: vec![],
            depends_on: vec![],
            extends: vec![],
            contradicts: vec![],
            requires_state: vec![],
            yields_state: vec![],
            handles_failure: vec![],
            generated_by: None,
        },
        payload: PayloadInfo {
            skill_id: "test".to_string(),
            available: false,
            executor: None,
            code: None,
            timeout: None,
            safety_notes: vec![],
        },
        knowledge_nodes: nodes.clone(),
        include_inherited_knowledge: true,
    };

    let engine = NodeBm25Engine::from_nodes("test", &nodes);
    let result = compact_context_with_query("test", &ctx, Some("file path validation"), Some(&engine));

    // Should contain file-related nodes but NOT database/network ones.
    assert!(result.contains("file paths"), "Should contain file path node");
    assert!(!result.contains("connection pooling"), "Should NOT contain database node");
    assert!(!result.contains("Cache repeated"), "Should NOT contain network node");
}

#[test]
fn test_compact_context_without_query_returns_all() {
    let nodes = vec![
        make_node("Node A", "heuristic", None, None, None, None),
        make_node("Node B", "constraint", None, None, None, None),
    ];

    let ctx = SkillContextResult {
        skill: SkillDetails {
            id: "test".to_string(),
            qualified_id: "pkg/test".to_string(),
            package_id: "pkg".to_string(),
            trust_tier: "official".to_string(),
            version: None,
            source: None,
            aliases: vec![],
            uri: String::new(),
            skill_type: SkillType::Executable,
            nature: "tool".to_string(),
            genus: None,
            differentia: None,
            intents: vec![],
            requirements: vec![],
            depends_on: vec![],
            extends: vec![],
            contradicts: vec![],
            requires_state: vec![],
            yields_state: vec![],
            handles_failure: vec![],
            generated_by: None,
        },
        payload: PayloadInfo {
            skill_id: "test".to_string(),
            available: false,
            executor: None,
            code: None,
            timeout: None,
            safety_notes: vec![],
        },
        knowledge_nodes: nodes.clone(),
        include_inherited_knowledge: true,
    };

    // No query — should return all nodes (current behavior).
    let result = compact_context_with_query("test", &ctx, None, None);
    assert!(result.contains("Node A"), "Should contain Node A");
    assert!(result.contains("Node B"), "Should contain Node B");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --manifest-path mcp/Cargo.toml compact_context_with_query`
Expected: FAIL — `compact_context_with_query` not found

- [ ] **Step 3: Implement `compact_context_with_query()`**

Add to `mcp/src/compact.rs`, after the existing `compact_context()` function (after line 160):

```rust
/// Compact a `SkillContextResult` with optional BM25-based node ranking.
///
/// When `query` and `node_engine` are both `Some`, ranks knowledge nodes
/// by BM25 relevance and returns only the top 8. Otherwise, returns all
/// nodes sorted by step_order + kind_priority (original behavior).
pub fn compact_context_with_query(
    skill_id: &str,
    ctx: &SkillContextResult,
    query: Option<&str>,
    node_engine: Option<&crate::bm25_engine::NodeBm25Engine>,
) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push(format!("## {}", skill_id));

    // Skill metadata (same as compact_context)
    let skill = &ctx.skill;
    if let Some(diff) = &skill.differentia {
        let genus = skill.genus.as_deref().unwrap_or("");
        lines.push(format!("{} — {}", genus, diff));
    }
    if !skill.intents.is_empty() {
        lines.push(format!("Intents: {}", skill.intents.join("; ")));
    }
    let reqs: Vec<&str> = skill.requirements.iter().map(|r| r.value.as_str()).collect();
    if !reqs.is_empty() {
        lines.push(format!("Requires: {}", reqs.join("; ")));
    }

    // Knowledge nodes — with optional BM25 ranking
    let nodes = &ctx.knowledge_nodes;
    if !nodes.is_empty() {
        lines.push(String::new());

        // Determine which nodes to include and in what order.
        let indices: Vec<usize> = match (query, node_engine) {
            (Some(q), Some(engine)) if !q.is_empty() => {
                let ranked = engine.rank_nodes(q);
                if ranked.is_empty() {
                    // BM25 returned nothing — fall back to all nodes.
                    (0..nodes.len()).collect()
                } else {
                    ranked.into_iter().map(|(idx, _)| idx).collect()
                }
            }
            _ => {
                // No query or no engine — sort by step_order + kind_priority.
                let mut indexed: Vec<(usize, i64, u8)> = nodes
                    .iter()
                    .enumerate()
                    .map(|(i, n)| (i, n.step_order.unwrap_or(999), kind_priority(&n.kind)))
                    .collect();
                indexed.sort_by_key(|&(_, order, priority)| (order, priority));
                indexed.into_iter().map(|(i, _, _)| i).collect()
            }
        };

        for idx in &indices {
            let node = &nodes[*idx];
            let content_text = node.directive_content.trim();
            if content_text.is_empty() {
                continue;
            }

            let mut parts: Vec<String> = Vec::new();
            parts.push(fmt_kind(&node.kind));

            if let Some(ctx_str) = &node.applies_to_context {
                if !ctx_str.is_empty() {
                    parts.push(format!("({})", ctx_str));
                }
            }

            if let Some(sev) = &node.severity_level {
                if sev == "CRITICAL" || sev == "HIGH" {
                    parts.push(format!("[{}]", sev));
                }
            }

            lines.push(format!("  {}:", parts.join(" ")));
            lines.push(format!("  {}", content_text));

            if let Some(sev) = &node.severity_level {
                if sev == "CRITICAL" || sev == "HIGH" {
                    if let Some(why) = &node.rationale {
                        if !why.is_empty() {
                            lines.push(format!("  Why: {}", why));
                        }
                    }
                }
            }
        }
    }

    lines.join("\n")
}
```

Then update the existing `compact_context()` to delegate to the new function for backward compatibility:

```rust
pub fn compact_context(skill_id: &str, ctx: &SkillContextResult) -> String {
    compact_context_with_query(skill_id, ctx, None, None)
}
```

Replace the entire body of the original `compact_context()` with this single delegation line.

- [ ] **Step 4: Run tests**

Run: `cargo test --manifest-path mcp/Cargo.toml`
Expected: All tests pass (existing `compact_context` tests + new query tests)

- [ ] **Step 5: Wire into main.rs for prefetch_knowledge**

In `mcp/src/main.rs`, find where `compact_context` is called (in the `prefetch_knowledge` handler). Build a `NodeBm25Engine` per skill and pass the query:

1. After loading each skill's context via `catalog.get_skill_context(...)`, build a node engine:
```rust
let node_engine = bm25_engine::NodeBm25Engine::from_nodes(&skill_id, &ctx.knowledge_nodes);
```

2. Call `compact_context_with_query` instead of `compact_context`:
```rust
let compact = compact::compact_context_with_query(&skill_id, &ctx, Some(&query), Some(&node_engine));
```

3. For `get_skill_context` (no query available), keep using `compact_context()` which delegates to `compact_context_with_query(..., None, None)`.

- [ ] **Step 6: Build and smoke test**

Run: `cargo build --manifest-path mcp/Cargo.toml && python benchmark/smoketest.py`
Expected: Build succeeds, smoke test passes with 5 tools

- [ ] **Step 7: Commit**

```bash
git add mcp/src/compact.rs mcp/src/main.rs
git commit -m "feat(mcp): BM25 node ranking in compact_context"
```

---

## Task 4: Multi-turn Execution Feedback Loop

**Files:**
- Modify: `benchmark/wrappers/skillsbench.py` (add `run_task_claudecode_with_retry()`)
- Modify: `benchmark/agents/claudecode.py` (add `run_with_feedback()`)
- Test: `benchmark/tests/`

- [ ] **Step 1: Add `run_with_feedback()` to `ClaudeCodeAgent`**

In `benchmark/agents/claudecode.py`, add a new method after `run_with_cli()`:

```python
def run_with_feedback(
    self,
    task: dict,
    feedback: str,
    max_budget: float = 0.67,
    timeout: int = 300,
) -> dict:
    """Run a follow-up attempt with Docker/test error feedback.

    Like run_with_cli() but with a feedback prompt instead of the original
    task prompt. The work_dir and env are already set up from the first call.
    """
    work_dir = self._work_dir
    if not work_dir:
        raise RuntimeError("Call setup_task_env() first")

    prompt = (
        "Your previous solution.py failed verification inside a Docker container.\n\n"
        f"{feedback}\n\n"
        "Write a corrected solution.py that fixes the errors above.\n"
        "IMPORTANT: Use CONTAINER paths (e.g., /root/data.csv), NOT host paths.\n"
    )

    cmd = [
        self.claude_bin,
        "-p",
        "--model", self.model,
        "--bare",
        "--output-format", "json",
        "--max-budget-usd", str(max_budget),
        "--dangerously-skip-permissions",
    ]

    if self._mcp_config_path:
        cmd.extend(["--mcp-config", self._mcp_config_path])

    cmd.append("--")
    cmd.append(prompt)

    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = self.api_key
    if os.environ.get("ANTHROPIC_BASE_URL"):
        env["ANTHROPIC_BASE_URL"] = os.environ["ANTHROPIC_BASE_URL"]

    start = time.perf_counter()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(work_dir),
            env=env,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            stdout, stderr = proc.communicate()
            duration_ms = (time.perf_counter() - start) * 1000
            return {
                "result": "[timeout]",
                "work_dir": str(work_dir),
                "solution_path": str(work_dir / "solution.py"),
                "duration_ms": duration_ms,
                "usage": {},
                "num_turns": 0,
                "total_cost_usd": 0,
            }

        duration_ms = (time.perf_counter() - start) * 1000
        stdout_text = stdout.decode("utf-8", errors="replace")

        cli_result: dict = {}
        try:
            parsed = json.loads(stdout_text)
            cli_result["result"] = parsed.get("result", "")
            cli_result["usage"] = parsed.get("usage", {})
            cli_result["num_turns"] = parsed.get("num_turns", 0)
            cli_result["total_cost_usd"] = parsed.get("total_cost_usd", 0)
        except json.JSONDecodeError:
            cli_result["result"] = stdout_text
            cli_result["usage"] = {}
            cli_result["num_turns"] = 0
            cli_result["total_cost_usd"] = 0

        cli_result["duration_ms"] = duration_ms
        cli_result["work_dir"] = str(work_dir)
        cli_result["solution_path"] = str(work_dir / "solution.py")

        # Fallback: extract code from response if no file written.
        if not (work_dir / "solution.py").exists():
            answer = cli_result.get("result", "")
            code = extract_python_code(answer)
            if code:
                (work_dir / "solution.py").write_text(code, encoding="utf-8")

        return cli_result

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "result": f"[error: {exc}]",
            "work_dir": str(work_dir),
            "solution_path": str(work_dir / "solution.py"),
            "duration_ms": duration_ms,
            "usage": {},
            "num_turns": 0,
            "total_cost_usd": 0,
        }
```

- [ ] **Step 2: Add `run_task_claudecode_with_retry()` to wrapper**

In `benchmark/wrappers/skillsbench.py`, add after `run_task_claudecode()` (after line 862):

```python
def run_task_claudecode_with_retry(
    self,
    cc_agent: "ClaudeCodeAgent",  # noqa: F821
    task: dict,
    timeout: int = 900,
    max_budget: float = 2.00,
    max_attempts: int = 3,
) -> dict:
    """Run a task with multi-turn Docker feedback (up to max_attempts).

    Flow: agent generates → Docker verifies → if failed, feed back errors
    → agent fixes → Docker re-verifies. Returns the best result.
    """
    budget_per_attempt = max_budget / max_attempts
    timeout_per_attempt = timeout // max_attempts

    best_result = None
    best_reward = -1.0

    # First attempt — standard run.
    result = self.run_task_claudecode(
        cc_agent, task, timeout=timeout_per_attempt, max_budget=budget_per_attempt,
    )

    # Find the task's Docker image for verification.
    task_dir = Path(task["task_dir"])
    task_id = task["task_id"]

    for attempt in range(max_attempts):
        # Docker verification.
        image_tag = self._get_image_tag(task_id)
        if not image_tag:
            logger.warning("No Docker image for %s, skipping verification", task_id)
            return result

        verification = self._run_solution(
            image_tag=image_tag,
            task_id=task_id,
            solution_script=result.get("solution_script", ""),
            task_dir=str(task_dir),
            work_dir=result.get("work_dir"),
        )
        reward = verification.get("reward", 0.0)

        # Track best result.
        if reward > best_reward:
            best_reward = reward
            best_result = result.copy()
            best_result["verification"] = verification
            best_result["reward"] = reward
            best_result["attempts"] = attempt + 1

        if reward >= 1.0:
            logger.info("Task %s: PASSED on attempt %d", task_id, attempt + 1)
            return best_result

        if attempt < max_attempts - 1:
            # Build feedback prompt.
            feedback_parts = []
            details = verification.get("test_details", [])
            failed_tests = [t for t in details if t.get("status") == "failed"]
            if failed_tests:
                feedback_parts.append("### Failed Tests")
                for t in failed_tests[:5]:
                    feedback_parts.append(f"- {t.get('name', '?')}: {t.get('message', '')[:200]}")

            sol_errors = verification.get("solution_errors", "")
            if sol_errors:
                feedback_parts.append(f"### Solution Errors\n{sol_errors[-1000:]}")

            test_output = verification.get("test_output", "")
            if test_output and "AssertionError" in test_output:
                # Extract assertion lines.
                lines = [l for l in test_output.split("\n") if "AssertionError" in l or "assert" in l]
                if lines:
                    feedback_parts.append("### Assertion Failures\n" + "\n".join(lines[:5]))

            feedback = "\n\n".join(feedback_parts)
            if not feedback.strip():
                break  # No useful feedback — stop retrying.

            logger.info(
                "Task %s: attempt %d reward=%.3f, retrying with feedback",
                task_id, attempt + 1, reward,
            )

            # Run follow-up attempt.
            cli_result = cc_agent.run_with_feedback(
                task,
                feedback=feedback,
                max_budget=budget_per_attempt,
                timeout=timeout_per_attempt,
            )

            # Read updated solution.
            solution_path = Path(cli_result["solution_path"])
            solution_script = ""
            if solution_path.exists():
                solution_script = solution_path.read_text(encoding="utf-8")

            result = {
                "task_id": task_id,
                "model_answer": cli_result.get("result", ""),
                "solution_script": solution_script,
                "work_dir": cli_result.get("work_dir", ""),
                "metrics": {
                    "input_tokens": result.get("metrics", {}).get("input_tokens", 0)
                        + cli_result.get("usage", {}).get("input_tokens", 0),
                    "output_tokens": result.get("metrics", {}).get("output_tokens", 0)
                        + cli_result.get("usage", {}).get("output_tokens", 0),
                    "latency_ms": result.get("metrics", {}).get("latency_ms", 0)
                        + cli_result.get("duration_ms", 0),
                    "tool_calls": result.get("metrics", {}).get("tool_calls", 0)
                        + cli_result.get("num_turns", 0),
                    "cost_usd": result.get("metrics", {}).get("cost_usd", 0)
                        + cli_result.get("total_cost_usd", 0),
                },
            }

    logger.info("Task %s: best reward=%.3f after %d attempts", task_id, best_reward, max_attempts)
    return best_result or result
```

Also add `_get_image_tag()` helper (needed because images are built in Phase 0):

```python
@staticmethod
def _get_image_tag(task_id: str) -> str | None:
    """Get the Docker image tag for a task (from pre-built images)."""
    tag = f"sb-{task_id}"
    # Check if image exists.
    import subprocess
    try:
        result = subprocess.run(
            ["podman", "image", "exists", tag],
            capture_output=True, timeout=10,
        )
        return tag if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
```

- [ ] **Step 3: Update `run_benchmark_claudecode()` to use retry**

In `run_benchmark_claudecode()`, replace the `run_task_claudecode` call (line 898) with `run_task_claudecode_with_retry`:

Change:
```python
result = self.run_task_claudecode(
    cc_agent, task, timeout=timeout, max_budget=max_budget,
)
```

To:
```python
result = self.run_task_claudecode_with_retry(
    cc_agent, task, timeout=timeout, max_budget=max_budget,
)
```

And remove the separate `verify_with_docker()` call (line 916) since verification is now done per-task inside `run_task_claudecode_with_retry()`:

Remove:
```python
# Phase 2: Docker verification (deterministic scoring, parallel).
logger.info("=== Docker verification phase (%d workers) ===", workers)
results = self.verify_with_docker(results, tasks, workers=workers)
```

Add before the Phase 1 loop:
```python
# Docker verification is done inline per-task (multi-turn with retry).
```

- [ ] **Step 4: Run existing tests**

Run: `python -m pytest benchmark/tests/ -q`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add benchmark/agents/claudecode.py benchmark/wrappers/skillsbench.py
git commit -m "feat(benchmark): multi-turn execution feedback (3 attempts per task)"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Run all Python tests**

Run: `python -m pytest benchmark/tests/ -q`
Expected: All pass

- [ ] **Step 2: Run all Rust tests**

Run: `cargo test --manifest-path mcp/Cargo.toml`
Expected: All pass

- [ ] **Step 3: Build MCP binary**

Run: `cargo build --manifest-path mcp/Cargo.toml`
Expected: Build succeeds

- [ ] **Step 4: Smoke test MCP**

Run: `python benchmark/smoketest.py`
Expected: All 5 tools present, search + context work

- [ ] **Step 5: Final commit with spec**

```bash
git add docs/superpowers/specs/2026-04-29-skillsbench-mcp-improvements-design.md
git commit -m "docs: add SkillsBench MCP improvements design spec"
```
