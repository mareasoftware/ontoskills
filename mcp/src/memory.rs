use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::bm25_engine::{MemoryBm25Document, MemoryBm25Engine};
use serde::Serialize;
use serde_json::{Value, json};

const BASE_URI: &str = "https://ontoskills.sh/ontology#";
const MAX_MEMORY_CONTENT_LEN: usize = 8_000;
const DEFAULT_LIMIT: usize = 10;
const MAX_LIMIT: usize = 100;

#[derive(Debug, Clone, Serialize)]
pub struct MemoryRecord {
    pub memory_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    pub memory_type: String,
    pub scope: String,
    pub content: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub applies_to_context: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rationale: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub severity_level: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub confidence: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    pub related_skill_ids: Vec<String>,
    pub related_topic_ids: Vec<String>,
    pub related_memory_ids: Vec<String>,
    pub depends_on_memory_ids: Vec<String>,
    pub supersedes_memory_ids: Vec<String>,
    pub related_intents: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
    pub is_archived: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct MemorySearchResult {
    #[serde(flatten)]
    pub memory: MemoryRecord,
    pub score: f32,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AssociationEdge {
    pub source_memory_id: String,
    pub target_id: String,
    pub relation: String,
}

impl AssociationEdge {
    fn new(source_memory_id: &str, target_id: &str, relation: &str) -> Self {
        Self {
            source_memory_id: source_memory_id.to_string(),
            target_id: target_id.to_string(),
            relation: relation.to_string(),
        }
    }
}

#[derive(Debug, Clone)]
struct AssociationPlan {
    memories: Vec<MemoryRecord>,
    edges: Vec<AssociationEdge>,
    primary_index: usize,
    association: Value,
}

#[derive(Debug, Clone)]
struct QualityGateResult {
    saved_memories: Vec<MemoryRecord>,
    merged_memories: Vec<Value>,
    merged_records: Vec<MemoryRecord>,
    association_quality: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum DedupePolicy {
    Merge,
    Reject,
    Allow,
}

impl DedupePolicy {
    fn as_str(self) -> &'static str {
        match self {
            Self::Merge => "merge",
            Self::Reject => "reject",
            Self::Allow => "allow",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum IsolationPolicy {
    AutoLink,
    Reject,
    Inbox,
}

impl IsolationPolicy {
    fn as_str(self) -> &'static str {
        match self {
            Self::AutoLink => "auto_link",
            Self::Reject => "reject",
            Self::Inbox => "inbox",
        }
    }
}

#[derive(Debug, Clone)]
pub struct MemoryStore {
    root: PathBuf,
    project_id: String,
    records: Vec<MemoryRecord>,
}

impl MemoryStore {
    pub fn from_environment() -> Self {
        let root = env::var_os("ONTOMEMORY_ROOT")
            .map(PathBuf::from)
            .or_else(|| {
                env::var_os("HOME")
                    .map(PathBuf::from)
                    .map(|home| home.join(".ontoskills").join("memories"))
            })
            .unwrap_or_else(|| PathBuf::from(".ontoskills").join("memories"));
        let project_id = env::var("ONTOMEMORY_PROJECT_ID").unwrap_or_else(|_| {
            env::current_dir()
                .ok()
                .and_then(|path| path.canonicalize().ok())
                .map(|path| stable_hash64(&path.display().to_string()))
                .unwrap_or_else(|| "unknown".to_string())
        });
        let fallback_root = root.clone();
        let fallback_project_id = project_id.clone();
        Self::load(root, project_id).unwrap_or_else(|_| Self {
            root: fallback_root,
            project_id: fallback_project_id,
            records: vec![],
        })
    }

    pub fn load(root: PathBuf, project_id: String) -> Result<Self, String> {
        let mut store = Self {
            root,
            project_id,
            records: vec![],
        };
        store.reload()?;
        Ok(store)
    }

    pub fn reload(&mut self) -> Result<(), String> {
        let mut records = Vec::new();
        for path in self.ttl_paths() {
            if path.exists() {
                let content = fs::read_to_string(&path).map_err(|err| {
                    format!("Failed to read memory file {}: {err}", path.display())
                })?;
                records.extend(parse_memories(&content));
            }
        }
        dedupe_memory_records(&mut records);
        self.records = records;
        Ok(())
    }

    pub fn ttl_paths(&self) -> Vec<PathBuf> {
        vec![self.global_path(), self.project_path()]
    }

    pub fn existing_ttl_paths(&self) -> Vec<PathBuf> {
        self.ttl_paths()
            .into_iter()
            .filter(|path| path.exists())
            .collect()
    }

    pub fn graph_records(
        &mut self,
        scope: &str,
        include_archived: bool,
    ) -> Result<Vec<MemoryRecord>, String> {
        validate_read_scope(scope)?;
        self.reload()?;
        let mut selected = self
            .records
            .iter()
            .filter(|record| include_archived || !record.is_archived)
            .filter(|record| scope_matches(scope, &record.scope))
            .cloned()
            .collect::<Vec<_>>();
        let mut selected_ids = selected
            .iter()
            .map(|record| record.memory_id.clone())
            .collect::<HashSet<_>>();
        let mut wanted = selected
            .iter()
            .flat_map(|record| {
                record
                    .depends_on_memory_ids
                    .iter()
                    .chain(record.supersedes_memory_ids.iter())
                    .chain(record.related_memory_ids.iter())
                    .cloned()
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        while let Some(memory_id) = wanted.pop() {
            if selected_ids.contains(&memory_id) {
                continue;
            }
            let Some(record) = self
                .records
                .iter()
                .find(|candidate| candidate.memory_id == memory_id)
                .cloned()
            else {
                continue;
            };
            if !include_archived && record.is_archived {
                continue;
            }
            selected_ids.insert(record.memory_id.clone());
            wanted.extend(record.depends_on_memory_ids.iter().cloned());
            wanted.extend(record.supersedes_memory_ids.iter().cloned());
            wanted.extend(record.related_memory_ids.iter().cloned());
            selected.push(record);
        }
        Ok(selected)
    }

    pub fn handle_action(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let action = required_string(arguments, "action")?;
        let normalized_action = normalize_action(action)?;
        match normalized_action {
            "remember" => self.remember(arguments),
            "associate" => {
                self.reload()?;
                self.associate_action(arguments)
            }
            "search" | "list" => {
                self.reload()?;
                self.search_action(arguments)
            }
            "get" => {
                self.reload()?;
                self.get_action(arguments)
            }
            "update" => self.update(arguments),
            "forget" => self.forget(arguments),
            "link" => self.link(arguments),
            "unlink" => self.unlink(arguments),
            "recluster" => self.recluster(arguments),
            other => Err(format!("Unknown ontomemory action: {other}")),
        }
    }

    pub fn relevant_memories_for_query(
        &mut self,
        query: &str,
        related_skill_ids: &[String],
        limit: usize,
    ) -> Result<Vec<MemorySearchResult>, String> {
        self.reload()?;
        let mut params = MemorySearchParams::default();
        params.query = Some(query.to_string());
        params.scope = "both".to_string();
        params.include_archived = false;
        params.limit = limit;
        let mut results = self.search(params);
        if !related_skill_ids.is_empty() {
            let related: HashSet<&str> = related_skill_ids.iter().map(String::as_str).collect();
            for result in &mut results {
                if result
                    .memory
                    .related_skill_ids
                    .iter()
                    .any(|sid| related.contains(sid.as_str()))
                {
                    result.score += 1.0;
                }
            }
            results.sort_by(|left, right| {
                right
                    .score
                    .partial_cmp(&left.score)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then(right.memory.updated_at.cmp(&left.memory.updated_at))
            });
            results.truncate(limit.min(MAX_LIMIT));
        }
        Ok(results)
    }

    fn remember(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let auto_associate = optional_bool(arguments, "auto_associate").unwrap_or(true);
        let decompose = optional_bool(arguments, "decompose").unwrap_or(true);
        if auto_associate || decompose {
            let plan = self.build_association_plan(arguments, decompose)?;
            let gate = self.apply_quality_gate(plan.memories.clone(), arguments)?;
            let memories = gate.saved_memories.clone();
            let primary = memories
                .get(plan.primary_index)
                .or_else(|| gate.merged_records.first())
                .cloned()
                .ok_or_else(|| "Association produced no memories".to_string())?;
            self.persist_all()?;
            let text = compact_association_result("Remembered", &memories, &plan.edges);
            return Ok(MemoryActionResult::changed(
                json!({
                    "memory": primary,
                    "memories": memories,
                    "edges": plan.edges,
                    "association": plan.association,
                    "merged_memories": gate.merged_memories,
                    "association_quality": gate.association_quality
                }),
                text,
            ));
        }
        let content = validated_content(required_string(arguments, "content")?)?;
        let scope = optional_string(arguments, "scope").unwrap_or_else(|| "project".to_string());
        validate_write_scope(&scope)?;
        let memory_type = normalize_memory_type(
            optional_string(arguments, "memory_type")
                .unwrap_or_else(|| "fact".to_string())
                .as_str(),
        )?;
        let severity_level = optional_string(arguments, "severity_level")
            .map(|value| normalize_severity(&value))
            .transpose()?;
        let confidence = optional_f64(arguments, "confidence")
            .map(validate_confidence)
            .transpose()?;
        let now = now_stamp();
        let memory_id = generate_memory_id(&content, &scope);
        if self
            .records
            .iter()
            .any(|record| record.memory_id == memory_id)
        {
            return Err(format!("Memory already exists: {memory_id}"));
        }

        let mut related_skill_ids = string_list(arguments, "related_skill_ids");
        if let Some(skill_id) = optional_string(arguments, "related_skill_id") {
            related_skill_ids.push(skill_id);
        }
        normalize_id_list(&mut related_skill_ids);

        let mut depends_on = string_list(arguments, "depends_on_memory_ids");
        normalize_id_list(&mut depends_on);
        let mut supersedes = string_list(arguments, "supersedes_memory_ids");
        normalize_id_list(&mut supersedes);
        self.validate_memory_refs(&depends_on, arguments)?;
        self.validate_memory_refs(&supersedes, arguments)?;
        let mut related_intents = string_list(arguments, "related_intents");
        normalize_id_list(&mut related_intents);
        let mut related_topic_ids = string_list(arguments, "related_topic_ids");
        normalize_id_list(&mut related_topic_ids);
        let mut related_memory_ids = string_list(arguments, "related_memory_ids");
        normalize_id_list(&mut related_memory_ids);
        self.validate_memory_refs(&related_memory_ids, arguments)?;

        let record = MemoryRecord {
            memory_id,
            title: optional_nonempty_string(arguments, "title"),
            memory_type,
            scope,
            content,
            applies_to_context: optional_nonempty_string(arguments, "applies_to_context"),
            rationale: optional_nonempty_string(arguments, "rationale"),
            severity_level,
            confidence,
            source: optional_nonempty_string(arguments, "source"),
            related_skill_ids,
            related_topic_ids,
            related_memory_ids,
            depends_on_memory_ids: depends_on,
            supersedes_memory_ids: supersedes,
            related_intents,
            created_at: now.clone(),
            updated_at: now,
            is_archived: false,
        };

        let gate = self.apply_quality_gate(vec![record.clone()], arguments)?;
        self.persist_all()?;
        let record = gate
            .saved_memories
            .first()
            .or_else(|| gate.merged_records.first())
            .cloned()
            .ok_or_else(|| "Memory was neither saved nor merged".to_string())?;
        Ok(MemoryActionResult::changed(
            json!({
                "memory": record,
                "memories": gate.saved_memories,
                "merged_memories": gate.merged_memories,
                "association_quality": gate.association_quality
            }),
            compact_one("Remembered", &record),
        ))
    }

    fn associate_action(&self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let decompose = optional_bool(arguments, "decompose").unwrap_or(true);
        let plan = self.build_association_plan(arguments, decompose)?;
        let primary = plan
            .memories
            .get(plan.primary_index)
            .cloned()
            .ok_or_else(|| "Association produced no memories".to_string())?;
        let text = compact_association_result("Association", &plan.memories, &plan.edges);
        Ok(MemoryActionResult::unchanged(
            json!({
                "memory": primary,
                "memories": plan.memories,
                "edges": plan.edges,
                "association": plan.association
            }),
            text,
        ))
    }

    fn search_action(&self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let mut params = MemorySearchParams::default();
        params.query = normalized_search_query(optional_string(arguments, "query"));
        params.scope = optional_string(arguments, "scope").unwrap_or_else(|| "both".to_string());
        params.memory_type = optional_string(arguments, "memory_type")
            .map(|value| normalize_memory_type(&value))
            .transpose()?;
        params.related_skill_id = optional_string(arguments, "related_skill_id");
        params.applies_to_context = optional_string(arguments, "applies_to_context");
        params.severity_level = optional_string(arguments, "severity_level")
            .map(|value| normalize_severity(&value))
            .transpose()?;
        params.min_confidence = optional_f64(arguments, "min_confidence")
            .map(validate_confidence)
            .transpose()?;
        params.include_archived = optional_bool(arguments, "include_archived").unwrap_or(false);
        params.limit = optional_usize(arguments, "limit")
            .unwrap_or(DEFAULT_LIMIT)
            .min(MAX_LIMIT);
        validate_read_scope(&params.scope)?;

        let results = self.search(params);
        let text = compact_search_results("Memories", &results);
        Ok(MemoryActionResult::unchanged(
            json!({ "memories": results }),
            text,
        ))
    }

    fn get_action(&self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let memory_id = required_string(arguments, "memory_id")?;
        let memory = self
            .find(memory_id)
            .ok_or_else(|| format!("Memory not found: {memory_id}"))?;
        let include_links = optional_bool(arguments, "include_links");
        let include_dependencies = optional_bool(arguments, "include_dependencies")
            .or(include_links)
            .unwrap_or(false);
        let include_superseded = optional_bool(arguments, "include_superseded")
            .or(include_links)
            .unwrap_or(false);
        let mut visible_memory = memory.clone();
        if !include_dependencies {
            visible_memory.depends_on_memory_ids.clear();
        }
        if !include_superseded {
            visible_memory.supersedes_memory_ids.clear();
        }
        let mut related = Vec::new();
        if include_dependencies {
            for dep_id in &memory.depends_on_memory_ids {
                if let Some(dep) = self.find(dep_id) {
                    related.push(dep.clone());
                }
            }
        }
        if include_superseded {
            for old_id in &memory.supersedes_memory_ids {
                if let Some(old) = self.find(old_id) {
                    related.push(old.clone());
                }
            }
        }
        let mut text = compact_one("Memory", &visible_memory);
        if !related.is_empty() {
            text.push_str("\n\nRelated:\n");
            for record in &related {
                text.push_str(&format!(
                    "- {} [{}]: {}\n",
                    record.memory_id, record.memory_type, record.content
                ));
            }
            text.truncate(text.trim_end().len());
        }
        Ok(MemoryActionResult::unchanged(
            json!({ "memory": visible_memory, "related": related }),
            text,
        ))
    }

    fn update(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let memory_id = required_string(arguments, "memory_id")?;
        let Some(index) = self
            .records
            .iter()
            .position(|record| record.memory_id == memory_id)
        else {
            return Err(format!("Memory not found: {memory_id}"));
        };

        if let Some(content) = optional_string(arguments, "content") {
            self.records[index].content = validated_content(&content)?;
        }
        if arguments.get("title").is_some() {
            self.records[index].title = optional_nonempty_string(arguments, "title");
        }
        if let Some(memory_type) = optional_string(arguments, "memory_type") {
            self.records[index].memory_type = normalize_memory_type(&memory_type)?;
        }
        if let Some(scope) = optional_string(arguments, "scope") {
            validate_write_scope(&scope)?;
            self.records[index].scope = scope;
        }
        if arguments.get("applies_to_context").is_some() {
            self.records[index].applies_to_context =
                optional_nonempty_string(arguments, "applies_to_context");
        }
        if arguments.get("rationale").is_some() {
            self.records[index].rationale = optional_nonempty_string(arguments, "rationale");
        }
        if arguments.get("severity_level").is_some() {
            self.records[index].severity_level = optional_string(arguments, "severity_level")
                .map(|severity| normalize_severity(&severity))
                .transpose()?;
        }
        if arguments.get("confidence").is_some() {
            self.records[index].confidence = optional_f64(arguments, "confidence")
                .map(validate_confidence)
                .transpose()?;
        }
        if arguments.get("source").is_some() {
            self.records[index].source = optional_nonempty_string(arguments, "source");
        }
        replace_id_list_if_present(
            arguments,
            "related_skill_ids",
            &mut self.records[index].related_skill_ids,
        );
        replace_id_list_if_present(
            arguments,
            "related_topic_ids",
            &mut self.records[index].related_topic_ids,
        );
        if arguments.get("related_memory_ids").is_some() {
            let values = normalized_list_from(arguments, "related_memory_ids");
            self.validate_memory_refs(&values, arguments)?;
            self.records[index].related_memory_ids = values;
        }
        if arguments.get("depends_on_memory_ids").is_some() {
            let values = normalized_list_from(arguments, "depends_on_memory_ids");
            self.validate_memory_refs(&values, arguments)?;
            self.records[index].depends_on_memory_ids = values;
        }
        if arguments.get("supersedes_memory_ids").is_some() {
            let values = normalized_list_from(arguments, "supersedes_memory_ids");
            self.validate_memory_refs(&values, arguments)?;
            self.records[index].supersedes_memory_ids = values;
        }
        replace_id_list_if_present(
            arguments,
            "related_intents",
            &mut self.records[index].related_intents,
        );
        if let Some(is_archived) = optional_bool(arguments, "is_archived") {
            self.records[index].is_archived = is_archived;
        }
        self.records[index].updated_at = now_stamp();
        let record = self.records[index].clone();
        self.persist_all()?;
        Ok(MemoryActionResult::changed(
            json!({ "memory": record }),
            compact_one("Updated", &record),
        ))
    }

    fn build_association_plan(
        &self,
        arguments: &Value,
        decompose: bool,
    ) -> Result<AssociationPlan, String> {
        let raw_content = validated_content(required_string(arguments, "content")?)?;
        let scope = optional_string(arguments, "scope").unwrap_or_else(|| "project".to_string());
        validate_write_scope(&scope)?;
        let explicit_type = optional_string(arguments, "memory_type")
            .map(|value| normalize_memory_type(&value))
            .transpose()?;
        let explicit_title = optional_nonempty_string(arguments, "title");
        let explicit_context = optional_nonempty_string(arguments, "applies_to_context");
        let explicit_rationale = optional_nonempty_string(arguments, "rationale");
        let explicit_severity = optional_string(arguments, "severity_level")
            .map(|value| normalize_severity(&value))
            .transpose()?;
        let explicit_confidence = optional_f64(arguments, "confidence")
            .map(validate_confidence)
            .transpose()?;
        let explicit_source = optional_nonempty_string(arguments, "source");
        let mut explicit_skill_ids = string_list(arguments, "related_skill_ids");
        if let Some(skill_id) = optional_string(arguments, "related_skill_id") {
            explicit_skill_ids.push(skill_id);
        }
        normalize_id_list(&mut explicit_skill_ids);
        let explicit_depends = normalized_list_from(arguments, "depends_on_memory_ids");
        let explicit_supersedes = normalized_list_from(arguments, "supersedes_memory_ids");
        let explicit_related_memories = normalized_list_from(arguments, "related_memory_ids");
        self.validate_memory_refs(&explicit_depends, arguments)?;
        self.validate_memory_refs(&explicit_supersedes, arguments)?;
        self.validate_memory_refs(&explicit_related_memories, arguments)?;
        let explicit_intents = normalized_list_from(arguments, "related_intents");
        let explicit_topics = normalized_list_from(arguments, "related_topic_ids");
        let now = now_stamp();
        let atoms = if decompose {
            split_atomic_statements(&raw_content)
        } else {
            vec![raw_content.clone()]
        };
        let workflow_intents = if explicit_intents.is_empty() {
            infer_workflow_intents(&atoms)
        } else {
            explicit_intents.clone()
        };
        let workflow_context = explicit_context
            .clone()
            .or_else(|| infer_context(&raw_content, &workflow_intents, &explicit_skill_ids));
        let mut memories = Vec::new();
        for (index, atom) in atoms.iter().enumerate() {
            let inferred_type = explicit_type
                .clone()
                .unwrap_or_else(|| infer_memory_type(atom).to_string());
            let mut related_intents = if explicit_intents.is_empty() {
                infer_related_intents(atom)
            } else {
                explicit_intents.clone()
            };
            for intent in &workflow_intents {
                push_unique(&mut related_intents, intent);
            }
            normalize_id_list(&mut related_intents);
            let mut related_skill_ids = if explicit_skill_ids.is_empty() {
                infer_related_skill_ids(atom)
            } else {
                explicit_skill_ids.clone()
            };
            normalize_id_list(&mut related_skill_ids);
            let confidence = explicit_confidence.or_else(|| Some(infer_confidence(atom)));
            let title = explicit_title
                .clone()
                .filter(|_| index == 0 || atoms.len() == 1)
                .or_else(|| Some(make_title(atom)));
            let record = MemoryRecord {
                memory_id: generate_memory_id(&format!("{index}:{atom}"), &scope),
                title,
                memory_type: inferred_type,
                scope: scope.clone(),
                content: atom.to_string(),
                applies_to_context: workflow_context
                    .clone()
                    .or_else(|| infer_context(atom, &related_intents, &related_skill_ids)),
                rationale: explicit_rationale.clone().or_else(|| {
                    Some("Automatically associated from a remembered compound thought.".to_string())
                }),
                severity_level: explicit_severity.clone(),
                confidence,
                source: explicit_source.clone(),
                related_skill_ids,
                related_topic_ids: explicit_topics.clone(),
                related_memory_ids: if index == 0 {
                    explicit_related_memories.clone()
                } else {
                    vec![]
                },
                depends_on_memory_ids: if index == 0 {
                    explicit_depends.clone()
                } else {
                    vec![]
                },
                supersedes_memory_ids: if index == 0 {
                    explicit_supersedes.clone()
                } else {
                    vec![]
                },
                related_intents,
                created_at: now.clone(),
                updated_at: now.clone(),
                is_archived: optional_bool(arguments, "is_archived").unwrap_or(false),
            };
            memories.push(record);
        }

        let mut edges = Vec::new();
        apply_inferred_memory_edges(&mut memories, &mut edges, &self.records, atoms.len() > 1);
        for memory in &memories {
            for target in &memory.depends_on_memory_ids {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "depends_on_memory",
                ));
            }
            for target in &memory.supersedes_memory_ids {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "supersedes_memory",
                ));
            }
            for target in &memory.related_skill_ids {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "related_to_skill",
                ));
            }
            for target in &memory.related_topic_ids {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "related_to_topic",
                ));
            }
            for target in &memory.related_memory_ids {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "related_to_memory",
                ));
            }
            for target in &memory.related_intents {
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    target,
                    "related_to_intent",
                ));
            }
        }
        dedupe_edges(&mut edges);
        let association = json!({
            "decomposed": memories.len() > 1,
            "primary_memory_id": memories.first().map(|memory| memory.memory_id.clone()),
            "rationale": "Local deterministic decomposition and graph association."
        });
        Ok(AssociationPlan {
            memories,
            edges,
            primary_index: 0,
            association,
        })
    }

    fn apply_quality_gate(
        &mut self,
        incoming: Vec<MemoryRecord>,
        arguments: &Value,
    ) -> Result<QualityGateResult, String> {
        let dedupe_policy = normalize_dedupe_policy(arguments)?;
        let isolation_policy = normalize_isolation_policy(arguments)?;
        let mut saved_memories = Vec::new();
        let mut merged_memories = Vec::new();
        let mut merged_records = Vec::new();
        let mut isolated_before = Vec::new();
        let mut isolated_after = Vec::new();
        let mut fallback_used = Vec::new();
        let mut topic_links = Vec::new();
        let mut topic_assignments = Vec::new();
        let mut cluster_links = Vec::new();
        let mut topic_created = Vec::new();

        for mut memory in incoming {
            if optional_bool(arguments, "auto_link_related").unwrap_or(true) {
                assign_memory_topics(
                    &mut memory,
                    &self.records,
                    &mut topic_assignments,
                    &mut topic_created,
                );
            }
            let was_isolated = is_isolated(&memory);
            if was_isolated {
                isolated_before.push(memory.memory_id.clone());
                apply_isolation_policy(
                    &mut memory,
                    &self.records,
                    isolation_policy,
                    &mut fallback_used,
                )?;
            }
            if is_isolated(&memory) {
                isolated_after.push(memory.memory_id.clone());
            }

            if dedupe_policy != DedupePolicy::Allow {
                if let Some(existing_index) = find_duplicate_index(&self.records, &memory) {
                    if dedupe_policy == DedupePolicy::Reject {
                        return Err(format!(
                            "Duplicate memory detected: {}",
                            self.records[existing_index].memory_id
                        ));
                    }
                    let existing_id = self.records[existing_index].memory_id.clone();
                    merge_memory_record(&mut self.records[existing_index], &memory);
                    let merged = self.records[existing_index].clone();
                    merged_memories.push(json!({
                        "incoming_memory_id": memory.memory_id,
                        "existing_memory_id": existing_id,
                        "action": "merged"
                    }));
                    merged_records.push(merged);
                    continue;
                }
            }

            if optional_bool(arguments, "auto_link_related").unwrap_or(true) {
                let candidates = best_related_memory_matches(&memory, &self.records, 3);
                for (candidate, score) in candidates {
                    push_unique(&mut memory.related_memory_ids, &candidate.memory_id);
                    cluster_links.push(json!({
                        "source_memory_id": memory.memory_id,
                        "target_memory_id": candidate.memory_id,
                        "relation": "related_to_memory",
                        "reason": "shared_topic_cluster",
                        "score": score
                    }));
                    topic_links.push(json!({
                        "source_memory_id": memory.memory_id,
                        "target_memory_id": candidate.memory_id,
                        "relation": "related_to_memory",
                        "reason": "shared_topic_cluster"
                    }));
                }
            }

            self.records.push(memory.clone());
            saved_memories.push(memory);
        }

        let association_quality = json!({
            "isolated_before": isolated_before,
            "isolated_after": isolated_after,
            "fallback_used": fallback_used,
            "topic_links": topic_links,
            "topic_assignments": topic_assignments,
            "cluster_links": cluster_links,
            "topic_created": topic_created,
            "dedupe_policy": dedupe_policy.as_str(),
            "isolation_policy": isolation_policy.as_str()
        });

        Ok(QualityGateResult {
            saved_memories,
            merged_memories,
            merged_records,
            association_quality,
        })
    }

    fn forget(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let memory_id = required_string(arguments, "memory_id")?;
        let hard_delete = optional_bool(arguments, "hard_delete").unwrap_or(false);
        let Some(index) = self
            .records
            .iter()
            .position(|record| record.memory_id == memory_id)
        else {
            return Err(format!("Memory not found: {memory_id}"));
        };

        let record = if hard_delete {
            self.records.remove(index)
        } else {
            self.records[index].is_archived = true;
            self.records[index].updated_at = now_stamp();
            self.records[index].clone()
        };
        self.persist_all()?;
        let label = if hard_delete { "Deleted" } else { "Archived" };
        Ok(MemoryActionResult::changed(
            json!({ "memory": record, "hard_delete": hard_delete }),
            compact_one(label, &record),
        ))
    }

    fn link(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let memory_id = required_string(arguments, "memory_id")?;
        let relation = optional_string(arguments, "relation")
            .or_else(|| optional_string(arguments, "link_type"))
            .or_else(|| {
                optional_string(arguments, "related_skill_id").map(|_| "related_to_skill".to_string())
            })
            .ok_or_else(|| {
                "Missing required string field 'relation' (or legacy alias 'link_type'); use related_skill_id for simple skill links".to_string()
            })?;
        let relation = relation.as_str();
        let target_id = link_target(arguments, relation)?;
        if target_id.is_empty() {
            return Err("target_id cannot be empty".to_string());
        }
        let Some(index) = self
            .records
            .iter()
            .position(|record| record.memory_id == memory_id)
        else {
            return Err(format!("Memory not found: {memory_id}"));
        };

        match relation {
            "depends_on_memory" => {
                self.validate_memory_refs(std::slice::from_ref(&target_id), arguments)?;
                push_unique(&mut self.records[index].depends_on_memory_ids, &target_id)
            }
            "supersedes_memory" => {
                self.validate_memory_refs(std::slice::from_ref(&target_id), arguments)?;
                push_unique(&mut self.records[index].supersedes_memory_ids, &target_id)
            }
            "related_to_memory" => {
                self.validate_memory_refs(std::slice::from_ref(&target_id), arguments)?;
                push_unique(&mut self.records[index].related_memory_ids, &target_id)
            }
            "related_to_skill" => {
                push_unique(&mut self.records[index].related_skill_ids, &target_id)
            }
            "related_to_topic" => {
                push_unique(&mut self.records[index].related_topic_ids, &target_id)
            }
            "related_to_intent" => {
                push_unique(&mut self.records[index].related_intents, &target_id)
            }
            other => return Err(format!("Unknown memory relation: {other}")),
        }
        self.records[index].updated_at = now_stamp();
        let record = self.records[index].clone();
        self.persist_all()?;
        Ok(MemoryActionResult::changed(
            json!({ "memory": record }),
            compact_one("Linked", &record),
        ))
    }

    fn unlink(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let memory_id = required_string(arguments, "memory_id")?;
        let relation = optional_string(arguments, "relation")
            .or_else(|| optional_string(arguments, "link_type"))
            .or_else(|| {
                optional_string(arguments, "related_skill_id").map(|_| "related_to_skill".to_string())
            })
            .ok_or_else(|| {
                "Missing required string field 'relation' (or legacy alias 'link_type'); use related_skill_id for simple skill links".to_string()
            })?;
        let relation = relation.as_str();
        let target_id = link_target(arguments, relation)?;
        if target_id.is_empty() {
            return Err("target_id cannot be empty".to_string());
        }
        let Some(index) = self
            .records
            .iter()
            .position(|record| record.memory_id == memory_id)
        else {
            return Err(format!("Memory not found: {memory_id}"));
        };

        match relation {
            "depends_on_memory" => {
                remove_value(&mut self.records[index].depends_on_memory_ids, &target_id)
            }
            "supersedes_memory" => {
                remove_value(&mut self.records[index].supersedes_memory_ids, &target_id)
            }
            "related_to_memory" => {
                remove_value(&mut self.records[index].related_memory_ids, &target_id)
            }
            "related_to_skill" => {
                remove_value(&mut self.records[index].related_skill_ids, &target_id)
            }
            "related_to_topic" => {
                remove_value(&mut self.records[index].related_topic_ids, &target_id)
            }
            "related_to_intent" => {
                remove_value(&mut self.records[index].related_intents, &target_id)
            }
            other => return Err(format!("Unknown memory relation: {other}")),
        }
        self.records[index].updated_at = now_stamp();
        let record = self.records[index].clone();
        self.persist_all()?;
        Ok(MemoryActionResult::changed(
            json!({ "memory": record }),
            compact_one("Unlinked", &record),
        ))
    }

    fn recluster(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
        let dry_run = optional_bool(arguments, "dry_run").unwrap_or(true);
        let apply = optional_bool(arguments, "apply").unwrap_or(!dry_run);
        let include_archived = optional_bool(arguments, "include_archived").unwrap_or(false);
        let original = self.records.clone();
        let mut records = self.records.clone();
        let mut changes = Vec::new();

        for index in 0..records.len() {
            if records[index].is_archived && !include_archived {
                continue;
            }
            let existing = records
                .iter()
                .enumerate()
                .filter(|(idx, record)| *idx != index && (include_archived || !record.is_archived))
                .map(|(_, record)| record.clone())
                .collect::<Vec<_>>();
            records[index].related_topic_ids.clear();
            let mut assignments = Vec::new();
            let mut created = Vec::new();
            assign_memory_topics(
                &mut records[index],
                &existing,
                &mut assignments,
                &mut created,
            );
        }

        for index in 0..records.len() {
            if records[index].is_archived && !include_archived {
                continue;
            }
            let existing = records
                .iter()
                .enumerate()
                .filter(|(idx, record)| *idx != index && (include_archived || !record.is_archived))
                .map(|(_, record)| record.clone())
                .collect::<Vec<_>>();
            records[index].related_memory_ids.clear();
            let links = best_related_memory_matches(&records[index], &existing, 3);
            for (candidate, _) in links {
                push_unique(&mut records[index].related_memory_ids, &candidate.memory_id);
            }
        }

        for index in 0..records.len() {
            if records[index].is_archived && !include_archived {
                continue;
            }
            let before_topics = original[index].related_topic_ids.clone();
            let before_related = original[index].related_memory_ids.clone();
            if records[index].related_topic_ids != before_topics
                || records[index].related_memory_ids != before_related
            {
                changes.push(json!({
                    "memory_id": records[index].memory_id,
                    "before": {
                        "related_topic_ids": before_topics,
                        "related_memory_ids": before_related
                    },
                    "after": {
                        "related_topic_ids": records[index].related_topic_ids,
                        "related_memory_ids": records[index].related_memory_ids
                    }
                }));
            }
        }

        if apply {
            self.records = records;
            for record in &mut self.records {
                let changed = original
                    .iter()
                    .find(|old| old.memory_id == record.memory_id)
                    .map(|old| {
                        old.related_topic_ids != record.related_topic_ids
                            || old.related_memory_ids != record.related_memory_ids
                    })
                    .unwrap_or(false);
                if changed {
                    record.updated_at = now_stamp();
                }
            }
            self.persist_all()?;
        }

        let changed_count = changes.len();
        let structured = json!({
            "dry_run": !apply,
            "applied": apply,
            "changes": changes,
            "changed_count": changed_count
        });
        let text = format!(
            "Recluster {} memories{}.",
            changed_count,
            if apply { "" } else { " (dry run)" }
        );
        if apply && changed_count > 0 {
            Ok(MemoryActionResult::changed(structured, text))
        } else {
            Ok(MemoryActionResult::unchanged(structured, text))
        }
    }

    fn validate_memory_refs(&self, memory_ids: &[String], arguments: &Value) -> Result<(), String> {
        if optional_bool(arguments, "allow_missing_memory_refs").unwrap_or(false) {
            return Ok(());
        }
        let existing = self
            .records
            .iter()
            .map(|record| record.memory_id.as_str())
            .collect::<HashSet<_>>();
        let missing = memory_ids
            .iter()
            .filter(|memory_id| !existing.contains(memory_id.as_str()))
            .cloned()
            .collect::<Vec<_>>();
        if missing.is_empty() {
            Ok(())
        } else {
            Err(format!(
                "Referenced memory not found: {}. Create it first or pass allow_missing_memory_refs=true.",
                missing.join(", ")
            ))
        }
    }

    fn search(&self, params: MemorySearchParams) -> Vec<MemorySearchResult> {
        let mut candidates: Vec<&MemoryRecord> = self
            .records
            .iter()
            .filter(|record| params.include_archived || !record.is_archived)
            .filter(|record| scope_matches(&params.scope, &record.scope))
            .filter(|record| {
                params
                    .memory_type
                    .as_deref()
                    .map(|kind| record.memory_type == kind)
                    .unwrap_or(true)
            })
            .filter(|record| {
                params
                    .related_skill_id
                    .as_deref()
                    .map(|skill_id| {
                        record
                            .related_skill_ids
                            .iter()
                            .any(|candidate| candidate == skill_id)
                    })
                    .unwrap_or(true)
            })
            .filter(|record| {
                params
                    .severity_level
                    .as_deref()
                    .map(|severity| record.severity_level.as_deref() == Some(severity))
                    .unwrap_or(true)
            })
            .filter(|record| {
                params
                    .min_confidence
                    .map(|minimum| {
                        record
                            .confidence
                            .map(|value| value >= minimum)
                            .unwrap_or(false)
                    })
                    .unwrap_or(true)
            })
            .filter(|record| {
                params
                    .applies_to_context
                    .as_deref()
                    .map(|needle| {
                        record
                            .applies_to_context
                            .as_deref()
                            .map(|value| {
                                value
                                    .to_ascii_lowercase()
                                    .contains(&needle.to_ascii_lowercase())
                            })
                            .unwrap_or(false)
                    })
                    .unwrap_or(true)
            })
            .collect();

        if candidates.is_empty() {
            return vec![];
        }

        let mut scored: Vec<MemorySearchResult> = if let Some(query) = params.query.as_deref() {
            let docs = candidates
                .iter()
                .map(|record| MemoryBm25Document {
                    memory_id: record.memory_id.clone(),
                    contents: searchable_text(record),
                })
                .collect();
            let engine = MemoryBm25Engine::from_documents(docs);
            let mut scores: HashMap<String, f32> = engine
                .search(query, candidates.len() * 2)
                .into_iter()
                .map(|result| (result.memory_id, result.score))
                .collect();
            candidates
                .iter()
                .filter_map(|record| {
                    scores
                        .remove(&record.memory_id)
                        .map(|score| MemorySearchResult {
                            memory: (*record).clone(),
                            score: score + memory_quality_bonus(record),
                        })
                })
                .collect::<Vec<_>>()
        } else {
            candidates
                .drain(..)
                .map(|record| MemorySearchResult {
                    memory: record.clone(),
                    score: memory_quality_bonus(record),
                })
                .collect()
        };

        if scored.is_empty() {
            if let Some(query) = params.query.as_deref() {
                let query_tokens = token_set(query);
                scored = candidates
                    .iter()
                    .filter_map(|record| {
                        let overlap = token_set(&searchable_text(record))
                            .intersection(&query_tokens)
                            .count();
                        (overlap > 0).then(|| MemorySearchResult {
                            memory: (*record).clone(),
                            score: overlap as f32 + memory_quality_bonus(record),
                        })
                    })
                    .collect();
            }
        }

        scored.sort_by(|left, right| {
            right
                .score
                .partial_cmp(&left.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(right.memory.updated_at.cmp(&left.memory.updated_at))
        });
        scored.truncate(params.limit.min(MAX_LIMIT));
        scored
    }

    fn find(&self, memory_id: &str) -> Option<&MemoryRecord> {
        self.records
            .iter()
            .find(|record| record.memory_id == memory_id)
    }

    fn global_path(&self) -> PathBuf {
        self.root.join("global.ttl")
    }

    fn project_path(&self) -> PathBuf {
        self.root
            .join("projects")
            .join(format!("{}.ttl", sanitize_path_segment(&self.project_id)))
    }

    fn persist_all(&self) -> Result<(), String> {
        let mut global = Vec::new();
        let mut project = Vec::new();
        for record in &self.records {
            if record.scope == "global" {
                global.push(record.clone());
            } else if record.scope == "project" {
                project.push(record.clone());
            }
        }
        write_memory_file(&self.global_path(), &global)?;
        write_memory_file(&self.project_path(), &project)?;
        Ok(())
    }
}

