mod catalog;

use std::env;
use std::io::{self, BufRead, BufReader, Write};
use std::path::PathBuf;

use catalog::Catalog;
use serde::Deserialize;
use serde_json::{Value, json};

const SERVER_NAME: &str = "ontoclaw-mcp";
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
                    "instructions": "Use OntoClaw tools to discover skills, inspect payloads, and plan from semantic state transitions."
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
                let result = json!({ "tools": tool_definitions() });
                respond_ok(&mut writer, wire_mode, request.id, result)?;
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
                respond_ok(
                    &mut writer,
                    wire_mode,
                    request.id,
                    json!({ "prompts": [] }),
                )?;
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

    if let Ok(path) = env::var("ONTOCLAW_MCP_ONTOLOGY_ROOT") {
        return PathBuf::from(path);
    }

    discover_ontology_root().unwrap_or_else(|| PathBuf::from("ontoskills"))
}

fn discover_ontology_root() -> Option<PathBuf> {
    let cwd = env::current_dir().ok()?;

    for candidate in candidate_roots(&cwd) {
        if candidate.exists() {
            return Some(candidate);
        }
    }

    None
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
        "list_skills" => json!(catalog.list_skills().map_err(|err| err.to_string())?),
        "find_skills_by_intent" => {
            let intent = required_string(&arguments, "intent")?;
            json!(
                catalog
                    .find_skills_by_intent(intent)
                    .map_err(|err| err.to_string())?
            )
        }
        "get_skill" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            json!(catalog.get_skill(skill_id).map_err(|err| err.to_string())?)
        }
        "get_skill_requirements" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            json!(
                catalog
                    .get_skill_requirements(skill_id)
                    .map_err(|err| err.to_string())?
            )
        }
        "get_skill_transitions" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            let details = catalog.get_skill(skill_id).map_err(|err| err.to_string())?;
            json!({
                "skill_id": details.id,
                "requires_state": details.requires_state,
                "yields_state": details.yields_state,
                "handles_failure": details.handles_failure,
            })
        }
        "get_skill_dependencies" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            let details = catalog.get_skill(skill_id).map_err(|err| err.to_string())?;
            json!({
                "skill_id": details.id,
                "depends_on": details.depends_on,
                "extends": details.extends,
                "contradicts": details.contradicts,
            })
        }
        "get_skill_conflicts" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            let details = catalog.get_skill(skill_id).map_err(|err| err.to_string())?;
            json!({
                "skill_id": details.id,
                "contradicts": details.contradicts,
            })
        }
        "find_skills_yielding_state" => {
            let state = required_string(&arguments, "state")?;
            json!(
                catalog
                    .find_skills_yielding_state(state)
                    .map_err(|err| err.to_string())?
            )
        }
        "find_skills_requiring_state" => {
            let state = required_string(&arguments, "state")?;
            json!(
                catalog
                    .find_skills_requiring_state(state)
                    .map_err(|err| err.to_string())?
            )
        }
        "check_skill_applicability" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            let current_states = string_list(&arguments, "current_states");
            json!(
                catalog
                    .check_skill_applicability(skill_id, &current_states)
                    .map_err(|err| err.to_string())?
            )
        }
        "plan_from_intent" => {
            let intent = required_string(&arguments, "intent")?;
            let current_states = string_list(&arguments, "current_states");
            json!(
                catalog
                    .plan_from_intent(intent, &current_states)
                    .map_err(|err| err.to_string())?
            )
        }
        "get_skill_payload" => {
            let skill_id = required_string(&arguments, "skill_id")?;
            json!(
                catalog
                    .get_skill_payload(skill_id)
                    .map_err(|err| err.to_string())?
            )
        }
        _ => return Err(format!("Unknown tool: {tool_name}")),
    };

    Ok(json!({
        "content": [
            {
                "type": "text",
                "text": serde_json::to_string_pretty(&structured).unwrap_or_else(|_| structured.to_string())
            }
        ],
        "structuredContent": structured,
        "isError": false
    }))
}

fn required_string<'a>(value: &'a Value, key: &str) -> Result<&'a str, String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("Missing required string field '{key}'"))
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
            "list_skills",
            "List all OntoClaw skills available in the global ontology catalog.",
            json!({
                "type": "object",
                "properties": {}
            }),
        ),
        tool(
            "find_skills_by_intent",
            "Find skills that resolve a given user intent.",
            json!({
                "type": "object",
                "properties": {
                    "intent": { "type": "string", "description": "Intent literal to match against oc:resolvesIntent." }
                },
                "required": ["intent"]
            }),
        ),
        tool(
            "get_skill",
            "Fetch the complete semantic description of a skill by skill_id.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string", "description": "Stable human-readable skill identifier." }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "get_skill_requirements",
            "Fetch the requirements attached to a skill.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "get_skill_transitions",
            "Return requires/yields/failure states for a skill.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "get_skill_dependencies",
            "Return dependsOn, extends, and contradicts relations for a skill.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "get_skill_conflicts",
            "Return only contradicts relations for a skill.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "find_skills_yielding_state",
            "Find skills that produce a given state via oc:yieldsState.",
            json!({
                "type": "object",
                "properties": {
                    "state": { "type": "string", "description": "State URI or oc:StateName compact value." }
                },
                "required": ["state"]
            }),
        ),
        tool(
            "find_skills_requiring_state",
            "Find skills that require a given state via oc:requiresState.",
            json!({
                "type": "object",
                "properties": {
                    "state": { "type": "string", "description": "State URI or oc:StateName compact value." }
                },
                "required": ["state"]
            }),
        ),
        tool(
            "check_skill_applicability",
            "Check whether a skill can run given the caller's current states.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" },
                    "current_states": {
                        "type": "array",
                        "items": { "type": "string" },
                        "description": "Current runtime states already satisfied by the caller."
                    }
                },
                "required": ["skill_id"]
            }),
        ),
        tool(
            "plan_from_intent",
            "Create a semantically grounded plan from an intent and the caller's current states.",
            json!({
                "type": "object",
                "properties": {
                    "intent": { "type": "string" },
                    "current_states": {
                        "type": "array",
                        "items": { "type": "string" }
                    }
                },
                "required": ["intent"]
            }),
        ),
        tool(
            "get_skill_payload",
            "Return the execution payload of a skill for the agent to run locally.",
            json!({
                "type": "object",
                "properties": {
                    "skill_id": { "type": "string" }
                },
                "required": ["skill_id"]
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
