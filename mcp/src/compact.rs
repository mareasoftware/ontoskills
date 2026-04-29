use crate::catalog::{ExecutionPlanEvaluation, KnowledgeNodeInfo, SkillContextResult};
use serde_json::Value;

/// Priority ordering for knowledge node kinds.
/// Lower = shown first. Matches the Python agent's _compact_context.
fn kind_priority(kind: &str) -> u8 {
    match kind {
        "procedure" => 0,
        "constraint" => 1,
        "design_principle" => 2,
        "heuristic" => 3,
        "anti_pattern" => 4,
        "recovery_tactic" => 5,
        "best_practice" => 6,
        "rule" => 7,
        _ => 99,
    }
}

/// Format a kind string for display: replace underscores with spaces, uppercase.
fn fmt_kind(kind: &str) -> String {
    kind.replace('_', " ").to_uppercase()
}

/// Compact a search result (JSON Value) into token-efficient text.
/// Handles BM25, semantic, structured, and alias modes.
pub fn compact_search(data: &Value) -> String {
    let mut lines: Vec<String> = Vec::new();
    let mode = data.get("mode").and_then(Value::as_str).unwrap_or("");
    lines.push(format!("Search mode: {}", mode));

    // BM25 results
    if let Some(results) = data.get("results").and_then(Value::as_array) {
        for r in results.iter().take(5) {
            let sid = r.get("skill_id").and_then(Value::as_str).unwrap_or("");
            let intents: Vec<&str> = r
                .get("intents")
                .and_then(Value::as_array)
                .map(|arr| arr.iter().filter_map(Value::as_str).take(2).collect())
                .unwrap_or_default();
            let tier = r.get("trust_tier").and_then(Value::as_str).unwrap_or("");
            lines.push(format!("- {} [{}]: {}", sid, tier, intents.join("; ")));
        }
    }

    // Semantic matches
    if let Some(matches) = data.get("matches").and_then(Value::as_array) {
        for m in matches.iter().take(3) {
            let intent = m.get("intent").and_then(Value::as_str).unwrap_or("");
            let score = m.get("score").and_then(Value::as_f64).unwrap_or(0.0);
            let skills: Vec<&str> = m
                .get("skills")
                .and_then(Value::as_array)
                .map(|arr| arr.iter().filter_map(Value::as_str).take(3).collect())
                .unwrap_or_default();
            lines.push(format!("- {} (score={:.2}): {}", intent, score, skills.join(", ")));
        }
    }

    // Structured results (not for alias/bm25 which use different keys)
    if mode != "alias" && mode != "bm25" {
        if let Some(skills) = data.get("skills").and_then(Value::as_array) {
            for s in skills.iter().take(5) {
                let sid = s.get("id").and_then(Value::as_str).unwrap_or("");
                let nature = s.get("nature").and_then(Value::as_str).unwrap_or("");
                lines.push(format!("- {} ({})", sid, nature));
            }
        }
    }

    // Alias results
    if mode == "alias" {
        if let Some(skills) = data.get("skills").and_then(Value::as_array) {
            for s in skills.iter().take(5) {
                let sid = s.get("id").or_else(|| s.get("skill_id")).and_then(Value::as_str).unwrap_or("");
                let tier = s.get("trust_tier").and_then(Value::as_str).unwrap_or("");
                lines.push(format!("- {} [{}]", sid, tier));
            }
        }
    }

    if lines.len() <= 1 {
        return "No results found.".to_string();
    }

    lines.join("\n")
}

/// Compact a `SkillContextResult` into token-efficient markdown-like text.
/// This is the most important function — it produces the knowledge the model sees.
pub fn compact_context(skill_id: &str, ctx: &SkillContextResult) -> String {
    compact_context_with_query(skill_id, ctx, None, None, None)
}