#[derive(Debug)]
pub struct MemoryActionResult {
    pub structured: Value,
    pub compact_text: String,
    pub changed: bool,
}

impl MemoryActionResult {
    fn changed(structured: Value, compact_text: String) -> Self {
        Self {
            structured,
            compact_text,
            changed: true,
        }
    }

    fn unchanged(structured: Value, compact_text: String) -> Self {
        Self {
            structured,
            compact_text,
            changed: false,
        }
    }
}

#[derive(Default)]
struct MemorySearchParams {
    query: Option<String>,
    scope: String,
    memory_type: Option<String>,
    related_skill_id: Option<String>,
    applies_to_context: Option<String>,
    severity_level: Option<String>,
    include_archived: bool,
    min_confidence: Option<f64>,
    limit: usize,
}

pub fn compact_search_results(title: &str, results: &[MemorySearchResult]) -> String {
    if results.is_empty() {
        return "No memories found.".to_string();
    }
    let mut lines = vec![format!("{title}:")];
    for result in results.iter().take(10) {
        let memory = &result.memory;
        let mut tags = vec![memory.scope.clone(), memory.memory_type.clone()];
        if let Some(severity) = &memory.severity_level {
            tags.push(severity.clone());
        }
        if memory.is_archived {
            tags.push("archived".to_string());
        }
        lines.push(format!(
            "- {} [{}] {}",
            memory.memory_id,
            tags.join(", "),
            memory.title.as_deref().unwrap_or(&memory.content)
        ));
    }
    lines.join("\n")
}

