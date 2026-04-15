mod catalog;
mod bm25_engine;
#[cfg(feature = "embeddings")]
mod embeddings;
mod schema;

use std::env;
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};

use catalog::{
    Catalog, CatalogError, EpistemicQueryParams, EvaluateExecutionPlanParams, SearchSkillsParams,
    SkillType,
};
use bm25_engine::Bm25Engine;
#[cfg(feature = "embeddings")]
use embeddings::EmbeddingEngine;
use schema::get_schema_resource;
use serde::Deserialize;
use serde_json::{Value, json};

const SERVER_NAME: &str = "ontomcp";
const SERVER_VERSION: &str = env!("CARGO_PKG_VERSION");
const DEFAULT_PROTOCOL_VERSION: &str = "2025-11-25";
const SUPPORTED_PROTOCOLS: &[&str] = &["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

#[derive(Debug, Deserialize)]
struct JsonRpcRequest {
    #[allow(dead_code)]
    jsonrpc: Option<String>,
    id: Option<Value>,
    method: String,
    params: Option<Value>,
}

#[derive(Clone, Copy)]
enum WireMode {
    Framed,
    LineDelimited,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let ontology_root = parse_ontology_root();
    let catalog = Catalog::load(&ontology_root)?;

    // Build BM25 engine (always available — in-memory from Catalog data)
    let bm25_engine = Bm25Engine::from_catalog(&catalog).unwrap_or_else(|e| {
        eprintln!("[ontomcp] Warning: Failed to build BM25 engine: {}", e);
        std::process::exit(1);
    });
    eprintln!("[ontomcp] BM25 search engine ready");

    // Load embedding engine (optional - requires feature flag + model files)
    #[cfg(feature = "embeddings")]
    let mut embedding_engine: Option<EmbeddingEngine> = {
        let embeddings_dir = ontology_root.join("system").join("embeddings");
        if embeddings_dir.join("model.onnx").exists() {
            match EmbeddingEngine::load(&embeddings_dir, ontology_root) {
                Ok(engine) => {
                    eprintln!("[ontomcp] Loaded embedding engine with {} intents",
                        engine.intent_count());
                    Some(engine)
                }
                Err(e) => {
                    eprintln!("[ontomcp] Warning: Failed to load embeddings: {}", e);
                    None
                }
            }
        } else {
            eprintln!("[ontomcp] No embedding model found — using BM25 only");
            None
        }
    };

    #[cfg(not(feature = "embeddings"))]
    let mut embedding_engine: Option<()> = None;

    // Wire trust tiers from catalog into embedding engine for hybrid scoring
    #[cfg(feature = "embeddings")]
    if let Some(ref mut engine) = embedding_engine {
        let tiers = catalog.trust_tier_map();
        engine.set_trust_tiers(tiers);
    }

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut reader = BufReader::new(stdin.lock());
    let mut writer = stdout.lock();
    let mut initialized = false;

    while let Some((message, mode)) = read_message(&mut reader)? {
        let wire_mode = mode;
        let request: JsonRpcRequest = match serde_json::from_slice(&message) {
            Ok(request) => request,
            Err(err) => {
                write_response(
                    &mut writer,
                    wire_mode,
                    &json!({
                        "jsonrpc": "2.0",
                        "id": Value::Null,
                        "error": {
                            "code": -32700,
                            "message": format!("Parse error: {err}")
                        }
                    }),
                )?;
                continue;
            }
        };

        match request.method.as_str() {
            "initialize" => {
                let requested_version = request
                    .params
                    .as_ref()
                    .and_then(|params| params.get("protocolVersion"))
                    .and_then(Value::as_str)
                    .unwrap_or(DEFAULT_PROTOCOL_VERSION);

                let protocol_version = if SUPPORTED_PROTOCOLS.contains(&requested_version) {
                    requested_version
                } else {
                    DEFAULT_PROTOCOL_VERSION
                };

                initialized = true;
                let result = json!({
                    "protocolVersion": protocol_version,
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    },
                    "capabilities": {
                        "prompts": {
                            "listChanged": false
                        },
                        "resources": {
                            "listChanged": false,
                            "subscribe": false
                        },
                        "tools": {
                            "listChanged": false
                        }
                    },
                    "instructions": "Use the consolidated OntoSkills tools to discover skills, retrieve full skill context, evaluate execution plans, and query epistemic rules."
                });
                respond_ok(&mut writer, wire_mode, request.id, result)?;
            }
            "notifications/initialized" => {
                initialized = true;
            }
            "ping" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                respond_ok(&mut writer, wire_mode, request.id, json!({}))?;
            }
            "tools/list" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                respond_ok(
                    &mut writer,
                    wire_mode,
                    request.id,
                    json!({ "tools": tool_definitions() }),
                )?;
            }
            "resources/list" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                let resources = vec![json!({
                    "uri": "ontology://schema",
                    "name": "Ontology Schema",
                    "description": "Compact schema for querying the ontology",
                    "mimeType": "application/json"
                })];
                respond_ok(
                    &mut writer,
                    wire_mode,
                    request.id,
                    json!({ "resources": resources }),
                )?;
            }
            "resources/templates/list" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                respond_ok(
                    &mut writer,
                    wire_mode,
                    request.id,
                    json!({ "resourceTemplates": [] }),
                )?;
            }
            "prompts/list" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                respond_ok(&mut writer, wire_mode, request.id, json!({ "prompts": [] }))?;
            }
            "resources/read" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                let uri = request.params
                    .as_ref()
                    .and_then(|p| p.get("uri"))
                    .and_then(|u| u.as_str())
                    .ok_or_else(|| "Missing uri parameter".to_string());

                let uri = match uri {
                    Ok(u) => u,
                    Err(e) => {
                        respond_error(&mut writer, wire_mode, request.id, -32602, &e)?;
                        continue;
                    }
                };

                match uri {
                    "ontology://schema" => {
                        let schema_text = match serde_json::to_string(&get_schema_resource()) {
                            Ok(text) => text,
                            Err(e) => {
                                respond_error(
                                    &mut writer,
                                    wire_mode,
                                    request.id,
                                    -32603,
                                    &format!("Failed to serialize schema: {}", e),
                                )?;
                                continue;
                            }
                        };
                        respond_ok(
                            &mut writer,
                            wire_mode,
                            request.id,
                            json!({
                                "contents": [{
                                    "uri": uri,
                                    "mimeType": "application/json",
                                    "text": schema_text
                                }]
                            }),
                        )?;
                    }
                    _ => {
                        respond_error(
                            &mut writer,
                            wire_mode,
                            request.id,
                            -32602,
                            &format!("Unknown resource: {}", uri),
                        )?;
                    }
                }
            }
            "tools/call" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                let result = handle_tool_call(&catalog, &bm25_engine, embedding_engine.as_mut(), request.params.unwrap_or(Value::Null));
                match result {
                    Ok(result) => respond_ok(&mut writer, wire_mode, request.id, result)?,
                    Err(err) => respond_error(&mut writer, wire_mode, request.id, -32602, &err)?,
                }
            }
            _ => {
                if request.id.is_some() {
                    respond_error(
                        &mut writer,
                        wire_mode,
                        request.id,
                        -32601,
                        "Method not found",
                    )?;
                }
            }
        }
    }

    Ok(())
}

