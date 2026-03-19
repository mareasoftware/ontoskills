mod catalog;

use std::env;
use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;

use catalog::{
    Catalog, CatalogError, EpistemicQueryParams, EvaluateExecutionPlanParams, SearchSkillsParams,
    SkillType,
};
use serde::Deserialize;
use serde_json::{Value, json};

const SERVER_NAME: &str = "ontoskills-mcp";
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
                respond_ok(
                    &mut writer,
                    wire_mode,
                    request.id,
                    json!({ "resources": [] }),
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
            "tools/call" => {
                ensure_initialized(&mut writer, wire_mode, &request, initialized)?;
                let result = handle_tool_call(&catalog, request.params.unwrap_or(Value::Null));
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

    if let Ok(path) = env::var("ONTOSKILLS_MCP_ONTOLOGY_ROOT") {
        return PathBuf::from(path);
    }

    discover_ontology_root().unwrap_or_else(default_ontology_root)
}

fn discover_ontology_root() -> Option<PathBuf> {
    let cwd = env::current_dir().ok()?;

    for candidate in candidate_roots(&cwd) {
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let home_default = default_ontology_root();
    if home_default.exists() {
        return Some(home_default);
    }

    None
}

fn default_ontology_root() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join(".ontoskills").join("ontoskills"))
        .unwrap_or_else(|| PathBuf::from("ontoskills"))
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

fn handle_tool_call(catalog: &Catalog, params: Value) -> Result<Value, String> {
    let tool_name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or_else(|| "Missing tool name".to_string())?;
    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!({}));

    let structured = match tool_name {
        "search_skills" => {
            let params = SearchSkillsParams {
                intent: optional_string(&arguments, "intent"),
                requires_state: optional_string(&arguments, "requires_state"),
                yields_state: optional_string(&arguments, "yields_state"),
                skill_type: optional_skill_type(&arguments, "skill_type")?,
                limit: optional_usize(&arguments, "limit").unwrap_or(25),
            };
            json!(catalog.search_skills(params).map_err(public_error)?)
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
            "search_skills",
            "Discover skills with optional filters for intent, required state, yielded state, and skill type.",
            json!({
                "type": "object",
                "properties": {
                    "intent": { "type": "string" },
                    "requires_state": { "type": "string", "description": "State URI or oc:StateName compact value." },
                    "yields_state": { "type": "string", "description": "State URI or oc:StateName compact value." },
                    "skill_type": { "type": "string", "enum": ["executable", "declarative"] },
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
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea.office/xlsx'." },
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
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea.office/xlsx'." },
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
                    "skill_id": { "type": "string", "description": "Short id like 'xlsx' or qualified id like 'marea.office/xlsx'." },
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