pub fn compact_one(label: &str, memory: &MemoryRecord) -> String {
    let mut lines = vec![format!(
        "{}: {} [{}:{}]",
        label, memory.memory_id, memory.scope, memory.memory_type
    )];
    if let Some(title) = &memory.title {
        lines.push(format!("Title: {title}"));
    }
    lines.push(memory.content.clone());
    if let Some(context) = &memory.applies_to_context {
        lines.push(format!("Context: {context}"));
    }
    if let Some(rationale) = &memory.rationale {
        lines.push(format!("Why: {rationale}"));
    }
    if !memory.related_skill_ids.is_empty() {
        lines.push(format!("Skills: {}", memory.related_skill_ids.join(", ")));
    }
    if !memory.related_intents.is_empty() {
        lines.push(format!("Intents: {}", memory.related_intents.join(", ")));
    }
    if !memory.related_topic_ids.is_empty() {
        lines.push(format!("Topics: {}", memory.related_topic_ids.join(", ")));
    }
    if !memory.related_memory_ids.is_empty() {
        lines.push(format!(
            "Related memories: {}",
            memory.related_memory_ids.join(", ")
        ));
    }
    if !memory.depends_on_memory_ids.is_empty() {
        lines.push(format!(
            "Depends on: {}",
            memory.depends_on_memory_ids.join(", ")
        ));
    }
    if !memory.supersedes_memory_ids.is_empty() {
        lines.push(format!(
            "Supersedes: {}",
            memory.supersedes_memory_ids.join(", ")
        ));
    }
    lines.join("\n")
}

fn compact_association_result(
    label: &str,
    memories: &[MemoryRecord],
    edges: &[AssociationEdge],
) -> String {
    let mut lines = vec![format!("{label}: {} memories", memories.len())];
    for memory in memories.iter().take(10) {
        lines.push(format!(
            "- {} [{}:{}] {}",
            memory.memory_id,
            memory.scope,
            memory.memory_type,
            memory.title.as_deref().unwrap_or(&memory.content)
        ));
    }
    if !edges.is_empty() {
        lines.push(format!("Edges: {}", edges.len()));
    }
    lines.join("\n")
}

fn write_memory_file(path: &Path, records: &[MemoryRecord]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "Failed to create memory directory {}: {err}",
                parent.display()
            )
        })?;
    }
    let mut output = String::new();
    output.push_str("@prefix oc: <https://ontoskills.sh/ontology#> .\n");
    output.push_str("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n");
    for record in records {
        output.push_str(&serialize_record(record));
        output.push('\n');
    }
    atomic_write(path, output.as_bytes())
        .map_err(|err| format!("Failed to write memory file {}: {err}", path.display()))
}