fn parse_ontology_root() -> PathBuf {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--ontology-root" {
            if let Some(path) = args.next() {
                return PathBuf::from(path);
            }
        }
    }

    if let Ok(path) = env::var("ONTOMCP_ONTOLOGY_ROOT") {
        return PathBuf::from(path);
    }
    if let Ok(path) = env::var("ONTOSKILLS_MCP_ONTOLOGY_ROOT") {
        return PathBuf::from(path);
    }

    discover_ontology_root().unwrap_or_else(default_ontology_root)
}

fn discover_ontology_root() -> Option<PathBuf> {
    let cwd = env::current_dir().ok()?;

    for candidate in candidate_roots(&cwd) {
        if candidate.exists() && has_ontology_data(&candidate) {
            return Some(candidate);
        }
    }

    let home_default = default_ontology_root();

    // Prefer new path only if it contains actual data
    if home_default.exists() && has_ontology_data(&home_default) {
        return Some(home_default);
    }

    // Fallback to legacy path for backward compatibility
    let legacy_home = env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join(".ontoskills").join("ontoskills"));
    if let Some(ref legacy) = legacy_home {
        if legacy.exists() && has_ontology_data(legacy) {
            eprintln!("[ontomcp] Warning: Using legacy ontology path {:?}. Consider migrating to {:?}",
                legacy, home_default);
            return Some(legacy.clone());
        }
    }

    // Fall back to home_default even if empty (let Catalog::load handle the error)
    if home_default.exists() {
        return Some(home_default);
    }

    None
}