/// Compact a `SkillContextResult` with optional BM25-based node filtering.
///
/// When `query` and `node_engine` are provided, only the most relevant knowledge
/// nodes are included (ranked by BM25). Otherwise, all nodes are shown sorted by
/// step_order and kind priority (original behaviour).
pub fn compact_context_with_query(
    skill_id: &str,
    ctx: &SkillContextResult,
    query: Option<&str>,
    node_engine: Option<&crate::bm25_engine::NodeBm25Engine>,
    section_engine: Option<&crate::bm25_engine::SectionBm25Engine>,
) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push(format!("## {}", skill_id));

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

    let nodes = &ctx.knowledge_nodes;
    if !nodes.is_empty() {
        lines.push(String::new());

        let fallback_indices = || -> Vec<usize> {
            let mut indexed: Vec<(usize, i64, u8)> = nodes
                .iter()
                .enumerate()
                .map(|(i, n)| (i, n.step_order.unwrap_or(999), kind_priority(&n.kind)))
                .collect();
            indexed.sort_by_key(|&(_, order, priority)| (order, priority));
            indexed.into_iter().map(|(i, _, _)| i).collect()
        };

        let indices: Vec<usize> = match (query, node_engine) {
            (Some(q), Some(engine)) if !q.is_empty() => {
                let ranked = engine.rank_nodes(q);
                if ranked.is_empty() {
                    fallback_indices()
                } else {
                    ranked.into_iter().map(|(idx, _)| idx).collect()
                }
            }
            _ => fallback_indices(),
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

    // Section tree content: code examples + reference tables only.
    // Paragraphs and bullet lists are NOT included here because their
    // content is already captured by knowledge nodes' directive_content.
    let sections = &ctx.sections;
    if !sections.is_empty() {
        let budget = crate::bm25_engine::SECTION_BUDGET_CHARS;
        let selected_indices: Vec<usize> = match (query, section_engine) {
            (Some(q), Some(engine)) if !q.is_empty() => {
                engine.rank_within_budget(q, sections, budget)
            }
            _ => {
                let mut indices = Vec::new();
                let mut used = 0;
                for (i, s) in sections.iter().enumerate() {
                    if used + s.content.len() > budget {
                        continue;
                    }
                    used += s.content.len();
                    indices.push(i);
                    if used >= budget {
                        break;
                    }
                }
                indices
            }
        };

        if !selected_indices.is_empty() {
            lines.push(String::new());
            lines.push("Examples & Reference Tables:".to_string());

            for idx in &selected_indices {
                let section = &sections[*idx];
                if let Some(title) = &section.section_title {
                    if !title.is_empty() {
                        lines.push(format!("[{}]", title));
                    }
                }

                if section.content_type == "code_example" {
                    let lang = section.language.as_deref().unwrap_or("");
                    lines.push(format!("```{}", lang));
                    for line in section.content.lines() {
                        lines.push(line.to_string());
                    }
                    lines.push("```".to_string());
                } else if section.content_type == "table" {
                    // Table markdown is already formatted, render as-is.
                    for line in section.content.lines() {
                        lines.push(line.to_string());
                    }
                }
            }
        }
    }

    lines.join("\n")
}

/// Compact an `ExecutionPlanEvaluation` into token-efficient text.
pub fn compact_plan(plan: &ExecutionPlanEvaluation) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push(format!(
        "Applicable: {}",
        if plan.applicable { "Yes" } else { "No" }
    ));

    if let Some(rec) = &plan.recommended_skill {
        lines.push(format!("Recommended: {}", rec));
    }

    if !plan.plan_steps.is_empty() {
        lines.push("Plan:".to_string());
        for (i, step) in plan.plan_steps.iter().enumerate() {
            lines.push(format!("  {}. {}: {}", i + 1, step.skill_id, step.purpose));
        }
    }

    if !plan.missing_states.is_empty() {
        lines.push(format!("Missing states: {}", plan.missing_states.join(", ")));
    }

    if !plan.dependency_warnings.is_empty() {
        let warns: Vec<&str> = plan.dependency_warnings.iter().take(3).map(String::as_str).collect();
        lines.push(format!("Warnings: {}", warns.join("; ")));
    }

    lines.join("\n")
}