fn atomic_write(path: &Path, content: &[u8]) -> std::io::Result<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("memories.ttl");
    let temp_path = parent.join(format!(
        ".{file_name}.{}.tmp",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    ));
    {
        let mut file = File::create(&temp_path)?;
        file.write_all(content)?;
        file.sync_all()?;
    }
    fs::rename(&temp_path, path)?;
    if let Ok(dir) = OpenOptions::new().read(true).open(parent) {
        let _ = dir.sync_all();
    }
    Ok(())
}

fn serialize_record(record: &MemoryRecord) -> String {
    let subject = memory_ref(&record.memory_id);
    let class = memory_class(&record.memory_type);
    let knowledge_class = knowledge_class_for_memory_type(&record.memory_type);
    let mut lines = vec![format!(
        "{} a oc:Memory, oc:{}, oc:{} ;",
        subject, class, knowledge_class
    )];
    push_literal(&mut lines, "oc:memoryId", &record.memory_id);
    push_optional_literal(&mut lines, "oc:memoryTitle", record.title.as_deref());
    push_literal(&mut lines, "oc:memoryScope", &record.scope);
    push_literal(&mut lines, "oc:directiveContent", &record.content);
    push_optional_literal(
        &mut lines,
        "oc:appliesToContext",
        record.applies_to_context.as_deref(),
    );
    push_optional_literal(&mut lines, "oc:hasRationale", record.rationale.as_deref());
    push_optional_literal(
        &mut lines,
        "oc:severityLevel",
        record.severity_level.as_deref(),
    );
    if let Some(confidence) = record.confidence {
        lines.push(format!(
            "    oc:confidence \"{confidence:.3}\"^^xsd:decimal ;"
        ));
    }
    push_optional_literal(&mut lines, "oc:source", record.source.as_deref());
    push_typed_literal(
        &mut lines,
        "oc:createdAt",
        &record.created_at,
        "xsd:dateTime",
    );
    push_typed_literal(
        &mut lines,
        "oc:updatedAt",
        &record.updated_at,
        "xsd:dateTime",
    );
    lines.push(format!(
        "    oc:isArchived \"{}\"^^xsd:boolean ;",
        record.is_archived
    ));
    for skill_id in &record.related_skill_ids {
        lines.push(format!("    oc:relatedToSkill {} ;", skill_ref(skill_id)));
        push_literal(&mut lines, "oc:relatedSkillId", skill_id);
    }
    for intent in &record.related_intents {
        push_literal(&mut lines, "oc:relatedIntent", intent);
    }
    for topic_id in &record.related_topic_ids {
        push_literal(&mut lines, "oc:relatedTopic", topic_id);
    }
    for memory_id in &record.related_memory_ids {
        lines.push(format!(
            "    oc:relatedToMemory {} ;",
            memory_ref(memory_id)
        ));
    }
    for memory_id in &record.depends_on_memory_ids {
        lines.push(format!(
            "    oc:dependsOnMemory {} ;",
            memory_ref(memory_id)
        ));
    }
    for memory_id in &record.supersedes_memory_ids {
        lines.push(format!(
            "    oc:supersedesMemory {} ;",
            memory_ref(memory_id)
        ));
    }
    if let Some(last) = lines.last_mut() {
        if last.ends_with(';') {
            last.pop();
            last.push('.');
        }
    }
    lines.join("\n")
}

fn parse_memories(content: &str) -> Vec<MemoryRecord> {
    let mut records = Vec::new();
    let mut block = Vec::new();
    for raw_line in content.lines() {
        let line = raw_line.trim();
        if line.starts_with("oc:mem_") && !block.is_empty() {
            if let Some(record) = parse_memory_block(&block) {
                records.push(record);
            }
            block.clear();
        }
        if !block.is_empty() || line.starts_with("oc:mem_") {
            block.push(line.to_string());
            if line.ends_with('.') {
                if let Some(record) = parse_memory_block(&block) {
                    records.push(record);
                }
                block.clear();
            }
        }
    }
    if !block.is_empty() {
        if let Some(record) = parse_memory_block(&block) {
            records.push(record);
        }
    }
    records
}

fn parse_memory_block(lines: &[String]) -> Option<MemoryRecord> {
    let first = lines.first()?;
    if !first.contains("oc:Memory") {
        return None;
    }
    let mut record = MemoryRecord {
        memory_id: String::new(),
        title: None,
        memory_type: memory_type_from_block(first),
        scope: "project".to_string(),
        content: String::new(),
        applies_to_context: None,
        rationale: None,
        severity_level: None,
        confidence: None,
        source: None,
        related_skill_ids: vec![],
        related_topic_ids: vec![],
        related_memory_ids: vec![],
        depends_on_memory_ids: vec![],
        supersedes_memory_ids: vec![],
        related_intents: vec![],
        created_at: String::new(),
        updated_at: String::new(),
        is_archived: false,
    };
    let mut related_skill_exact_ids = Vec::new();
    let mut related_skill_fallback_ids = Vec::new();

    for line in lines {
        if line.contains("oc:memoryId ") {
            record.memory_id = extract_literal(line)?;
        } else if line.contains("oc:memoryTitle ") {
            record.title = extract_literal(line);
        } else if line.contains("oc:memoryScope ") {
            record.scope = extract_literal(line)?;
        } else if line.contains("oc:directiveContent ") {
            record.content = extract_literal(line)?;
        } else if line.contains("oc:appliesToContext ") {
            record.applies_to_context = extract_literal(line);
        } else if line.contains("oc:hasRationale ") {
            record.rationale = extract_literal(line);
        } else if line.contains("oc:severityLevel ") {
            record.severity_level = extract_literal(line);
        } else if line.contains("oc:confidence ") {
            record.confidence = extract_literal(line).and_then(|value| value.parse::<f64>().ok());
        } else if line.contains("oc:source ") {
            record.source = extract_literal(line);
        } else if line.contains("oc:createdAt ") {
            record.created_at = extract_literal(line)?;
        } else if line.contains("oc:updatedAt ") {
            record.updated_at = extract_literal(line)?;
        } else if line.contains("oc:isArchived ") {
            record.is_archived = extract_literal(line)
                .map(|value| value == "true")
                .unwrap_or(false);
        } else if line.contains("oc:relatedSkillId ") {
            if let Some(value) = extract_literal(line) {
                related_skill_exact_ids.push(value);
            }
        } else if line.contains("oc:relatedIntent ") {
            if let Some(value) = extract_literal(line) {
                record.related_intents.push(value);
            }
        } else if line.contains("oc:relatedTopic ") {
            if let Some(value) = extract_literal(line) {
                record.related_topic_ids.push(value);
            }
        } else if line.contains("oc:relatedToSkill ") {
            if let Some(value) = extract_prefixed_object(line, "oc:skill_") {
                related_skill_fallback_ids.push(desanitize_ref(&value));
            }
        } else if line.contains("oc:relatedToMemory ") {
            if let Some(value) = extract_prefixed_object(line, "oc:mem_") {
                record
                    .related_memory_ids
                    .push(desanitize_memory_ref(&value));
            }
        } else if line.contains("oc:dependsOnMemory ") {
            if let Some(value) = extract_prefixed_object(line, "oc:mem_") {
                record
                    .depends_on_memory_ids
                    .push(desanitize_memory_ref(&value));
            }
        } else if line.contains("oc:supersedesMemory ") {
            if let Some(value) = extract_prefixed_object(line, "oc:mem_") {
                record
                    .supersedes_memory_ids
                    .push(desanitize_memory_ref(&value));
            }
        }
    }

    if record.memory_id.is_empty() || record.content.is_empty() {
        return None;
    }
    record.related_skill_ids = if related_skill_exact_ids.is_empty() {
        related_skill_fallback_ids
    } else {
        related_skill_exact_ids
    };
    normalize_id_list(&mut record.related_skill_ids);
    normalize_id_list(&mut record.related_topic_ids);
    normalize_id_list(&mut record.related_memory_ids);
    normalize_id_list(&mut record.depends_on_memory_ids);
    normalize_id_list(&mut record.supersedes_memory_ids);
    normalize_id_list(&mut record.related_intents);
    Some(record)
}

fn memory_type_from_block(first: &str) -> String {
    for (class, kind) in [
        ("ProcedureMemory", "procedure"),
        ("CorrectionMemory", "correction"),
        ("AntiPatternMemory", "anti_pattern"),
        ("PreferenceMemory", "preference"),
        ("FactMemory", "fact"),
    ] {
        if first.contains(class) {
            return kind.to_string();
        }
    }
    "fact".to_string()
}

fn push_literal(lines: &mut Vec<String>, predicate: &str, value: &str) {
    lines.push(format!("    {} \"{}\" ;", predicate, escape_literal(value)));
}

fn push_typed_literal(lines: &mut Vec<String>, predicate: &str, value: &str, datatype: &str) {
    lines.push(format!(
        "    {} \"{}\"^^{} ;",
        predicate,
        escape_literal(value),
        datatype
    ));
}

fn push_optional_literal(lines: &mut Vec<String>, predicate: &str, value: Option<&str>) {
    if let Some(value) = value {
        if !value.trim().is_empty() {
            push_literal(lines, predicate, value);
        }
    }
}

fn escape_literal(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn unescape_literal(value: &str) -> String {
    let mut out = String::new();
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch == '\\' {
            match chars.next() {
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('"') => out.push('"'),
                Some('\\') => out.push('\\'),
                Some(other) => {
                    out.push('\\');
                    out.push(other);
                }
                None => out.push('\\'),
            }
        } else {
            out.push(ch);
        }
    }
    out
}

fn extract_literal(line: &str) -> Option<String> {
    let start = line.find('"')?;
    let rest = &line[start + 1..];
    let mut escaped = false;
    for (idx, ch) in rest.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
            continue;
        }
        if ch == '"' {
            return Some(unescape_literal(&rest[..idx]));
        }
    }
    None
}

fn extract_prefixed_object(line: &str, prefix: &str) -> Option<String> {
    let idx = line.find(prefix)?;
    let rest = &line[idx + prefix.len()..];
    let raw = rest
        .trim_end_matches([';', '.'])
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .trim();
    if raw.is_empty() {
        None
    } else {
        Some(raw.to_string())
    }
}

fn desanitize_ref(value: &str) -> String {
    value.replace('_', "/")
}

fn desanitize_memory_ref(value: &str) -> String {
    value.replace('_', "-")
}

fn memory_ref(memory_id: &str) -> String {
    format!("oc:mem_{}", sanitize_ref(memory_id))
}

fn skill_ref(skill_id: &str) -> String {
    if skill_id.starts_with("http://") || skill_id.starts_with("https://") {
        format!("<{}>", skill_id)
    } else {
        format!("oc:skill_{}", sanitize_ref(skill_id))
    }
}

fn sanitize_ref(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .to_string()
}

fn sanitize_path_segment(value: &str) -> String {
    let sanitized = sanitize_ref(value);
    if sanitized.is_empty() {
        "unknown".to_string()
    } else {
        sanitized
    }
}

fn memory_class(memory_type: &str) -> &'static str {
    match memory_type {
        "procedure" => "ProcedureMemory",
        "correction" => "CorrectionMemory",
        "anti_pattern" => "AntiPatternMemory",
        "preference" => "PreferenceMemory",
        _ => "FactMemory",
    }
}

fn knowledge_class_for_memory_type(memory_type: &str) -> &'static str {
    match memory_type {
        "procedure" => "Procedure",
        "correction" => "RecoveryTactic",
        "anti_pattern" => "AntiPattern",
        "preference" => "Heuristic",
        _ => "DataProvenance",
    }
}

fn normalize_memory_type(value: &str) -> Result<String, String> {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "procedure" => Ok("procedure".to_string()),
        "correction" => Ok("correction".to_string()),
        "anti_pattern" | "antipattern" => Ok("anti_pattern".to_string()),
        "preference" => Ok("preference".to_string()),
        "fact" => Ok("fact".to_string()),
        other => Err(format!("Invalid memory_type: {other}")),
    }
}

fn normalize_severity(value: &str) -> Result<String, String> {
    match value.trim().to_ascii_uppercase().as_str() {
        "CRITICAL" => Ok("CRITICAL".to_string()),
        "HIGH" => Ok("HIGH".to_string()),
        "MEDIUM" => Ok("MEDIUM".to_string()),
        "LOW" => Ok("LOW".to_string()),
        other => Err(format!("Invalid severity_level: {other}")),
    }
}

fn validate_content(value: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        return Err("content cannot be empty".to_string());
    }
    if value.len() > MAX_MEMORY_CONTENT_LEN {
        return Err(format!(
            "content exceeds {MAX_MEMORY_CONTENT_LEN} characters"
        ));
    }
    Ok(())
}

fn validated_content(value: &str) -> Result<String, String> {
    validate_content(value)?;
    Ok(value.trim().to_string())
}

fn validate_confidence(value: f64) -> Result<f64, String> {
    if !(0.0..=1.0).contains(&value) {
        return Err("confidence must be between 0.0 and 1.0".to_string());
    }
    Ok(value)
}

fn validate_write_scope(scope: &str) -> Result<(), String> {
    match scope {
        "global" | "project" => Ok(()),
        other => Err(format!(
            "Invalid write scope: {other}. Expected global or project"
        )),
    }
}

fn validate_read_scope(scope: &str) -> Result<(), String> {
    match scope {
        "global" | "project" | "both" => Ok(()),
        other => Err(format!(
            "Invalid read scope: {other}. Expected global, project, or both"
        )),
    }
}

fn scope_matches(filter: &str, scope: &str) -> bool {
    filter == "both" || filter == scope
}

fn now_stamp() -> String {
    timestamp_from_unix_nanos(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_nanos())
            .unwrap_or(0),
    )
}

fn timestamp_from_unix_nanos(nanos: u128) -> String {
    let seconds = (nanos / 1_000_000_000) as i64;
    let subsecond_nanos = (nanos % 1_000_000_000) as u32;
    let days = seconds.div_euclid(86_400);
    let seconds_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = (seconds_of_day % 3_600) / 60;
    let second = seconds_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{subsecond_nanos:09}Z")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

fn generate_memory_id(content: &str, scope: &str) -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    format!(
        "mem-{millis}-{}",
        stable_hash64(&format!("{scope}:{content}"))
    )[..32]
        .to_string()
}

