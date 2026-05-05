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
    pub depends_on_memory_ids: Vec<String>,
    pub supersedes_memory_ids: Vec<String>,
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

    pub fn handle_action(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let action = required_string(arguments, "action")?;
        match action {
            "remember" => self.remember(arguments),
            "search" => self.search_action(arguments),
            "get" => self.get_action(arguments),
            "update" => self.update(arguments),
            "forget" => self.forget(arguments),
            "link" => self.link(arguments),
            other => Err(format!("Unknown ontomemory action: {other}")),
        }
    }

    pub fn relevant_memories_for_query(
        &self,
        query: &str,
        related_skill_ids: &[String],
        limit: usize,
    ) -> Vec<MemorySearchResult> {
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
        results
    }

    fn remember(&mut self, arguments: &Value) -> Result<MemoryActionResult, String> {
        self.reload()?;
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

        let record = MemoryRecord {
            memory_id,
            memory_type,
            scope,
            content,
            applies_to_context: optional_nonempty_string(arguments, "applies_to_context"),
            rationale: optional_nonempty_string(arguments, "rationale"),
            severity_level,
            confidence,
            source: optional_nonempty_string(arguments, "source"),
            related_skill_ids,
            depends_on_memory_ids: depends_on,
            supersedes_memory_ids: vec![],
            created_at: now.clone(),
            updated_at: now,
            is_archived: false,
        };

        self.records.push(record.clone());
        self.persist_all()?;
        Ok(MemoryActionResult::changed(
            json!({ "memory": record }),
            compact_one("Remembered", &record),
        ))
    }

    fn search_action(&self, arguments: &Value) -> Result<MemoryActionResult, String> {
        let mut params = MemorySearchParams::default();
        params.query = optional_string(arguments, "query");
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
        if let Some(memory_type) = optional_string(arguments, "memory_type") {
            self.records[index].memory_type = normalize_memory_type(&memory_type)?;
        }
        if arguments.get("applies_to_context").is_some() {
            self.records[index].applies_to_context =
                optional_nonempty_string(arguments, "applies_to_context");
        }
        if arguments.get("rationale").is_some() {
            self.records[index].rationale = optional_nonempty_string(arguments, "rationale");
        }
        if let Some(severity) = optional_string(arguments, "severity_level") {
            self.records[index].severity_level = Some(normalize_severity(&severity)?);
        }
        if let Some(confidence) = optional_f64(arguments, "confidence") {
            self.records[index].confidence = Some(validate_confidence(confidence)?);
        }
        if arguments.get("source").is_some() {
            self.records[index].source = optional_nonempty_string(arguments, "source");
        }
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
            .ok_or_else(|| {
                "Missing required string field 'relation' (or legacy alias 'link_type')".to_string()
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
                push_unique(&mut self.records[index].depends_on_memory_ids, &target_id)
            }
            "supersedes_memory" => {
                push_unique(&mut self.records[index].supersedes_memory_ids, &target_id)
            }
            "related_to_skill" => {
                push_unique(&mut self.records[index].related_skill_ids, &target_id)
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
                .collect()
        } else {
            candidates
                .drain(..)
                .map(|record| MemorySearchResult {
                    memory: record.clone(),
                    score: memory_quality_bonus(record),
                })
                .collect()
        };

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
            memory.content
        ));
    }
    lines.join("\n")
}

pub fn compact_one(label: &str, memory: &MemoryRecord) -> String {
    let mut lines = vec![format!(
        "{}: {} [{}:{}]",
        label, memory.memory_id, memory.scope, memory.memory_type
    )];
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
        memory_type: memory_type_from_block(first),
        scope: "project".to_string(),
        content: String::new(),
        applies_to_context: None,
        rationale: None,
        severity_level: None,
        confidence: None,
        source: None,
        related_skill_ids: vec![],
        depends_on_memory_ids: vec![],
        supersedes_memory_ids: vec![],
        created_at: String::new(),
        updated_at: String::new(),
        is_archived: false,
    };

    for line in lines {
        if line.contains("oc:memoryId ") {
            record.memory_id = extract_literal(line)?;
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
        } else if line.contains("oc:relatedToSkill ") {
            if let Some(value) = extract_prefixed_object(line, "oc:skill_") {
                record.related_skill_ids.push(desanitize_ref(&value));
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
    normalize_id_list(&mut record.related_skill_ids);
    normalize_id_list(&mut record.depends_on_memory_ids);
    normalize_id_list(&mut record.supersedes_memory_ids);
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
    parts.join(" ")
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

fn optional_string(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(ToString::to_string)
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
            } else {
                optional_string(arguments, "target_memory_id")
            }
        })
        .ok_or_else(|| match relation {
            "related_to_skill" => {
                "Missing required string field 'target_id' (or legacy alias 'related_skill_id')"
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
                "target_id": "mem-parent"
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
    fn related_skill_ids_roundtrip_across_reload() {
        let dir = tempdir().unwrap();
        let mut store =
            MemoryStore::load(dir.path().join("memories"), "project-a".to_string()).unwrap();
        let skill_id = "marea/search";
        store
            .handle_action(&json!({
                "action": "remember",
                "content": "Roundtrip skill relation",
                "related_skill_id": skill_id
            }))
            .unwrap();

        store.reload().unwrap();

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
}