/// Compact epistemic rules (a list of knowledge nodes) into token-efficient text.
pub fn compact_epistemic_rules(nodes: &[KnowledgeNodeInfo]) -> String {
    let mut lines: Vec<String> = Vec::new();

    for node in nodes {
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
    }

    if lines.is_empty() {
        return "No knowledge nodes found.".to_string();
    }

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalog::{RequirementInfo, SkillDetails, SkillType, PayloadInfo, PlanStep};

    fn make_node(
        kind: &str,
        content: &str,
        severity: Option<&str>,
        rationale: Option<&str>,
        context: Option<&str>,
        step_order: Option<i64>,
    ) -> KnowledgeNodeInfo {
        KnowledgeNodeInfo {
            uri: String::new(),
            label: None,
            kind: kind.to_string(),
            dimension: None,
            directive_content: content.to_string(),
            rationale: rationale.map(String::from),
            applies_to_context: context.map(String::from),
            severity_level: severity.map(String::from),
            source_skill_id: "test-skill".to_string(),
            source_qualified_id: None,
            inherited: false,
            code_language: None,
            step_order,
            template_variables: None,
        }
    }

    #[test]
    fn test_compact_context_basic() {
        let ctx = SkillContextResult {
            skill: SkillDetails {
                id: "xlsx".to_string(),
                qualified_id: "pkg/xlsx".to_string(),
                package_id: "pkg".to_string(),
                trust_tier: "official".to_string(),
                version: None,
                source: None,
                aliases: vec![],
                uri: String::new(),
                skill_type: SkillType::Executable,
                nature: "tool".to_string(),
                genus: Some("file handler".to_string()),
                differentia: Some("creates and edits Excel files".to_string()),
                intents: vec!["create spreadsheet".to_string(), "analyze data".to_string()],
                requirements: vec![RequirementInfo {
                    requirement_type: "pip".to_string(),
                    value: "openpyxl".to_string(),
                    optional: false,
                }],
                depends_on: vec![],
                extends: vec![],
                contradicts: vec![],
                requires_state: vec![],
                yields_state: vec![],
                handles_failure: vec![],
                generated_by: None,
            },
            payload: PayloadInfo {
                skill_id: "xlsx".to_string(),
                available: false,
                executor: None,
                code: None,
                timeout: None,
                safety_notes: vec![],
            },
            knowledge_nodes: vec![
                make_node(
                    "anti_pattern",
                    "NEVER hardcode values",
                    Some("CRITICAL"),
                    Some("Breaks spreadsheet dynamics"),
                    Some("When writing cells"),
                    None,
                ),
                make_node(
                    "constraint",
                    "Always use formulas",
                    Some("HIGH"),
                    None,
                    None,
                    None,
                ),
                make_node(
                    "heuristic",
                    "Check formatting",
                    Some("MEDIUM"),
                    None,
                    None,
                    Some(2),
                ),
            ],
            sections: vec![],
            include_inherited_knowledge: true,
        };

        let result = compact_context("xlsx", &ctx);

        // Check structure
        assert!(result.starts_with("## xlsx"));
        assert!(result.contains("file handler — creates and edits Excel files"));
        assert!(result.contains("Intents: create spreadsheet; analyze data"));
        assert!(result.contains("Requires: openpyxl"));
        assert!(result.contains("ANTI PATTERN (When writing cells) [CRITICAL]:"));
        assert!(result.contains("  NEVER hardcode values"));
        assert!(result.contains("  Why: Breaks spreadsheet dynamics"));
        assert!(result.contains("CONSTRAINT [HIGH]:"));
        assert!(result.contains("HEURISTIC:"));
        // MEDIUM severity should NOT appear in brackets
        assert!(!result.contains("[MEDIUM]"));
    }

    #[test]
    fn test_compact_search_bm25() {
        let data = serde_json::json!({
            "mode": "bm25",
            "query": "excel",
            "results": [
                {
                    "skill_id": "xlsx",
                    "qualified_id": "pkg/xlsx",
                    "score": 0.95,
                    "matched_by": ["excel"],
                    "intents": ["create spreadsheet", "analyze data", "export"],
                    "aliases": [],
                    "trust_tier": "official"
                },
                {
                    "skill_id": "csv-handler",
                    "qualified_id": "pkg/csv",
                    "score": 0.3,
                    "matched_by": ["excel"],
                    "intents": ["read csv"],
                    "aliases": [],
                    "trust_tier": "community"
                }
            ]
        });

        let result = compact_search(&data);
        assert!(result.contains("Search mode: bm25"));
        assert!(result.contains("- xlsx [official]: create spreadsheet; analyze data"));
        assert!(result.contains("- csv-handler [community]: read csv"));
        // Third intent should be truncated
        assert!(!result.contains("export"));
    }

    #[test]
    fn test_compact_plan() {
        let plan = ExecutionPlanEvaluation {
            intent: Some("create spreadsheet".to_string()),
            requested_skill: Some("xlsx".to_string()),
            matching_skills: vec!["xlsx".to_string()],
            recommended_skill: Some("xlsx".to_string()),
            applicable: true,
            current_states: vec![],
            required_states: vec!["data.loaded".to_string()],
            missing_states: vec!["data.loaded".to_string()],
            dependency_warnings: vec!["xlsx requires openpyxl".to_string()],
            conflict_warnings: vec![],
            plan_steps: vec![PlanStep {
                skill_id: "xlsx".to_string(),
                purpose: "Create formatted spreadsheet".to_string(),
                requires_state: vec![],
                yields_state: vec![],
            }],
            reasoning_summary: "xlsx is the best match".to_string(),
        };

        let result = compact_plan(&plan);
        assert!(result.contains("Applicable: Yes"));
        assert!(result.contains("Recommended: xlsx"));
        assert!(result.contains("Plan:"));
        assert!(result.contains("1. xlsx: Create formatted spreadsheet"));
        assert!(result.contains("Missing states: data.loaded"));
        assert!(result.contains("Warnings: xlsx requires openpyxl"));
    }

    #[test]
    fn test_compact_epistemic_rules() {
        let nodes = vec![
            make_node(
                "constraint",
                "Always validate input",
                Some("CRITICAL"),
                Some("Prevents crashes"),
                None,
                None,
            ),
            make_node(
                "best_practice",
                "Use type hints",
                None,
                None,
                Some("When writing Python"),
                None,
            ),
        ];

        let result = compact_epistemic_rules(&nodes);
        assert!(result.contains("CONSTRAINT [CRITICAL]:"));
        assert!(result.contains("  Always validate input"));
        assert!(result.contains("BEST PRACTICE (When writing Python):"));
        assert!(result.contains("  Use type hints"));
    }

    #[test]
    fn test_kind_priority_ordering() {
        assert!(kind_priority("procedure") < kind_priority("constraint"));
        assert!(kind_priority("constraint") < kind_priority("anti_pattern"));
        assert!(kind_priority("anti_pattern") < kind_priority("rule"));
    }

    #[test]
    fn test_empty_nodes() {
        let nodes: Vec<KnowledgeNodeInfo> = vec![];
        let result = compact_epistemic_rules(&nodes);
        assert_eq!(result, "No knowledge nodes found.");
    }

    #[test]
    fn test_skip_empty_directive_content() {
        let nodes = vec![make_node("heuristic", "", None, None, None, None)];
        let result = compact_epistemic_rules(&nodes);
        assert_eq!(result, "No knowledge nodes found.");
    }

    use crate::bm25_engine::NodeBm25Engine;

    #[test]
    fn test_compact_context_with_query_filters_nodes() {
        let nodes = vec![
            make_node("anti_pattern", "Never trust user-provided file paths", Some("CRITICAL"), Some("Prevents path traversal"), Some("file handling"), None),
            make_node("best_practice", "Use connection pooling for database", None, None, Some("database"), None),
            make_node("heuristic", "Check file permissions before writing", Some("HIGH"), None, Some("file handling"), None),
            make_node("heuristic", "Cache repeated API calls", None, None, Some("network"), None),
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
            sections: vec![],
            include_inherited_knowledge: true,
        };

        let engine = NodeBm25Engine::from_nodes("test", &nodes);
        let result = compact_context_with_query("test", &ctx, Some("file path validation"), Some(&engine), None);

        assert!(result.contains("file paths"), "Should contain file path node: {}", result);
        assert!(!result.contains("connection pooling"), "Should NOT contain database node");
        assert!(!result.contains("Cache repeated"), "Should NOT contain network node");
    }

    #[test]
    fn test_compact_context_without_query_returns_all() {
        let nodes = vec![
            make_node("heuristic", "Node A content here", None, None, None, None),
            make_node("constraint", "Node B content here", None, None, None, None),
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
            knowledge_nodes: nodes,
            sections: vec![],
            include_inherited_knowledge: true,
        };

        let result = compact_context_with_query("test", &ctx, None, None, None);
        assert!(result.contains("Node A content here"));
        assert!(result.contains("Node B content here"));
    }
}