fn stable_hash64(value: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for byte in value.as_bytes() {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

fn searchable_text(record: &MemoryRecord) -> String {
    let mut parts = vec![
        record.content.clone(),
        record.memory_type.clone(),
        record.scope.clone(),
    ];
    if let Some(title) = &record.title {
        parts.push(title.clone());
    }
    if let Some(context) = &record.applies_to_context {
        parts.push(context.clone());
    }
    if let Some(rationale) = &record.rationale {
        parts.push(rationale.clone());
    }
    if let Some(source) = &record.source {
        parts.push(source.clone());
    }
    if let Some(severity) = &record.severity_level {
        parts.push(severity.clone());
    }
    parts.extend(record.related_skill_ids.iter().cloned());
    parts.extend(record.related_topic_ids.iter().cloned());
    parts.extend(record.related_memory_ids.iter().cloned());
    parts.extend(record.depends_on_memory_ids.iter().cloned());
    parts.extend(record.supersedes_memory_ids.iter().cloned());
    parts.extend(record.related_intents.iter().cloned());
    parts.join(" ")
}

fn split_atomic_statements(content: &str) -> Vec<String> {
    let mut normalized = content.replace('\n', ". ");
    for delimiter in [';', '。'] {
        normalized = normalized.replace(delimiter, ". ");
    }
    let mut atoms = normalized
        .split(['.', '!', '?'])
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .map(|part| {
            part.trim_matches(|ch: char| ch == '-' || ch == '*' || ch.is_whitespace())
                .trim()
                .to_string()
        })
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>();
    if atoms.is_empty() {
        atoms.push(content.trim().to_string());
    }
    atoms
}

fn infer_memory_type(content: &str) -> &'static str {
    let lower = content.to_ascii_lowercase();
    if contains_any(
        &lower,
        &[
            "non usare",
            "non fare",
            "evita",
            "mai ",
            "do not",
            "avoid",
            "never ",
        ],
    ) {
        "anti_pattern"
    } else if contains_any(
        &lower,
        &[
            "correggi",
            "correzione",
            "invece di",
            "obsoleto",
            "sostituisci",
            "supersede",
            "instead of",
            "obsolete",
        ],
    ) {
        "correction"
    } else if contains_any(
        &lower,
        &["prefer", "preferisci", "piace", "favorite", "usa sempre"],
    ) {
        "preference"
    } else if contains_any(
        &lower,
        &[
            "prima", "poi", "dopo", "verifica", "esegui", "usa ", "run ", "check ", "deploy",
            "when ", "quando ",
        ],
    ) {
        "procedure"
    } else {
        "fact"
    }
}

fn infer_confidence(content: &str) -> f64 {
    let lower = content.to_ascii_lowercase();
    if contains_any(&lower, &["forse", "credo", "maybe", "probably", "penso"]) {
        0.55
    } else if contains_any(
        &lower,
        &["sempre", "mai", "must", "deve", "never", "always"],
    ) {
        0.82
    } else {
        0.68
    }
}

fn infer_context(
    content: &str,
    related_intents: &[String],
    related_skill_ids: &[String],
) -> Option<String> {
    let lower = content.to_ascii_lowercase();
    for marker in [
        "solo in ",
        "only in ",
        "per ",
        "for ",
        "quando ",
        "when ",
        "in staging",
        "in produzione",
        "in production",
    ] {
        if let Some(idx) = lower.find(marker) {
            if let Some(context) = marker.strip_prefix("in ") {
                return Some(context.trim().to_string());
            }
            let original = content[idx + marker.len()..]
                .split([',', ';', '.'])
                .next()
                .unwrap_or_default()
                .trim();
            if !original.is_empty() {
                return Some(original.chars().take(80).collect());
            }
        }
    }
    related_intents
        .first()
        .cloned()
        .or_else(|| related_skill_ids.first().cloned())
}

fn infer_related_intents(content: &str) -> Vec<String> {
    let lower = content.to_ascii_lowercase();
    let mut intents = Vec::new();
    let action_intent = infer_action_intent(content);
    if !action_intent.is_empty() {
        intents.push(action_intent);
    }
    for marker in ["per ", "for ", "quando ", "when "] {
        if let Some(idx) = lower.find(marker) {
            let phrase = content[idx + marker.len()..]
                .split([',', ';', '.'])
                .next()
                .unwrap_or_default();
            let slug = slugify_words(phrase, 4);
            if !slug.is_empty() {
                intents.push(slug);
            }
        }
    }
    if contains_any(&lower, &["deploy", "rilascio", "release"])
        && !intents.iter().any(|intent| intent.starts_with("deploy"))
    {
        intents.push("deploy".to_string());
    }
    normalize_id_list(&mut intents);
    intents
}

fn infer_workflow_intents(atoms: &[String]) -> Vec<String> {
    let mut intents = Vec::new();
    for atom in atoms.iter().rev() {
        let kind = infer_memory_type(atom);
        if kind == "procedure" || kind == "correction" {
            let intent = infer_action_intent(atom);
            if !intent.is_empty() {
                intents.push(intent);
                break;
            }
        }
    }
    if intents.is_empty() {
        for atom in atoms {
            let intent = infer_action_intent(atom);
            if !intent.is_empty() {
                intents.push(intent);
                break;
            }
        }
    }
    normalize_id_list(&mut intents);
    intents
}

fn infer_action_intent(content: &str) -> String {
    let tokens = meaningful_tokens(content);
    if tokens.is_empty() {
        return String::new();
    }
    let action_idx = tokens
        .iter()
        .position(|token| is_action_token(token))
        .unwrap_or(usize::MAX);
    if action_idx == usize::MAX && tokens.len() < 2 {
        return String::new();
    }
    let action_idx = if action_idx == usize::MAX {
        0
    } else {
        action_idx
    };
    tokens
        .iter()
        .skip(action_idx)
        .filter(|token| !is_sequence_token(token))
        .take(4)
        .cloned()
        .collect::<Vec<_>>()
        .join("-")
}

fn infer_related_skill_ids(content: &str) -> Vec<String> {
    let mut skills = Vec::new();
    for token in content.split_whitespace() {
        let clean = token.trim_matches(|ch: char| {
            !ch.is_ascii_alphanumeric() && ch != '/' && ch != '-' && ch != '_'
        });
        if clean.contains('/') || clean.ends_with("-skill") {
            skills.push(clean.to_string());
        }
    }
    normalize_id_list(&mut skills);
    skills
}

fn apply_inferred_memory_edges(
    memories: &mut [MemoryRecord],
    edges: &mut Vec<AssociationEdge>,
    existing: &[MemoryRecord],
    compound: bool,
) {
    for idx in 1..memories.len() {
        let current_lower = memories[idx].content.to_ascii_lowercase();
        let previous_lower = memories[idx - 1].content.to_ascii_lowercase();
        if contains_any(&current_lower, &["poi", "dopo", "then", "after", "quindi"])
            || contains_any(&previous_lower, &["prima", "before", "verifica", "check"])
            || (compound
                && memories[idx].memory_type == "procedure"
                && memories[idx - 1].memory_type == "procedure")
        {
            let target = memories[idx - 1].memory_id.clone();
            push_unique(&mut memories[idx].depends_on_memory_ids, &target);
            edges.push(AssociationEdge::new(
                &memories[idx].memory_id,
                &target,
                "depends_on_memory",
            ));
        }
    }
    for memory in memories.iter_mut() {
        let lower = memory.content.to_ascii_lowercase();
        if contains_any(
            &lower,
            &[
                "obsoleto",
                "obsolete",
                "invece di",
                "instead of",
                "non usare più",
                "sostituisce",
            ],
        ) {
            if let Some(target) = best_existing_memory_match(&memory.content, existing) {
                push_unique(&mut memory.supersedes_memory_ids, &target.memory_id);
                edges.push(AssociationEdge::new(
                    &memory.memory_id,
                    &target.memory_id,
                    "supersedes_memory",
                ));
            }
        }
    }
}

fn best_existing_memory_match<'a>(
    content: &str,
    existing: &'a [MemoryRecord],
) -> Option<&'a MemoryRecord> {
    let source_tokens = token_set(content);
    existing
        .iter()
        .filter(|memory| !memory.is_archived)
        .map(|memory| {
            let overlap = token_set(&searchable_text(memory))
                .intersection(&source_tokens)
                .count();
            (memory, overlap)
        })
        .filter(|(_, overlap)| *overlap >= 2)
        .max_by_key(|(_, overlap)| *overlap)
        .map(|(memory, _)| memory)
}

fn best_related_memory_matches<'a>(
    incoming: &MemoryRecord,
    existing: &'a [MemoryRecord],
    limit: usize,
) -> Vec<(&'a MemoryRecord, f32)> {
    let mut matches = existing
        .iter()
        .filter(|memory| !memory.is_archived)
        .filter(|memory| memory.scope == incoming.scope || memory.scope == "global")
        .filter(|memory| !incoming.related_memory_ids.contains(&memory.memory_id))
        .filter(|memory| !incoming.depends_on_memory_ids.contains(&memory.memory_id))
        .filter(|memory| !incoming.supersedes_memory_ids.contains(&memory.memory_id))
        .map(|memory| (memory, topic_similarity(incoming, memory)))
        .filter(|(_, score)| score.is_strong_match())
        .map(|(memory, score)| (memory, score.score))
        .collect::<Vec<_>>();
    matches.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    matches.truncate(limit);
    matches
}

fn assign_memory_topics(
    memory: &mut MemoryRecord,
    existing: &[MemoryRecord],
    topic_assignments: &mut Vec<Value>,
    topic_created: &mut Vec<Value>,
) {
    let mut assigned = Vec::new();
    if !memory.related_topic_ids.is_empty() {
        for topic_id in &memory.related_topic_ids {
            push_unique(&mut assigned, topic_id);
            topic_assignments.push(json!({
                "memory_id": memory.memory_id,
                "topic_id": topic_id,
                "action": "explicit",
                "score": 1.0
            }));
        }
    }

    for topic_id in infer_canonical_topic_ids(memory) {
        let already_present = assigned.iter().any(|existing| existing == &topic_id);
        push_unique(&mut assigned, &topic_id);
        topic_assignments.push(json!({
            "memory_id": memory.memory_id,
            "topic_id": topic_id,
            "action": if already_present { "explicit" } else { "inferred" },
            "score": 1.0
        }));
    }

    for (topic_id, score) in best_topic_matches(memory, existing, 3) {
        if assigned.len() >= 3 {
            break;
        }
        if assigned.iter().any(|existing| existing == &topic_id) {
            continue;
        }
        push_unique(&mut assigned, &topic_id);
        topic_assignments.push(json!({
            "memory_id": memory.memory_id,
            "topic_id": topic_id,
            "action": "matched",
            "score": score
        }));
    }

    if assigned.is_empty() {
        let topic_id = infer_topic_id(memory);
        push_unique(&mut assigned, &topic_id);
        topic_assignments.push(json!({
            "memory_id": memory.memory_id,
            "topic_id": topic_id,
            "action": "created",
            "score": 1.0
        }));
        topic_created.push(json!({
            "topic_id": topic_id,
            "source_memory_id": memory.memory_id
        }));
    }

    memory.related_topic_ids = assigned;
}

fn best_topic_matches(
    incoming: &MemoryRecord,
    existing: &[MemoryRecord],
    limit: usize,
) -> Vec<(String, f32)> {
    let mut scores: HashMap<String, f32> = HashMap::new();
    for memory in existing
        .iter()
        .filter(|memory| !memory.is_archived)
        .filter(|memory| memory.scope == incoming.scope || memory.scope == "global")
        .filter(|memory| !memory.related_topic_ids.is_empty())
    {
        let similarity = topic_similarity(incoming, memory);
        if !similarity.is_topic_match() {
            continue;
        }
        for topic_id in &memory.related_topic_ids {
            let entry = scores.entry(topic_id.clone()).or_insert(0.0);
            *entry = (*entry).max(similarity.score);
        }
    }
    let mut matches = scores
        .into_iter()
        .filter(|(_, score)| *score >= 1.85)
        .collect::<Vec<_>>();
    matches.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    matches.truncate(limit);
    matches
}

fn infer_canonical_topic_ids(memory: &MemoryRecord) -> Vec<String> {
    let text = topic_basis_text(memory).to_ascii_lowercase();
    let mut topics = Vec::new();

    if contains_any(
        &text,
        &[
            "moto",
            "scooter",
            "macchina",
            "auto",
            "tragitto",
            "tragitti",
            "spostamento",
            "spostamenti",
            "tratte",
            "viaggio",
            "viaggi",
            "piove",
            "citta",
            "città",
        ],
    ) {
        push_unique(&mut topics, "topic-mobilita");
    }
    if contains_any(
        &text,
        &[
            "lavoro",
            "ufficio",
            "professionale",
            "professione",
            "ingegnere",
            "informatico",
            "commuting",
            "commute",
        ],
    ) {
        push_unique(&mut topics, "topic-lavoro");
    }
    if contains_any(&text, &["moto", "scooter", "cilindrata", "600cc"]) {
        push_unique(&mut topics, "topic-moto");
    }
    if contains_any(&text, &["macchina", "auto"]) {
        push_unique(&mut topics, "topic-auto");
    }
    if contains_any(
        &text,
        &[
            "acquistare",
            "acquisto",
            "comprare",
            "vorrei",
            "desidero",
            "potente",
            "upgrade",
        ],
    ) {
        push_unique(&mut topics, "topic-acquisti");
    }
    if contains_any(
        &text,
        &[
            "codice", "coding", "progetto", "rust", "api", "server", "test",
        ],
    ) {
        push_unique(&mut topics, "topic-progetto-codice");
    }

    topics.truncate(3);
    topics
}

fn infer_topic_id(memory: &MemoryRecord) -> String {
    let mut parts = Vec::new();
    if let Some(context) = &memory.applies_to_context {
        parts.push(context.clone());
    }
    parts.extend(memory.related_skill_ids.iter().cloned());
    parts.extend(
        memory
            .related_intents
            .iter()
            .filter(|intent| !is_generic_topic_value(intent))
            .cloned(),
    );
    if parts.is_empty() {
        if let Some(title) = &memory.title {
            parts.push(title.clone());
        }
        parts.push(memory.content.clone());
    }
    let slug = slugify_words(&parts.join(" "), 5);
    if slug.is_empty() {
        "topic-unclassified".to_string()
    } else {
        format!("topic-{slug}")
    }
}