fn has_ontology_data(path: &PathBuf) -> bool {
    // Check for manifest files in system/
    path.join("system").join("index.enabled.ttl").exists()
        || path.join("system").join("index.ttl").exists()
        // Also check for any .ttl files recursively as a fallback
        || contains_ttl_recursive(path, 3)
}

fn contains_ttl_recursive(path: &Path, max_depth: usize) -> bool {
    if max_depth == 0 {
        return false;
    }
    let entries = match std::fs::read_dir(path) {
        Ok(entries) => entries,
        Err(_) => return false,
    };
    for entry_result in entries {
        let entry = match entry_result {
            Ok(e) => e,
            Err(_) => continue,
        };
        let entry_path = entry.path();
        if entry_path.is_dir() {
            if contains_ttl_recursive(&entry_path, max_depth.saturating_sub(1)) {
                return true;
            }
        } else if entry_path
            .extension()
            .map_or(false, |ext| ext == "ttl")
        {
            return true;
        }
    }
    false
}

fn default_ontology_root() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join(".ontoskills").join("ontologies"))
        .unwrap_or_else(|| PathBuf::from("ontologies"))
}

fn candidate_roots(start: &PathBuf) -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    for dir in start.ancestors() {
        candidates.push(dir.join("ontoskills"));
        candidates.push(dir.join("../ontoskills"));
    }

    candidates
}

fn ensure_initialized(
    writer: &mut dyn Write,
    wire_mode: WireMode,
    request: &JsonRpcRequest,
    initialized: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if initialized {
        return Ok(());
    }

    if request.id.is_some() {
        respond_error(
            writer,
            wire_mode,
            request.id.clone(),
            -32002,
            "Server not initialized",
        )?;
    }
    Err("Server not initialized".into())
}

fn handle_tool_call(
    catalog: &Catalog,
    bm25_engine: &Bm25Engine,
    #[cfg(feature = "embeddings")] embedding_engine: Option<&mut EmbeddingEngine>,
    #[cfg(not(feature = "embeddings"))] _embedding_engine: Option<&mut ()>,
    params: Value,
) -> Result<Value, String> {
    let tool_name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| "Missing tool name".to_string())?;
    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!({}));

    let structured = match tool_name {
        "search" => {
            // Dispatch based on which parameters are provided:
            // - query → semantic search if embeddings available, otherwise BM25
            // - alias → alias resolution
            // - otherwise → structured skill search
            // query and alias are mutually exclusive.
            let has_query = arguments.get("query").and_then(Value::as_str).is_some();
            let has_alias = arguments.get("alias").and_then(Value::as_str).is_some();

            if has_query && has_alias {
                return Err("Parameters 'query' and 'alias' are mutually exclusive. Provide one or the other.".to_string());
            }

            if has_query {
                let query = arguments
                    .get("query")
                    .and_then(Value::as_str)
                    .ok_or_else(|| "query required".to_string())?;
                let top_k = arguments
                    .get("top_k")
                    .and_then(Value::as_u64)
                    .unwrap_or(5) as usize;

                // Prefer semantic search when embeddings are available
                #[cfg(feature = "embeddings")]
                if let Some(engine) = embedding_engine {
                    let matches = engine
                        .search(query, top_k)
                        .map_err(|e| format!("Search failed: {}", e))?;
                    if !matches.is_empty() {
                        return Ok(json!({
                            "mode": "semantic",
                            "query": query,
                            "matches": matches.iter().map(|m| json!({
                                "intent": m.intent,
                                "score": m.score,
                                "skills": m.skills
                            })).collect::<Vec<_>>()
                        }));
                    }
                }

                // Fallback: BM25 keyword search (always available)
                let bm25_results = bm25_engine.search(query, top_k);
                json!({
                    "mode": "bm25",
                    "query": query,
                    "results": bm25_results.iter().map(|m| json!({
                        "skill_id": m.skill_id,
                        "qualified_id": m.qualified_id,
                        "score": m.score,
                        "matched_by": m.matched_by,
                        "intents": m.intents,
                        "aliases": m.aliases,
                        "trust_tier": m.trust_tier
                    })).collect::<Vec<_>>()
                })
            } else if has_alias {
                let alias = required_string(&arguments, "alias")?;
                let skills = catalog.resolve_alias(&alias).map_err(public_error)?;
                json!({ "mode": "alias", "alias": alias, "skills": skills })
            } else {
                let params = SearchSkillsParams {
                    intent: optional_string(&arguments, "intent"),
                    requires_state: optional_string(&arguments, "requires_state"),
                    yields_state: optional_string(&arguments, "yields_state"),
                    skill_type: optional_skill_type(&arguments, "skill_type")?,
                    category: optional_string(&arguments, "category"),
                    is_user_invocable: optional_bool(&arguments, "is_user_invocable"),
                    limit: optional_usize(&arguments, "limit").unwrap_or(25),
                };
                json!({ "mode": "structured", "skills": catalog.search_skills(params).map_err(public_error)? })
            }
        }
        "get_skill_context" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            let include_inherited_knowledge =
                optional_bool(&arguments, "include_inherited_knowledge").unwrap_or(true);
            json!(
                catalog
                    .get_skill_context(skill_id, include_inherited_knowledge)
                    .map_err(public_error)?
            )
        }
        "evaluate_execution_plan" => {
            let params = EvaluateExecutionPlanParams {
                intent: optional_string(&arguments, "intent"),
                skill_id: optional_string(&arguments, "skill_id"),
                current_states: string_list(&arguments, "current_states"),
                max_depth: optional_usize(&arguments, "max_depth").unwrap_or(10),
            };
            json!(
                catalog
                    .evaluate_execution_plan(params)
                    .map_err(public_error)?
            )
        }
        "query_epistemic_rules" => {
            let params = EpistemicQueryParams {
                skill_id: optional_string(&arguments, "skill_id"),
                kind: optional_string(&arguments, "kind"),
                dimension: optional_string(&arguments, "dimension"),
                severity_level: optional_string(&arguments, "severity_level"),
                applies_to_context: optional_string(&arguments, "applies_to_context"),
                include_inherited: optional_bool(&arguments, "include_inherited").unwrap_or(true),
                limit: optional_usize(&arguments, "limit").unwrap_or(25),
            };
            json!(
                catalog
                    .query_epistemic_rules(params)
                    .map_err(public_error)?
            )
        }
        _ => return Err(format!("Unknown tool: {tool_name}")),
    };

    let structured_content = normalize_structured_content(structured.clone());

    Ok(json!({
        "content": [
            {
                "type": "text",
                "text": serde_json::to_string_pretty(&structured).unwrap_or_else(|_| structured.to_string())
            }
        ],
        "structuredContent": structured_content,
        "isError": false
    }))
}

fn normalize_structured_content(value: Value) -> Value {
    match value {
        Value::Object(_) => value,
        other => json!({ "result": other }),
    }
}

fn public_error(err: CatalogError) -> String {
    match err {
        CatalogError::SkillNotFound(skill_id) => format!("Skill not found: {skill_id}"),
        CatalogError::InvalidInput(message) => format!("Invalid input: {message}"),
        CatalogError::InvalidState(state) => format!("Invalid state value: {state}"),
        CatalogError::MissingOntologyRoot(_) => "Ontology root not found".to_string(),
        CatalogError::Io(_) | CatalogError::Walk(_) | CatalogError::Oxigraph(_) => {
            "Ontology query failed".to_string()
        }
    }
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

fn optional_bool(value: &Value, key: &str) -> Option<bool> {
    value.get(key).and_then(Value::as_bool)
}

fn optional_usize(value: &Value, key: &str) -> Option<usize> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
}

fn optional_skill_type(value: &Value, key: &str) -> Result<Option<SkillType>, String> {
    let Some(raw) = value.get(key).and_then(Value::as_str) else {
        return Ok(None);
    };

    match raw.trim().to_ascii_lowercase().as_str() {
        "executable" => Ok(Some(SkillType::Executable)),
        "declarative" => Ok(Some(SkillType::Declarative)),
        _ => Err(format!(
            "Invalid skill_type '{raw}'. Expected 'executable' or 'declarative'"
        )),
    }
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

fn read_message(reader: &mut impl BufRead) -> io::Result<Option<(Vec<u8>, WireMode)>> {
    let mut content_length = None;
    let mut line = String::new();

    line.clear();
    let read = reader.read_line(&mut line)?;
    if read == 0 {
        return Ok(None);
    }

    let mut trimmed = line.trim_end_matches(['\r', '\n']).to_string();
    if trimmed.starts_with('{') {
        return Ok(Some((trimmed.into_bytes(), WireMode::LineDelimited)));
    }

    loop {
        if trimmed.is_empty() {
            break;
        }

        if let Some(value) = trimmed.strip_prefix("Content-Length:") {
            content_length = value.trim().parse::<usize>().ok();
        }

        line.clear();
        let read = reader.read_line(&mut line)?;
        if read == 0 {
            break;
        }
        trimmed = line.trim_end_matches(['\r', '\n']).to_string();
    }

    let content_length = content_length.ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "Missing Content-Length header")
    })?;

    let mut buffer = vec![0; content_length];
    reader.read_exact(&mut buffer)?;
    Ok(Some((buffer, WireMode::Framed)))
}