#[derive(Debug, Clone, Copy)]
struct TopicSimilarity {
    score: f32,
    intent_overlap: usize,
    skill_overlap: usize,
    topic_overlap: usize,
    context_match: bool,
    token_overlap: usize,
    jaccard: f32,
}

impl TopicSimilarity {
    fn is_strong_match(self) -> bool {
        if self.score < 2.2 {
            return false;
        }
        self.intent_overlap > 0
            || self.skill_overlap > 0
            || self.topic_overlap > 0
            || (self.context_match && self.token_overlap > 0)
            || self.token_overlap >= 3
            || self.jaccard >= 0.28
    }

    fn is_topic_match(self) -> bool {
        if self.score < 1.85 {
            return false;
        }
        self.intent_overlap > 0
            || self.skill_overlap > 0
            || self.topic_overlap > 0
            || (self.context_match && self.token_overlap > 0)
            || self.token_overlap >= 2
            || self.jaccard >= 0.22
    }
}

fn topic_similarity(left: &MemoryRecord, right: &MemoryRecord) -> TopicSimilarity {
    let mut score = 0.0;
    let left_intents = topic_intent_set(&left.related_intents);
    let right_intents = topic_intent_set(&right.related_intents);
    let intent_overlap = left_intents.intersection(&right_intents).count();
    score += intent_overlap as f32 * 2.8;
    score += loose_intent_similarity(&left.related_intents, &right.related_intents);

    let left_skills = left.related_skill_ids.iter().collect::<HashSet<_>>();
    let right_skills = right.related_skill_ids.iter().collect::<HashSet<_>>();
    let skill_overlap = left_skills.intersection(&right_skills).count();
    score += skill_overlap as f32 * 2.0;

    let left_topics = left.related_topic_ids.iter().collect::<HashSet<_>>();
    let right_topics = right.related_topic_ids.iter().collect::<HashSet<_>>();
    let topic_overlap = left_topics.intersection(&right_topics).count();
    score += topic_overlap as f32 * 2.4;

    let context_match = left.applies_to_context.is_some()
        && left.applies_to_context.as_deref() == right.applies_to_context.as_deref()
        && !is_generic_topic_value(left.applies_to_context.as_deref().unwrap_or_default());
    if context_match {
        score += 1.5;
    }

    let left_tokens = topic_token_set(&topic_basis_text(left));
    let right_tokens = topic_token_set(&topic_basis_text(right));
    let token_overlap = left_tokens.intersection(&right_tokens).count();
    score += (token_overlap as f32 * 0.35).min(2.1);
    let jaccard = jaccard(&left_tokens, &right_tokens);
    score += jaccard * 2.5;

    TopicSimilarity {
        score,
        intent_overlap,
        skill_overlap,
        topic_overlap,
        context_match,
        token_overlap,
        jaccard,
    }
}

fn topic_basis_text(record: &MemoryRecord) -> String {
    let mut parts = Vec::new();
    if let Some(title) = &record.title {
        parts.push(title.clone());
    }
    parts.push(record.content.clone());
    if let Some(context) = &record.applies_to_context {
        parts.push(context.clone());
    }
    parts.extend(record.related_skill_ids.iter().cloned());
    parts.extend(record.related_intents.iter().cloned());
    parts.extend(record.related_topic_ids.iter().cloned());
    parts.join(" ")
}

fn topic_intent_set(intents: &[String]) -> HashSet<&str> {
    intents
        .iter()
        .map(String::as_str)
        .filter(|intent| !is_generic_topic_value(intent))
        .collect()
}

fn loose_intent_similarity(left: &[String], right: &[String]) -> f32 {
    let mut best = 0.0;
    for left_intent in left {
        if is_generic_topic_value(left_intent) {
            continue;
        }
        let left_tokens = topic_token_set(left_intent);
        for right_intent in right {
            if is_generic_topic_value(right_intent) {
                continue;
            }
            let right_tokens = topic_token_set(right_intent);
            let overlap = left_tokens.intersection(&right_tokens).count();
            if overlap >= 2 {
                let score = 0.9 + (overlap as f32 * 0.25);
                if score > best {
                    best = score;
                }
            }
        }
    }
    best
}

fn topic_token_set(content: &str) -> HashSet<String> {
    meaningful_tokens(content)
        .into_iter()
        .filter(|token| !is_generic_topic_value(token))
        .collect()
}

fn is_generic_topic_value(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "" | "inbox"
            | "inbox/unclassified"
            | "unclassified"
            | "project"
            | "global"
            | "fact"
            | "preference"
            | "procedure"
            | "warning"
            | "correction"
            | "deploy"
            | "release"
            | "check"
            | "verifica"
            | "usa"
            | "use"
            | "run"
            | "esegui"
    )
}

fn token_set(content: &str) -> HashSet<String> {
    content
        .split(|ch: char| !ch.is_ascii_alphanumeric())
        .map(str::trim)
        .filter(|token| token.len() > 2)
        .map(|token| token.to_ascii_lowercase())
        .collect()
}

fn make_title(content: &str) -> String {
    let trimmed = content.trim();
    let mut title = trimmed
        .split_whitespace()
        .take(8)
        .collect::<Vec<_>>()
        .join(" ");
    if title.len() > 80 {
        title.truncate(80);
    }
    if title.is_empty() {
        "Memory".to_string()
    } else {
        title
    }
}

fn slugify_words(value: &str, max_words: usize) -> String {
    meaningful_tokens(value)
        .into_iter()
        .take(max_words)
        .collect::<Vec<_>>()
        .join("-")
}

fn meaningful_tokens(value: &str) -> Vec<String> {
    value
        .split(|ch: char| !ch.is_ascii_alphanumeric())
        .map(str::trim)
        .filter(|word| word.len() > 2)
        .map(|word| word.to_ascii_lowercase())
        .filter(|word| !is_stopword(word))
        .collect()
}

fn is_action_token(value: &str) -> bool {
    matches!(
        value,
        "deploy"
            | "rilascio"
            | "release"
            | "verifica"
            | "check"
            | "run"
            | "esegui"
            | "usa"
            | "use"
            | "crea"
            | "create"
            | "correggi"
            | "fix"
            | "aggiorna"
            | "update"
    )
}

fn is_sequence_token(value: &str) -> bool {
    matches!(
        value,
        "prima" | "poi" | "dopo" | "quindi" | "before" | "then" | "after"
    )
}

fn is_stopword(value: &str) -> bool {
    matches!(
        value,
        "prima"
            | "poi"
            | "dopo"
            | "quindi"
            | "solo"
            | "only"
            | "quando"
            | "when"
            | "per"
            | "for"
            | "the"
            | "and"
            | "con"
            | "senza"
            | "nella"
            | "nelle"
            | "della"
            | "degli"
            | "del"
            | "dei"
            | "una"
            | "uno"
            | "gli"
            | "che"
            | "in"
            | "di"
            | "da"
    )
}

fn contains_any(value: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| value.contains(needle))
}

fn memory_quality_bonus(record: &MemoryRecord) -> f32 {
    let severity = match record.severity_level.as_deref() {
        Some("CRITICAL") => 0.4,
        Some("HIGH") => 0.3,
        Some("MEDIUM") => 0.15,
        _ => 0.0,
    };
    let confidence = record.confidence.unwrap_or(0.5) as f32 * 0.2;
    severity + confidence
}

fn normalize_dedupe_policy(arguments: &Value) -> Result<DedupePolicy, String> {
    match optional_string(arguments, "dedupe_policy")
        .unwrap_or_else(|| "merge".to_string())
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "merge" => Ok(DedupePolicy::Merge),
        "reject" => Ok(DedupePolicy::Reject),
        "allow" => Ok(DedupePolicy::Allow),
        other => Err(format!("Invalid dedupe_policy: {other}")),
    }
}

fn normalize_isolation_policy(arguments: &Value) -> Result<IsolationPolicy, String> {
    match optional_string(arguments, "isolation_policy")
        .unwrap_or_else(|| "auto_link".to_string())
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "auto_link" | "auto-link" => Ok(IsolationPolicy::AutoLink),
        "reject" => Ok(IsolationPolicy::Reject),
        "inbox" => Ok(IsolationPolicy::Inbox),
        other => Err(format!("Invalid isolation_policy: {other}")),
    }
}

fn is_isolated(memory: &MemoryRecord) -> bool {
    memory.related_skill_ids.is_empty()
        && memory.related_topic_ids.is_empty()
        && memory.related_memory_ids.is_empty()
        && memory.related_intents.is_empty()
        && memory.depends_on_memory_ids.is_empty()
        && memory.supersedes_memory_ids.is_empty()
}

fn apply_isolation_policy(
    memory: &mut MemoryRecord,
    existing: &[MemoryRecord],
    policy: IsolationPolicy,
    fallback_used: &mut Vec<String>,
) -> Result<(), String> {
    let mut intents = infer_related_intents(&memory.content);
    if intents.is_empty() {
        if let Some(title) = memory.title.as_deref() {
            intents.extend(infer_related_intents(title));
        }
    }
    for intent in intents {
        push_unique(&mut memory.related_intents, &intent);
    }
    if !is_isolated(memory) {
        return Ok(());
    }

    if policy == IsolationPolicy::AutoLink {
        if let Some(candidate) = best_existing_memory_match(&memory.content, existing) {
            push_unique(&mut memory.depends_on_memory_ids, &candidate.memory_id);
            fallback_used.push(format!("{}:nearest_memory", memory.memory_id));
            return Ok(());
        }
    }

    match policy {
        IsolationPolicy::Reject => Err(format!(
            "Memory would be isolated: {}",
            memory.title.as_deref().unwrap_or(&memory.content)
        )),
        IsolationPolicy::AutoLink | IsolationPolicy::Inbox => {
            push_unique(&mut memory.related_intents, "inbox/unclassified");
            fallback_used.push(format!("{}:inbox/unclassified", memory.memory_id));
            Ok(())
        }
    }
}

fn find_duplicate_index(records: &[MemoryRecord], incoming: &MemoryRecord) -> Option<usize> {
    let incoming_signature = memory_signature(incoming);
    let incoming_tokens = token_set(&dedupe_text(incoming));
    records
        .iter()
        .enumerate()
        .filter(|(_, record)| !record.is_archived)
        .filter(|(_, record)| record.scope == incoming.scope || record.scope == "global")
        .map(|(idx, record)| {
            let exact = memory_signature(record) == incoming_signature;
            let similarity = jaccard(&incoming_tokens, &token_set(&dedupe_text(record)));
            (idx, exact, similarity)
        })
        .filter(|(_, exact, similarity)| *exact || *similarity >= 0.82)
        .max_by(|left, right| {
            left.2
                .partial_cmp(&right.2)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(idx, _, _)| idx)
}

fn merge_memory_record(existing: &mut MemoryRecord, incoming: &MemoryRecord) {
    if existing.title.is_none() {
        existing.title = incoming.title.clone();
    }
    if existing.applies_to_context.is_none() {
        existing.applies_to_context = incoming.applies_to_context.clone();
    }
    if existing.rationale.is_none() {
        existing.rationale = incoming.rationale.clone();
    }
    if existing.severity_level.is_none() {
        existing.severity_level = incoming.severity_level.clone();
    }
    if existing.confidence.unwrap_or(0.0) < incoming.confidence.unwrap_or(0.0) {
        existing.confidence = incoming.confidence;
    }
    if existing.source.is_none() {
        existing.source = incoming.source.clone();
    }
    extend_unique(&mut existing.related_skill_ids, &incoming.related_skill_ids);
    extend_unique(&mut existing.related_topic_ids, &incoming.related_topic_ids);
    extend_unique(
        &mut existing.related_memory_ids,
        &incoming.related_memory_ids,
    );
    extend_unique(
        &mut existing.depends_on_memory_ids,
        &incoming.depends_on_memory_ids,
    );
    extend_unique(
        &mut existing.supersedes_memory_ids,
        &incoming.supersedes_memory_ids,
    );
    extend_unique(&mut existing.related_intents, &incoming.related_intents);
    existing.updated_at = now_stamp();
}

fn extend_unique(target: &mut Vec<String>, values: &[String]) {
    for value in values {
        push_unique(target, value);
    }
}

fn memory_signature(memory: &MemoryRecord) -> String {
    normalize_for_dedupe(&dedupe_text(memory))
}

fn dedupe_text(memory: &MemoryRecord) -> String {
    [
        memory.title.clone().unwrap_or_default(),
        memory.content.clone(),
        memory.applies_to_context.clone().unwrap_or_default(),
    ]
    .join(" ")
}

fn normalize_for_dedupe(value: &str) -> String {
    meaningful_tokens(value).join(" ")
}

fn jaccard(left: &HashSet<String>, right: &HashSet<String>) -> f32 {
    if left.is_empty() || right.is_empty() {
        return 0.0;
    }
    let intersection = left.intersection(right).count() as f32;
    let union = left.union(right).count() as f32;
    if union == 0.0 {
        0.0
    } else {
        intersection / union
    }
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    let normalized = value.trim().to_string();
    if !normalized.is_empty() && !values.iter().any(|existing| existing == &normalized) {
        values.push(normalized);
    }
}

fn normalize_id_list(values: &mut Vec<String>) {
    let mut seen = HashSet::new();
    let mut normalized_values = Vec::new();
    for value in values.drain(..) {
        let normalized = value.trim().to_string();
        if !normalized.is_empty() && !seen.contains(&normalized) {
            seen.insert(normalized);
            normalized_values.push(value.trim().to_string());
        }
    }
    *values = normalized_values;
}

fn normalized_list_from(arguments: &Value, key: &str) -> Vec<String> {
    let mut values = string_list(arguments, key);
    normalize_id_list(&mut values);
    values
}

fn dedupe_edges(edges: &mut Vec<AssociationEdge>) {
    let mut seen = HashSet::new();
    edges.retain(|edge| {
        seen.insert(format!(
            "{}|{}|{}",
            edge.source_memory_id, edge.relation, edge.target_id
        ))
    });
}

fn replace_id_list_if_present(arguments: &Value, key: &str, target: &mut Vec<String>) {
    if arguments.get(key).is_some() {
        let mut values = string_list(arguments, key);
        normalize_id_list(&mut values);
        *target = values;
    }
}

fn remove_value(values: &mut Vec<String>, value: &str) {
    values.retain(|existing| existing != value);
}

fn dedupe_memory_records(records: &mut Vec<MemoryRecord>) {
    records.sort_by(|left, right| {
        left.memory_id
            .cmp(&right.memory_id)
            .then(left.updated_at.cmp(&right.updated_at))
    });
    records.dedup_by(|left, right| left.memory_id == right.memory_id);
}

fn required_string<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("Missing required string field '{key}'"))
}