fn write_response(writer: &mut dyn Write, wire_mode: WireMode, value: &Value) -> io::Result<()> {
    let body = serde_json::to_vec(value).map_err(io::Error::other)?;
    match wire_mode {
        WireMode::Framed => {
            write!(writer, "Content-Length: {}\r\n\r\n", body.len())?;
            writer.write_all(&body)?;
            writer.flush()
        }
        WireMode::LineDelimited => {
            writer.write_all(&body)?;
            writer.write_all(b"\n")?;
            writer.flush()
        }
    }
}

fn respond_ok(
    writer: &mut dyn Write,
    wire_mode: WireMode,
    id: Option<Value>,
    result: Value,
) -> io::Result<()> {
    write_response(
        writer,
        wire_mode,
        &json!({
            "jsonrpc": "2.0",
            "id": id.unwrap_or(Value::Null),
            "result": result
        }),
    )
}

fn respond_error(
    writer: &mut dyn Write,
    wire_mode: WireMode,
    id: Option<Value>,
    code: i64,
    message: &str,
) -> io::Result<()> {
    write_response(
        writer,
        wire_mode,
        &json!({
            "jsonrpc": "2.0",
            "id": id.unwrap_or(Value::Null),
            "error": {
                "code": code,
                "message": message
            }
        }),
    )
}

fn tool_definitions() -> Vec<Value> {
    vec![
        tool(
            "search",
            "Search skills by keyword query, alias, or structured filters. If 'query' is provided, uses semantic search when embeddings are available, otherwise falls back to BM25 keyword search. If 'alias' is provided, resolves the alias to matching skills. Otherwise, filters skills by intent, state, type, category, and user-invocability.",
            json!({
                "type": "object",
                "properties": {
                    "query": { "type": "string", "description": "Natural language query for semantic intent search (e.g., 'create a pdf document')" },
                    "alias": { "type": "string", "description": "Alias to resolve (case-insensitive)" },
                    "top_k": { "type": "integer", "description": "Number of semantic results (default 5)", "default": 5 },
                    "intent": { "type": "string", "description": "Filter by resolved intent" },
                    "requires_state": { "type": "string", "description": "State URI or oc:StateName compact value." },
                    "yields_state": { "type": "string", "description": "State URI or oc:StateName compact value." },
                    "skill_type": { "type": "string", "enum": ["executable", "declarative"] },
                    "category": { "type": "string", "description": "Filter by skill category (e.g., automation, document, marketing)." },
                    "is_user_invocable": { "type": "boolean", "description": "Filter by whether the skill is directly invocable by users." },
                    "limit": { "type": "integer", "minimum": 1, "maximum": 100 }
                }
            }),
        ),
        tool(
            "get_skill_context",
            "Fetch the full execution context for a skill, including requirements, transitions, payload, dependencies, and knowledge nodes.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea/office/xlsx'." },
                    "include_inherited_knowledge": { "type": "boolean", "default": true }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "evaluate_execution_plan",
            "Evaluate whether an intent or skill can be executed from the current states and return the full plan plus warnings.",
            json!({
                "type": "object",
                "properties": {
                    "intent": { "type": "string" },
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea/office/xlsx'." },
                    "current_states": {
                        "type": "array",
                        "items": { "type": "string" }
                    },
                    "max_depth": { "type": "integer", "minimum": 1, "maximum": 10 }
                }
            }),
        ),
        tool(
            "query_epistemic_rules",
            "Query normalized knowledge nodes with guided filters such as kind, dimension, severity, context, and skill.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea/office/xlsx'." },
                    "kind": { "type": "string" },
                    "dimension": { "type": "string" },
                    "severity_level": { "type": "string" },
                    "applies_to_context": { "type": "string" },
                    "include_inherited": { "type": "boolean", "default": true },
                    "limit": { "type": "integer", "minimum": 1, "maximum": 100 }
                }
            }),
        ),
    ]
}

fn tool(name: &str, description: &str, input_schema: Value) -> Value {
    json!({
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    })
}