fn normalize_action(action: &str) -> Result<&'static str, String> {
    match action.trim().to_ascii_lowercase().as_str() {
        "remember" | "add" | "save" => Ok("remember"),
        "associate" | "plan" | "preview" => Ok("associate"),
        "recluster" | "cluster" | "backfill" => Ok("recluster"),
        "search" | "find" | "query" => Ok("search"),
        "list" | "ls" | "all" | "show" | "list_all" | "list-all" | "list memories"
        | "list_memories" | "show memories" | "show_memories" => Ok("list"),
        "get" | "read" | "show_memory" => Ok("get"),
        "update" | "edit" => Ok("update"),
        "forget" | "archive" | "delete" => Ok("forget"),
        "link" | "relate" => Ok("link"),
        "unlink" | "unrelate" => Ok("unlink"),
        other => Err(format!("Unknown ontomemory action: {other}")),
    }
}

fn optional_string(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToString::to_string)
}

fn normalized_search_query(value: Option<String>) -> Option<String> {
    value.and_then(|query| {
        let trimmed = query.trim();
        if trimmed.is_empty()
            || matches!(
                trimmed.to_ascii_lowercase().as_str(),
                "*" | "all" | "list all" | "everything" | "tutto" | "tutte" | "tutti"
            )
        {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn optional_nonempty_string(value: &Value, key: &str) -> Option<String> {
    optional_string(value, key).and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn optional_bool(value: &Value, key: &str) -> Option<bool> {
    value.get(key).and_then(Value::as_bool)
}

fn optional_usize(value: &Value, key: &str) -> Option<usize> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
}

fn optional_f64(value: &Value, key: &str) -> Option<f64> {
    value.get(key).and_then(Value::as_f64)
}

fn link_target(arguments: &Value, relation: &str) -> Result<String, String> {
    let target = optional_string(arguments, "target_id")
        .or_else(|| {
            if relation == "related_to_skill" {
                optional_string(arguments, "related_skill_id")
            } else if relation == "related_to_intent" {
                optional_string(arguments, "related_intent")
                    .or_else(|| optional_string(arguments, "intent"))
            } else if relation == "related_to_topic" {
                optional_string(arguments, "related_topic_id")
                    .or_else(|| optional_string(arguments, "topic_id"))
            } else {
                optional_string(arguments, "target_memory_id")
            }
        })
        .ok_or_else(|| match relation {
            "related_to_skill" => {
                "Missing required string field 'target_id' (or legacy alias 'related_skill_id')"
                    .to_string()
            }
            "related_to_intent" => {
                "Missing required string field 'target_id' (or alias 'related_intent'/'intent')"
                    .to_string()
            }
            "related_to_topic" => {
                "Missing required string field 'target_id' (or alias 'related_topic_id'/'topic_id')"
                    .to_string()
            }
            _ => "Missing required string field 'target_id' (or legacy alias 'target_memory_id')"
                .to_string(),
        })?;
    Ok(target.trim().to_string())
}

fn string_list(value: &Value, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(ToString::to_string)
                .collect()
        })
        .unwrap_or_default()
}

#[allow(dead_code)]
fn memory_uri(memory_id: &str) -> String {
    format!("{}mem_{}", BASE_URI, sanitize_ref(memory_id))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn remember_search_and_get_memory() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let result = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Always run cargo test after changing the MCP runtime",
                "memory_type": "procedure",
                "scope": "project",
                "related_skill_id": "rust"
            }))
            .unwrap();
        assert!(result.changed);
        let memory_id = result.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let search = store
            .handle_action(&json!({
                "action": "search",
                "query": "cargo test runtime",
                "scope": "both"
            }))
            .unwrap();
        assert_eq!(search.structured["memories"].as_array().unwrap().len(), 1);

        let get = store
            .handle_action(&json!({
                "action": "get",
                "memory_id": memory_id
            }))
            .unwrap();
        assert!(get.compact_text.contains("cargo test"));
    }

    #[test]
    fn archived_memories_are_hidden_by_default() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let result = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Do not hardcode generated ids in tests"
            }))
            .unwrap();
        let memory_id = result.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        store
            .handle_action(&json!({
                "action": "forget",
                "memory_id": memory_id
            }))
            .unwrap();

        let hidden = store
            .handle_action(&json!({
                "action": "search",
                "query": "hardcode ids",
                "scope": "both"
            }))
            .unwrap();
        assert_eq!(hidden.structured["memories"].as_array().unwrap().len(), 0);

        let visible = store
            .handle_action(&json!({
                "action": "search",
                "query": "hardcode ids",
                "scope": "both",
                "include_archived": true
            }))
            .unwrap();
        assert_eq!(visible.structured["memories"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn wildcard_search_lists_filtered_memories() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let remembered = store
            .handle_action(&json!({
                "action": "remember",
                "content": "The user's favorite color is yellow",
                "memory_type": "preference",
                "scope": "global"
            }))
            .unwrap();
        let memory_id = remembered.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let wildcard = store
            .handle_action(&json!({
                "action": "search",
                "query": "*",
                "scope": "global",
                "limit": 100
            }))
            .unwrap();

        let memories = wildcard.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 1);
        assert_eq!(memories[0]["memory_id"], memory_id);
    }

    #[test]
    fn list_action_lists_filtered_memories() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let global = store
            .handle_action(&json!({
                "action": "remember",
                "content": "The user's favorite color is yellow",
                "memory_type": "preference",
                "scope": "global"
            }))
            .unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Run cargo test before committing",
                "memory_type": "procedure",
                "scope": "project"
            }))
            .unwrap();

        let listed = store
            .handle_action(&json!({
                "action": "list",
                "scope": "global",
                "limit": 100
            }))
            .unwrap();

        let memories = listed.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 1);
        assert_eq!(
            memories[0]["memory_id"],
            global.structured["memory"]["memory_id"]
        );
        assert_eq!(memories[0]["scope"], "global");
    }

    #[test]
    fn list_action_accepts_agent_friendly_aliases() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let remembered = store
            .handle_action(&json!({
                "action": "REMEMBER",
                "content": "Prefer action=list when showing all memories",
                "memory_type": "procedure",
                "scope": "global"
            }))
            .unwrap();

        for action in ["LIST", "list_all", "show memories", "all", "ls"] {
            let listed = store
                .handle_action(&json!({
                    "action": action,
                    "scope": "global",
                    "limit": 100
                }))
                .unwrap();
            let memories = listed.structured["memories"].as_array().unwrap();
            assert_eq!(memories.len(), 1);
            assert_eq!(
                memories[0]["memory_id"],
                remembered.structured["memory"]["memory_id"]
            );
        }
    }

    #[test]
    fn serialized_ttl_uses_ontoskills_namespace_and_typed_dates() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let result = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Keep ontology predicates aligned",
                "memory_type": "procedure",
                "rationale": "RDF validators depend on canonical predicates",
                "confidence": 0.9,
                "severity_level": "high",
                "related_skill_id": "marea/search"
            }))
            .unwrap();
        let memory_id = result.structured["memory"]["memory_id"].as_str().unwrap();
        store
            .handle_action(&json!({
                "action": "link",
                "memory_id": memory_id,
                "relation": "depends_on_memory",
                "target_id": "mem-parent",
                "allow_missing_memory_refs": true
            }))
            .unwrap();

        let ttl = fs::read_to_string(store.project_path()).unwrap();
        assert!(ttl.contains("@prefix oc: <https://ontoskills.sh/ontology#>"));
        assert!(ttl.contains("a oc:Memory, oc:ProcedureMemory"));
        assert!(ttl.contains("oc:hasRationale"));
        assert!(!ttl.contains("oc:rationale"));
        assert!(ttl.contains("^^xsd:dateTime"));
        assert!(!ttl.contains("unix:"));
        assert!(ttl.contains("oc:relatedToSkill oc:skill_marea_search"));
        assert!(ttl.contains("oc:dependsOnMemory oc:mem_mem_parent"));
    }

    #[test]
    fn remember_update_link_unlink_related_intents_and_memory_arrays() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let old = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Old memory",
                "related_intents": ["legacy-intent"]
            }))
            .unwrap();
        let old_id = old.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        let parent = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Parent memory"
            }))
            .unwrap();
        let parent_id = parent.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let remembered = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Run the staged deploy chain",
                "memory_type": "procedure",
                "related_skill_ids": ["deploy", "deploy"],
                "depends_on_memory_ids": [parent_id],
                "supersedes_memory_ids": [old_id],
                "related_intents": ["deploy-web", "deploy-web"],
                "related_topic_ids": ["topic-deploy-web"],
                "related_memory_ids": [parent_id]
            }))
            .unwrap();
        let memory_id = remembered.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        assert_eq!(
            remembered.structured["memory"]["related_intents"],
            json!(["deploy-web"])
        );
        assert_eq!(
            remembered.structured["memory"]["supersedes_memory_ids"],
            json!([old_id])
        );

        let replacement_dep = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Replacement dependency"
            }))
            .unwrap();
        let replacement_dep_id = replacement_dep.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        let updated = store
            .handle_action(&json!({
                "action": "update",
                "memory_id": memory_id,
                "related_skill_ids": ["release"],
                "depends_on_memory_ids": [replacement_dep_id],
                "related_topic_ids": ["topic-release-web"],
                "related_memory_ids": [replacement_dep_id],
                "supersedes_memory_ids": [],
                "related_intents": ["release-web"]
            }))
            .unwrap();
        assert_eq!(
            updated.structured["memory"]["related_skill_ids"],
            json!(["release"])
        );
        assert_eq!(
            updated.structured["memory"]["depends_on_memory_ids"],
            json!([replacement_dep_id])
        );
        assert_eq!(
            updated.structured["memory"]["supersedes_memory_ids"],
            json!([])
        );
        assert_eq!(
            updated.structured["memory"]["related_intents"],
            json!(["release-web"])
        );
        assert_eq!(
            updated.structured["memory"]["related_topic_ids"],
            json!(["topic-release-web"])
        );
        assert_eq!(
            updated.structured["memory"]["related_memory_ids"],
            json!([replacement_dep_id])
        );

        let linked = store
            .handle_action(&json!({
                "action": "link",
                "memory_id": memory_id,
                "relation": "related_to_intent",
                "target_id": "hotfix-web"
            }))
            .unwrap();
        assert_eq!(
            linked.structured["memory"]["related_intents"],
            json!(["release-web", "hotfix-web"])
        );

        let unlinked = store
            .handle_action(&json!({
                "action": "unlink",
                "memory_id": memory_id,
                "relation": "related_to_intent",
                "target_id": "release-web"
            }))
            .unwrap();
        assert_eq!(
            unlinked.structured["memory"]["related_intents"],
            json!(["hotfix-web"])
        );

        let linked_topic = store
            .handle_action(&json!({
                "action": "link",
                "memory_id": memory_id,
                "relation": "related_to_topic",
                "target_id": "topic-hotfix-web"
            }))
            .unwrap();
        assert_eq!(
            linked_topic.structured["memory"]["related_topic_ids"],
            json!(["topic-release-web", "topic-hotfix-web"])
        );

        let unlinked_memory = store
            .handle_action(&json!({
                "action": "unlink",
                "memory_id": memory_id,
                "relation": "related_to_memory",
                "target_id": replacement_dep_id
            }))
            .unwrap();
        assert_eq!(
            unlinked_memory.structured["memory"]["related_memory_ids"],
            json!([])
        );
    }

    #[test]
    fn related_intents_roundtrip_and_search_index() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Use the release checklist",
                "related_intents": ["ship-mobile-client"],
                "related_topic_ids": ["topic-mobile-release"]
            }))
            .unwrap();

        let ttl = fs::read_to_string(store.project_path()).unwrap();
        assert!(ttl.contains("oc:relatedIntent \"ship-mobile-client\""));
        assert!(ttl.contains("oc:relatedTopic \"topic-mobile-release\""));

        store.reload().unwrap();
        let matches = store
            .handle_action(&json!({
                "action": "search",
                "query": "ship-mobile-client",
                "scope": "both"
            }))
            .unwrap();
        assert_eq!(matches.structured["memories"].as_array().unwrap().len(), 1);
        assert_eq!(
            matches.structured["memories"][0]["related_intents"],
            json!(["ship-mobile-client"])
        );
        assert_eq!(
            matches.structured["memories"][0]["related_topic_ids"],
            json!(["topic-mobile-release"])
        );
    }

    #[test]
    fn remember_decomposes_compound_thought_and_associate_is_dry_run() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();

        let preview = store
            .handle_action(&json!({
                "action": "associate",
                "content": "Prima verifica Redis; poi deploy backend in staging"
            }))
            .unwrap();
        assert!(!preview.changed);
        assert_eq!(preview.structured["memories"].as_array().unwrap().len(), 2);
        assert_eq!(
            store
                .handle_action(&json!({ "action": "list", "scope": "both" }))
                .unwrap()
                .structured["memories"]
                .as_array()
                .unwrap()
                .len(),
            0
        );

        let remembered = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Prima verifica Redis; poi deploy backend in staging",
                "related_intents": ["deploy-backend"]
            }))
            .unwrap();
        assert!(remembered.changed);
        let memories = remembered.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 2);
        assert_eq!(
            remembered.structured["memory"]["memory_id"],
            memories[0]["memory_id"]
        );
        assert!(
            remembered.structured["edges"]
                .as_array()
                .unwrap()
                .iter()
                .any(|edge| edge["relation"] == "depends_on_memory")
        );

        let ttl = fs::read_to_string(store.project_path()).unwrap();
        assert!(ttl.contains("oc:memoryTitle"));
        store.reload().unwrap();
        let title_match = store
            .handle_action(&json!({
                "action": "search",
                "query": "verifica Redis",
                "scope": "both"
            }))
            .unwrap();
        assert!(
            !title_match.structured["memories"]
                .as_array()
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn association_infers_workflow_intents_context_and_sequence_relations() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();

        let preview = store
            .handle_action(&json!({
                "action": "associate",
                "content": "Prima verifica Redis; poi deploy backend in staging"
            }))
            .unwrap();

        let memories = preview.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 2);
        for memory in memories {
            assert_eq!(memory["applies_to_context"], "staging");
            assert!(
                memory["related_intents"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .any(|intent| intent == "deploy-backend-staging")
            );
        }
        assert!(
            memories[0]["related_intents"]
                .as_array()
                .unwrap()
                .iter()
                .any(|intent| intent == "verifica-redis")
        );
        assert!(preview.structured["edges"].as_array().unwrap().iter().any(
            |edge| edge["relation"] == "depends_on_memory"
                && edge["source_memory_id"] == memories[1]["memory_id"]
                && edge["target_id"] == memories[0]["memory_id"]
        ));
    }

    #[test]
    fn related_skill_ids_roundtrip_across_reload() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        for skill_id in ["marea/search", "test-skill", "snake_case"] {
            store
                .handle_action(&json!({
                    "action": "remember",
                    "content": format!("Roundtrip skill relation for {skill_id}"),
                    "related_skill_id": skill_id
                }))
                .unwrap();
        }

        store.reload().unwrap();

        for skill_id in ["marea/search", "test-skill", "snake_case"] {
            let matches = store
                .handle_action(&json!({
                    "action": "search",
                    "scope": "both",
                    "related_skill_id": skill_id
                }))
                .unwrap();
            assert_eq!(matches.structured["memories"].as_array().unwrap().len(), 1);
            assert_eq!(
                matches.structured["memories"][0]["related_skill_ids"],
                json!([skill_id])
            );
        }
    }

    #[test]
    fn min_confidence_and_case_insensitive_severity_filter_search() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let high = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Escalate destructive data corrections",
                "confidence": 0.95,
                "severity_level": "high"
            }))
            .unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Log routine cleanup reminders",
                "confidence": 0.6,
                "severity_level": "LOW"
            }))
            .unwrap();

        let matches = store
            .handle_action(&json!({
                "action": "search",
                "scope": "both",
                "severity_level": "HIGH",
                "min_confidence": 0.9
            }))
            .unwrap();
        let memories = matches.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 1);
        assert_eq!(
            memories[0]["memory_id"],
            high.structured["memory"]["memory_id"]
        );
    }

    #[test]
    fn include_links_false_does_not_override_explicit_link_flags() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let source = store
            .handle_action(&json!({ "action": "remember", "content": "source memory" }))
            .unwrap();
        let source_id = source.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        let dependency = store
            .handle_action(&json!({ "action": "remember", "content": "dependency memory" }))
            .unwrap();
        let dependency_id = dependency.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        store
            .handle_action(&json!({
                "action": "link",
                "memory_id": source_id,
                "link_type": "depends_on_memory",
                "target_memory_id": dependency_id
            }))
            .unwrap();

        let explicit_flag = store
            .handle_action(&json!({
                "action": "get",
                "memory_id": source_id,
                "include_links": false,
                "include_dependencies": true
            }))
            .unwrap();
        assert_eq!(
            explicit_flag.structured["memory"]["depends_on_memory_ids"],
            json!([dependency_id])
        );
    }

    #[test]
    fn link_accepts_simple_related_skill_id() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let source = store
            .handle_action(&json!({ "action": "remember", "content": "source memory" }))
            .unwrap();
        let source_id = source.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let linked = store
            .handle_action(&json!({
                "action": "link",
                "memory_id": source_id,
                "related_skill_id": "test-skill"
            }))
            .unwrap();

        assert_eq!(
            linked.structured["memory"]["related_skill_ids"],
            json!(["test-skill"])
        );
    }

    #[test]
    fn link_accepts_legacy_aliases_and_get_include_links() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let source = store
            .handle_action(&json!({ "action": "remember", "content": "source memory" }))
            .unwrap();
        let source_id = source.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();
        let dependency = store
            .handle_action(&json!({ "action": "remember", "content": "dependency memory" }))
            .unwrap();
        let dependency_id = dependency.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        store
            .handle_action(&json!({
                "action": "link",
                "memory_id": source_id,
                "link_type": "depends_on_memory",
                "target_memory_id": dependency_id
            }))
            .unwrap();

        let without_links = store
            .handle_action(&json!({
                "action": "get",
                "memory_id": source_id,
                "include_links": false
            }))
            .unwrap();
        assert_eq!(
            without_links.structured["memory"]["depends_on_memory_ids"],
            json!([])
        );

        let with_links = store
            .handle_action(&json!({
                "action": "get",
                "memory_id": source_id,
                "include_links": true
            }))
            .unwrap();
        assert_eq!(
            with_links.structured["memory"]["depends_on_memory_ids"],
            json!([dependency_id])
        );
    }

    #[test]
    fn memory_links_reject_missing_targets_by_default() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let source = store
            .handle_action(&json!({ "action": "remember", "content": "source memory" }))
            .unwrap();
        let source_id = source.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let err = store
            .handle_action(&json!({
                "action": "link",
                "memory_id": source_id,
                "relation": "depends_on_memory",
                "target_id": "mem-missing"
            }))
            .unwrap_err();
        assert!(err.contains("Referenced memory not found"));
    }

    #[test]
    fn remember_merges_duplicate_and_enriches_existing_memory() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let first = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Deploy backend in staging",
                "related_intents": ["deploy-backend-staging"]
            }))
            .unwrap();
        let first_id = first.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let second = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Deploy backend in staging",
                "related_skill_ids": ["backend/deploy"]
            }))
            .unwrap();
        assert_eq!(
            second.structured["memory"]["memory_id"].as_str().unwrap(),
            first_id
        );
        assert_eq!(second.structured["memories"].as_array().unwrap().len(), 0);
        assert_eq!(
            second.structured["merged_memories"][0]["existing_memory_id"],
            first_id
        );

        let listed = store
            .handle_action(&json!({
                "action": "list",
                "scope": "both",
                "limit": 100
            }))
            .unwrap();
        let memories = listed.structured["memories"].as_array().unwrap();
        assert_eq!(memories.len(), 1);
        assert_eq!(memories[0]["related_skill_ids"], json!(["backend/deploy"]));
        assert_eq!(
            memories[0]["related_intents"],
            json!(["deploy-backend-staging"])
        );
    }

    #[test]
    fn remember_auto_links_new_memory_to_existing_topic() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let first = store
            .handle_action(&json!({
                "action": "remember",
                "content": "OntoClaw uses Redis for MCP memory cache"
            }))
            .unwrap();
        let first_id = first.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let second = store
            .handle_action(&json!({
                "action": "remember",
                "content": "For OntoClaw, Redis cache keys must include the project scope"
            }))
            .unwrap();
        let first_topics = first.structured["memory"]["related_topic_ids"]
            .as_array()
            .unwrap();
        let first_topic = first_topics[0].as_str().unwrap();

        assert_eq!(second.structured["memories"].as_array().unwrap().len(), 1);
        assert!(
            second.structured["memory"]["related_topic_ids"]
                .as_array()
                .unwrap()
                .iter()
                .any(|value| value.as_str() == Some(first_topic))
        );
        assert!(
            second.structured["memory"]["related_memory_ids"]
                .as_array()
                .unwrap()
                .iter()
                .any(|value| value.as_str() == Some(first_id.as_str()))
        );
        assert!(
            second.structured["association_quality"]["topic_links"]
                .as_array()
                .unwrap()
                .iter()
                .any(
                    |link| link["target_memory_id"].as_str() == Some(first_id.as_str())
                        && link["relation"].as_str() == Some("related_to_memory")
                )
        );
    }

    #[test]
    fn remember_creates_distinct_topics_for_unrelated_memories() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let first = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Postgres migrations require transaction-safe DDL checks"
            }))
            .unwrap();
        let second = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Figma export assets should keep transparent PNG backgrounds"
            }))
            .unwrap();

        assert_ne!(
            first.structured["memory"]["related_topic_ids"],
            second.structured["memory"]["related_topic_ids"]
        );
        assert_eq!(second.structured["memory"]["related_memory_ids"], json!([]));
    }

    #[test]
    fn remember_uses_multi_topic_bridge_without_merging_clusters() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let work = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Per lavoro sono ingegnere informatico",
                "scope": "global"
            }))
            .unwrap();
        let work_id = work.structured["memory"]["memory_id"].as_str().unwrap();
        assert_eq!(
            work.structured["memory"]["related_topic_ids"],
            json!(["topic-lavoro"])
        );

        let bike = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Vorrei acquistare una moto di 600cc",
                "scope": "global"
            }))
            .unwrap();
        let bike_id = bike.structured["memory"]["memory_id"].as_str().unwrap();
        assert!(
            bike.structured["memory"]["related_topic_ids"]
                .as_array()
                .unwrap()
                .iter()
                .any(|topic| topic == "topic-mobilita")
        );
        assert!(
            bike.structured["memory"]["related_topic_ids"]
                .as_array()
                .unwrap()
                .iter()
                .any(|topic| topic == "topic-moto")
        );

        let bridge = store
            .handle_action(&json!({
                "action": "remember",
                "content": "A lavoro ci vado solo in moto, altrimenti se piove uso la macchina",
                "scope": "global"
            }))
            .unwrap();
        let bridge_topics = bridge.structured["memory"]["related_topic_ids"]
            .as_array()
            .unwrap();
        assert!(bridge_topics.iter().any(|topic| topic == "topic-lavoro"));
        assert!(bridge_topics.iter().any(|topic| topic == "topic-mobilita"));
        assert!(bridge_topics.iter().any(|topic| topic == "topic-moto"));

        let bridge_links = bridge.structured["memory"]["related_memory_ids"]
            .as_array()
            .unwrap();
        assert!(
            bridge_links
                .iter()
                .any(|memory| memory.as_str() == Some(work_id))
        );
        assert!(
            bridge_links
                .iter()
                .any(|memory| memory.as_str() == Some(bike_id))
        );

        let work_after = store
            .handle_action(&json!({
                "action": "get",
                "memory_id": work_id
            }))
            .unwrap();
        assert_eq!(
            work_after.structured["memory"]["related_topic_ids"],
            json!(["topic-lavoro"])
        );
    }

    #[test]
    fn recluster_backfills_existing_memories_and_is_idempotent() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Uso la macchina per tratte lunghe",
                "auto_link_related": false
            }))
            .unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Vorrei acquistare una moto di 600cc",
                "auto_link_related": false
            }))
            .unwrap();
        let ttl_before = fs::read_to_string(store.project_path()).unwrap();

        let preview = store
            .handle_action(&json!({
                "action": "recluster",
                "dry_run": true
            }))
            .unwrap();
        assert!(!preview.changed);
        assert!(preview.structured["changed_count"].as_u64().unwrap() >= 2);
        assert_eq!(
            fs::read_to_string(store.project_path()).unwrap(),
            ttl_before
        );

        let applied = store
            .handle_action(&json!({
                "action": "recluster",
                "apply": true
            }))
            .unwrap();
        assert!(applied.changed);
        let ttl_after = fs::read_to_string(store.project_path()).unwrap();
        assert!(ttl_after.contains("oc:relatedTopic \"topic-mobilita\""));

        let second = store
            .handle_action(&json!({
                "action": "recluster",
                "apply": true
            }))
            .unwrap();
        assert_eq!(second.structured["changed_count"], 0);
    }

    #[test]
    fn remember_rejects_duplicate_when_policy_is_reject() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Use the staging bucket",
                "related_intents": ["staging-bucket"]
            }))
            .unwrap();

        let err = store
            .handle_action(&json!({
                "action": "remember",
                "content": "Use the staging bucket",
                "dedupe_policy": "reject"
            }))
            .unwrap_err();
        assert!(err.contains("Duplicate memory detected"));
    }

    #[test]
    fn remember_auto_links_or_inboxes_isolated_memory() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let remembered = store
            .handle_action(&json!({
                "action": "remember",
                "content": "foobar",
                "auto_associate": false,
                "decompose": false
            }))
            .unwrap();

        assert_eq!(
            remembered.structured["memory"]["related_topic_ids"],
            json!(["topic-foobar"])
        );
        assert!(
            remembered.structured["association_quality"]["topic_created"]
                .as_array()
                .unwrap()
                .iter()
                .any(|value| value["topic_id"] == "topic-foobar")
        );
    }

    #[test]
    fn remember_rejects_isolated_memory_when_policy_is_reject() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let err = store
            .handle_action(&json!({
                "action": "remember",
                "content": "foobar",
                "auto_associate": false,
                "decompose": false,
                "auto_link_related": false,
                "isolation_policy": "reject"
            }))
            .unwrap_err();
        assert!(err.contains("Memory would be isolated"));
    }

    #[test]
    fn reload_before_write_preserves_external_file_changes() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        store
            .handle_action(&json!({ "action": "remember", "content": "first memory" }))
            .unwrap();

        let mut external = store.clone();
        external.reload().unwrap();
        external
            .handle_action(&json!({ "action": "remember", "content": "external memory" }))
            .unwrap();

        store
            .handle_action(&json!({ "action": "remember", "content": "second memory" }))
            .unwrap();

        let ttl = fs::read_to_string(store.project_path()).unwrap();
        assert!(ttl.contains("first memory"));
        assert!(ttl.contains("external memory"));
        assert!(ttl.contains("second memory"));
    }

    #[test]
    fn read_actions_reload_external_writes_from_other_agents() {
        let dir = tempdir().unwrap();
        let root = dir.path().join("memories");
        let mut agent_a = MemoryStore::load(root.clone(), "project-a".to_string()).unwrap();
        let mut agent_b = MemoryStore::load(root, "project-a".to_string()).unwrap();

        let remembered = agent_a
            .handle_action(&json!({
                "action": "remember",
                "content": "Shared memory should be visible without restarting agents",
                "memory_type": "fact",
                "scope": "global"
            }))
            .unwrap();
        let memory_id = remembered.structured["memory"]["memory_id"]
            .as_str()
            .unwrap()
            .to_string();

        let listed = agent_b
            .handle_action(&json!({
                "action": "list",
                "scope": "global",
                "format": "raw"
            }))
            .unwrap();
        assert_eq!(
            listed.structured["memories"][0]["memory_id"],
            json!(memory_id)
        );

        let fetched = agent_b
            .handle_action(&json!({
                "action": "get",
                "memory_id": memory_id
            }))
            .unwrap();
        assert_eq!(
            fetched.structured["memory"]["content"],
            "Shared memory should be visible without restarting agents"
        );
    }
}
