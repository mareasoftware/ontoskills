use std::collections::{BTreeSet, HashMap};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use crate::catalog::Catalog;
use crate::memory::MemoryStore;
use serde_json::{Value, json};

pub struct GraphServerHandle {
    host: String,
    port: u16,
    running: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

impl GraphServerHandle {
    pub fn url(&self) -> String {
        format!("http://{}:{}", self.host, self.port)
    }

    pub fn host(&self) -> &str {
        &self.host
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    pub fn stop(mut self) {
        self.running.store(false, Ordering::SeqCst);
        let _ = TcpStream::connect((self.host.as_str(), self.port));
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }

    pub fn wait(mut self) {
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for GraphServerHandle {
    fn drop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        let _ = TcpStream::connect((self.host.as_str(), self.port));
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

pub fn start_server(
    ontology_root: PathBuf,
    host: &str,
    preferred_port: u16,
    open_port_range: bool,
) -> Result<GraphServerHandle, String> {
    let (listener, addr) = bind_listener(host, preferred_port, open_port_range)?;
    listener
        .set_nonblocking(true)
        .map_err(|err| format!("Failed to configure graph server socket: {err}"))?;

    let running = Arc::new(AtomicBool::new(true));
    let thread_running = Arc::clone(&running);
    let host = addr.ip().to_string();
    let port = addr.port();
    let thread = thread::spawn(move || {
        while thread_running.load(Ordering::SeqCst) {
            match listener.accept() {
                Ok((stream, _)) => handle_connection(stream, &ontology_root),
                Err(err) if err.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(25));
                }
                Err(_) => thread::sleep(Duration::from_millis(50)),
            }
        }
    });

    Ok(GraphServerHandle {
        host,
        port,
        running,
        thread: Some(thread),
    })
}

fn bind_listener(
    host: &str,
    preferred_port: u16,
    open_port_range: bool,
) -> Result<(TcpListener, SocketAddr), String> {
    let max_attempts = if open_port_range { 100 } else { 1 };
    let mut last_error = None;
    for offset in 0..max_attempts {
        let Some(port) = preferred_port.checked_add(offset) else {
            break;
        };
        match TcpListener::bind((host, port)) {
            Ok(listener) => {
                let addr = listener
                    .local_addr()
                    .map_err(|err| format!("Failed to read graph server address: {err}"))?;
                return Ok((listener, addr));
            }
            Err(err) => {
                last_error = Some(err.to_string());
                continue;
            }
        }
    }
    let detail = last_error.unwrap_or_else(|| "no bind attempts completed".to_string());
    Err(format!(
        "Failed to bind OntoGraph server on {host}:{preferred_port}: {detail}"
    ))
}

fn handle_connection(mut stream: TcpStream, ontology_root: &PathBuf) {
    let mut buffer = vec![0_u8; 64 * 1024];
    let Ok(bytes_read) = stream.read(&mut buffer) else {
        return;
    };
    if bytes_read == 0 {
        return;
    }
    buffer.truncate(bytes_read);
    let request = String::from_utf8_lossy(&buffer);
    let Some((request_line, rest)) = request.split_once("\r\n") else {
        write_text(&mut stream, 400, "text/plain", "Bad request");
        return;
    };
    let parts: Vec<&str> = request_line.split_whitespace().collect();
    if parts.len() < 2 {
        write_text(&mut stream, 400, "text/plain", "Bad request");
        return;
    }
    let method = parts[0];
    let target = parts[1];
    let body = rest
        .split_once("\r\n\r\n")
        .map(|(_, body)| body.as_bytes())
        .unwrap_or_default();

    match (method, target) {
        ("GET", "/") | ("GET", "/index.html") => write_text(&mut stream, 200, "text/html", UI_HTML),
        ("GET", target) if target.starts_with("/api/status") => write_json(
            &mut stream,
            200,
            json!({
                "ok": true,
                "ontology_root": ontology_root.display().to_string(),
                "memory_root": std::env::var("ONTOMEMORY_ROOT").ok()
            }),
        ),
        ("GET", target) if target.starts_with("/api/graph") => {
            let params = parse_query(target);
            match build_graph_response(ontology_root, &params) {
                Ok(value) => write_json(&mut stream, 200, value),
                Err(err) => write_json(&mut stream, 500, json!({ "error": err })),
            }
        }
        ("POST", "/api/memory") => match serde_json::from_slice::<Value>(body) {
            Ok(arguments) => match handle_memory_action(arguments) {
                Ok(value) => write_json(&mut stream, 200, value),
                Err(err) => write_json(&mut stream, 400, json!({ "error": err })),
            },
            Err(err) => write_json(&mut stream, 400, json!({ "error": err.to_string() })),
        },
        ("OPTIONS", _) => write_options(&mut stream),
        _ => write_text(&mut stream, 404, "text/plain", "Not found"),
    }
}

fn build_graph_response(
    ontology_root: &PathBuf,
    params: &HashMap<String, String>,
) -> Result<Value, String> {
    let catalog = Catalog::load(ontology_root).map_err(|err| err.to_string())?;
    let mut memory_store = MemoryStore::from_environment();
    build_graph_value(&catalog, &mut memory_store, ontology_root, params)
}

pub(crate) fn build_graph_value(
    catalog: &Catalog,
    memory_store: &mut MemoryStore,
    ontology_root: &PathBuf,
    params: &HashMap<String, String>,
) -> Result<Value, String> {
    let include_archived = params
        .get("include_archived")
        .map(|value| value == "true" || value == "1")
        .unwrap_or(false);
    let scope = params.get("scope").map(String::as_str).unwrap_or("both");

    let mut nodes = Vec::new();
    let mut edges = Vec::new();
    let mut seen_nodes = BTreeSet::new();
    let mut seen_edges = BTreeSet::new();

    for skill_id in catalog.all_skill_ids() {
        let Ok(ctx) = catalog.get_skill_context(&skill_id, false) else {
            continue;
        };
        let skill = ctx.skill.clone();
        push_node(
            &mut nodes,
            &mut seen_nodes,
            json!({
                "id": format!("skill:{skill_id}"),
                "label": skill_id,
                "kind": "skill",
                "group": "skill",
                "data": skill
            }),
        );
        for target in &ctx.skill.depends_on {
            push_skill_ref(&mut nodes, &mut seen_nodes, target);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("skill:{target}"),
                "depends_on",
            );
        }
        for target in &ctx.skill.extends {
            push_skill_ref(&mut nodes, &mut seen_nodes, target);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("skill:{target}"),
                "extends",
            );
        }
        for target in &ctx.skill.contradicts {
            push_skill_ref(&mut nodes, &mut seen_nodes, target);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("skill:{target}"),
                "contradicts",
            );
        }
        for intent in &ctx.skill.intents {
            push_intent(&mut nodes, &mut seen_nodes, intent);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("intent:{intent}"),
                "resolves_intent",
            );
        }
        for state in &ctx.skill.requires_state {
            push_state(&mut nodes, &mut seen_nodes, &state);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("state:{state}"),
                "requires_state",
            );
        }
        for state in &ctx.skill.yields_state {
            push_state(&mut nodes, &mut seen_nodes, &state);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("state:{state}"),
                "yields_state",
            );
        }
        for state in &ctx.skill.handles_failure {
            push_state(&mut nodes, &mut seen_nodes, &state);
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &format!("state:{state}"),
                "handles_failure",
            );
        }
        for node in ctx.knowledge_nodes {
            let node_id = format!("knowledge:{}", node.uri);
            push_node(
                &mut nodes,
                &mut seen_nodes,
                json!({
                    "id": node_id,
                    "label": node.label.clone().unwrap_or_else(|| node.kind.clone()),
                    "kind": "knowledge_node",
                    "group": node.dimension.clone().unwrap_or_else(|| "knowledge".to_string()),
                    "data": {
                        "uri": node.uri,
                        "kind": node.kind,
                        "dimension": node.dimension,
                        "directive_content": node.directive_content,
                        "rationale": node.rationale,
                        "applies_to_context": node.applies_to_context,
                        "severity_level": node.severity_level,
                        "source_skill_id": node.source_skill_id,
                        "code_language": node.code_language,
                        "step_order": node.step_order,
                        "template_variables": node.template_variables,
                        "links": node.links
                    }
                }),
            );
            push_edge(
                &mut edges,
                &mut seen_edges,
                &format!("skill:{skill_id}"),
                &node_id,
                "imparts_knowledge",
            );
        }
    }

    let memories = memory_store.graph_records(scope, include_archived)?;
    for record in memories {
        let memory = json!(record);
        let Some(memory_id) = memory.get("memory_id").and_then(Value::as_str) else {
            continue;
        };
        let node_id = format!("memory:{memory_id}");
        push_node(
            &mut nodes,
            &mut seen_nodes,
            json!({
                "id": node_id,
                    "label": memory_label(&memory, memory_id),
                "kind": "memory",
                "group": memory.get("memory_type").and_then(Value::as_str).unwrap_or("memory"),
                "data": memory
            }),
        );
        if let Some(skill_ids) = memory.get("related_skill_ids").and_then(Value::as_array) {
            for skill in skill_ids {
                if let Some(skill_id) = skill.as_str() {
                    push_skill_ref(&mut nodes, &mut seen_nodes, skill_id);
                    push_edge(
                        &mut edges,
                        &mut seen_edges,
                        &node_id,
                        &format!("skill:{skill_id}"),
                        "related_to_skill",
                    );
                }
            }
        }
        if let Some(intents) = memory.get("related_intents").and_then(Value::as_array) {
            for intent in intents {
                if let Some(intent_id) = intent.as_str() {
                    push_intent(&mut nodes, &mut seen_nodes, intent_id);
                    push_edge(
                        &mut edges,
                        &mut seen_edges,
                        &node_id,
                        &format!("intent:{intent_id}"),
                        "related_to_intent",
                    );
                }
            }
        }
        if let Some(topics) = memory.get("related_topic_ids").and_then(Value::as_array) {
            for topic in topics {
                if let Some(topic_id) = topic.as_str() {
                    push_topic(&mut nodes, &mut seen_nodes, topic_id);
                    push_edge(
                        &mut edges,
                        &mut seen_edges,
                        &node_id,
                        &format!("topic:{topic_id}"),
                        "related_to_topic",
                    );
                }
            }
        }
        for (field, relation) in [
            ("related_memory_ids", "related_to_memory"),
            ("depends_on_memory_ids", "depends_on_memory"),
            ("supersedes_memory_ids", "supersedes_memory"),
        ] {
            if let Some(ids) = memory.get(field).and_then(Value::as_array) {
                for target in ids {
                    if let Some(target_id) = target.as_str() {
                        push_memory_ref(&mut nodes, &mut seen_nodes, target_id);
                        push_edge(
                            &mut edges,
                            &mut seen_edges,
                            &node_id,
                            &format!("memory:{target_id}"),
                            relation,
                        );
                    }
                }
            }
        }
    }

    let missing_memory_refs = missing_memory_refs(&nodes);
    Ok(json!({
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": nodes.len(),
            "edges": edges.len(),
            "missing_memory_refs": missing_memory_refs,
            "ontology_root": ontology_root.display().to_string()
        }
    }))
}

fn handle_memory_action(arguments: Value) -> Result<Value, String> {
    let mut store = MemoryStore::from_environment();
    let result = store.handle_action(&arguments)?;
    Ok(result.structured)
}

fn push_state(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, state: &str) {
    push_node(
        nodes,
        seen_nodes,
        json!({
            "id": format!("state:{state}"),
            "label": state,
            "kind": "state",
            "group": "state",
            "data": { "state": state }
        }),
    );
}

fn push_intent(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, intent: &str) {
    push_node(
        nodes,
        seen_nodes,
        json!({
            "id": format!("intent:{intent}"),
            "label": intent,
            "kind": "intent",
            "group": "intent",
            "data": { "intent": intent }
        }),
    );
}

fn push_topic(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, topic: &str) {
    push_node(
        nodes,
        seen_nodes,
        json!({
            "id": format!("topic:{topic}"),
            "label": topic,
            "kind": "topic",
            "group": "topic",
            "data": { "topic": topic }
        }),
    );
}

fn push_skill_ref(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, skill_id: &str) {
    push_node(
        nodes,
        seen_nodes,
        json!({
            "id": format!("skill:{skill_id}"),
            "label": skill_id,
            "kind": "skill",
            "group": "skill_ref",
            "data": {
                "id": skill_id,
                "placeholder": true,
                "note": "Referenced skill not loaded in the current catalog graph."
            }
        }),
    );
}

fn push_memory_ref(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, memory_id: &str) {
    push_node(
        nodes,
        seen_nodes,
        json!({
            "id": format!("memory:{memory_id}"),
            "label": memory_id,
            "kind": "memory",
            "group": "memory_ref",
            "data": {
                "memory_id": memory_id,
                "placeholder": true,
                "note": "Referenced memory was not found in the loaded memory files, or it is filtered out."
            }
        }),
    );
}

fn push_node(nodes: &mut Vec<Value>, seen_nodes: &mut BTreeSet<String>, node: Value) {
    if let Some(id) = node.get("id").and_then(Value::as_str) {
        if seen_nodes.insert(id.to_string()) {
            nodes.push(node);
        } else if !node
            .pointer("/data/placeholder")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            if let Some(existing) = nodes
                .iter_mut()
                .find(|existing| existing.get("id").and_then(Value::as_str) == Some(id))
            {
                if existing
                    .pointer("/data/placeholder")
                    .and_then(Value::as_bool)
                    .unwrap_or(false)
                {
                    *existing = node;
                }
            }
        }
    }
}

fn memory_label(memory: &Value, memory_id: &str) -> String {
    memory
        .get("title")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .or_else(|| memory.get("content").and_then(Value::as_str))
        .map(|value| {
            let mut label = value.trim().replace('\n', " ");
            if label.len() > 72 {
                label.truncate(72);
            }
            label
        })
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| memory_id.to_string())
}

fn missing_memory_refs(nodes: &[Value]) -> Vec<String> {
    let mut refs = nodes
        .iter()
        .filter(|node| node.get("kind").and_then(Value::as_str) == Some("memory"))
        .filter(|node| {
            node.pointer("/data/placeholder")
                .and_then(Value::as_bool)
                .unwrap_or(false)
        })
        .filter_map(|node| {
            node.pointer("/data/memory_id")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
        .collect::<Vec<_>>();
    refs.sort();
    refs.dedup();
    refs
}

fn push_edge(
    edges: &mut Vec<Value>,
    seen_edges: &mut BTreeSet<String>,
    source: &str,
    target: &str,
    relation: &str,
) {
    let id = format!("{source}|{relation}|{target}");
    if seen_edges.insert(id.clone()) {
        edges.push(json!({
            "id": id,
            "source": source,
            "target": target,
            "relation": relation
        }));
    }
}

fn parse_query(target: &str) -> HashMap<String, String> {
    let mut params = HashMap::new();
    let Some((_, query)) = target.split_once('?') else {
        return params;
    };
    for pair in query.split('&') {
        let Some((key, value)) = pair.split_once('=') else {
            continue;
        };
        params.insert(percent_decode(key), percent_decode(value));
    }
    params
}

fn percent_decode(value: &str) -> String {
    let mut output = String::new();
    let mut chars = value.as_bytes().iter().copied();
    while let Some(byte) = chars.next() {
        if byte == b'%' {
            let hi = chars.next();
            let lo = chars.next();
            if let (Some(hi), Some(lo)) = (hi, lo) {
                if let Ok(hex) = std::str::from_utf8(&[hi, lo]) {
                    if let Ok(decoded) = u8::from_str_radix(hex, 16) {
                        output.push(decoded as char);
                        continue;
                    }
                }
            }
            output.push('%');
        } else if byte == b'+' {
            output.push(' ');
        } else {
            output.push(byte as char);
        }
    }
    output
}

fn write_json(stream: &mut TcpStream, status: u16, value: Value) {
    let body = serde_json::to_string(&value).unwrap_or_else(|_| "{}".to_string());
    write_text(stream, status, "application/json", &body);
}

fn write_options(stream: &mut TcpStream) {
    let response = "HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET,POST,OPTIONS\r\nAccess-Control-Allow-Headers: content-type\r\nContent-Length: 0\r\n\r\n";
    let _ = stream.write_all(response.as_bytes());
}

fn write_text(stream: &mut TcpStream, status: u16, content_type: &str, body: &str) {
    let status_text = match status {
        200 => "OK",
        204 => "No Content",
        400 => "Bad Request",
        404 => "Not Found",
        500 => "Internal Server Error",
        _ => "OK",
    };
    let response = format!(
        "HTTP/1.1 {status} {status_text}\r\nContent-Type: {content_type}; charset=utf-8\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes());
}

const UI_HTML: &str = r#"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OntoGraph</title>
<style>
html,body{height:100%;margin:0;background:#0f1217;color:#e8edf2;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow:hidden}
button,input,select,textarea{font:inherit}
.app{display:grid;grid-template-columns:1fr 440px;height:100%}
.stage{position:relative;min-width:0;background:radial-gradient(circle at 20% 15%,#202934 0,#11161d 36%,#0d1116 100%)}
#graph{width:100%;height:100%;display:block}
.bar{position:absolute;top:14px;left:14px;right:14px;z-index:3;display:flex;gap:8px;align-items:center;pointer-events:none}
.bar>*{pointer-events:auto}
.chip,.control,button{height:38px;box-sizing:border-box;border:1px solid #3a4654;background:rgba(24,31,39,.92);color:#e8edf2;border-radius:6px;padding:0 10px;box-shadow:0 8px 24px rgba(0,0,0,.2);display:inline-flex;align-items:center}
button{cursor:pointer}
button:hover{background:#26313b}
.control{min-width:130px}
.legend{position:absolute;left:14px;bottom:14px;display:flex;gap:10px;flex-wrap:wrap;padding:8px 10px;border:1px solid #303b47;background:rgba(15,19,24,.84);border-radius:6px;color:#c8d2dc;font-size:12px}
.legend span{display:inline-flex;align-items:center;gap:6px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.side{border-left:1px solid #2f3945;background:#151a21;display:grid;grid-template-rows:auto minmax(0,1fr) auto;min-width:0;min-height:0}
.head{padding:16px 18px;border-bottom:1px solid #2f3945;background:#181f27}
.head h1{font-size:18px;margin:0 0 9px}
.stats{display:flex;gap:8px;flex-wrap:wrap;color:#aeb8c2;font-size:12px}
.panel{overflow:auto;padding:18px;min-height:0}
.section{margin-bottom:24px}
.section h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#aeb8c2;margin:0 0 12px}
.kv{display:grid;grid-template-columns:98px 1fr;gap:8px 12px;font-size:13px}
.kv div:nth-child(odd){color:#9da8b3}
.content{white-space:pre-wrap;line-height:1.45;background:#10151b;border:1px solid #27323d;border-radius:6px;padding:10px;overflow:auto}
textarea,input,select{width:100%;box-sizing:border-box;background:#10151b;color:#e8edf2;border:1px solid #33404c;border-radius:6px;padding:8px}
textarea{min-height:92px;resize:vertical}
label{display:grid;gap:6px;margin:0 0 12px;color:#c2ccd6;font-size:13px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.foot{padding:10px 18px;border-top:1px solid #303842;color:#9da8b3;font-size:12px}
.hidden{display:none}
.badge{font-size:11px;padding:2px 6px;border-radius:999px;background:#26313b;color:#cbd5df}
.rel{display:grid;grid-template-columns:90px 1fr;gap:6px 10px;font-size:12px}.rel div{padding:6px 0;border-bottom:1px solid #252f39}.rel div:nth-child(odd){color:#f1c35d}
.hint{color:#8f9ba6;font-size:11px;margin-top:-8px;margin-bottom:10px}
@media(max-width:900px){.app{grid-template-columns:1fr}.side{position:absolute;right:0;top:0;bottom:0;width:min(440px,92vw)}}
</style>
</head>
<body>
<div class="app">
  <main class="stage">
    <canvas id="graph"></canvas>
    <div class="bar">
      <input id="search" class="control" placeholder="Search graph">
      <select id="kind" class="control">
        <option value="">All nodes</option><option value="skill">Skills</option><option value="knowledge_node">Knowledge</option><option value="memory">Memories</option><option value="intent">Intents</option><option value="topic">Topics</option><option value="state">States</option>
      </select>
      <select id="scope" class="control"><option value="both">Both scopes</option><option value="global">Global</option><option value="project">Project</option></select>
      <label class="chip"><input id="archived" type="checkbox"> archived</label>
      <button id="reload">Reload</button>
      <button id="resetView">Reset view</button>
    </div>
    <div class="legend">
      <span><i class="dot" style="background:#349eff"></i>Skill</span>
      <span><i class="dot" style="background:#faa338"></i>Memory</span>
      <span><i class="dot" style="background:#7ad16b"></i>Knowledge</span>
      <span><i class="dot" style="background:#f27ac4"></i>Intent</span>
      <span><i class="dot" style="background:#26c7bd"></i>Topic</span>
      <span><i class="dot" style="background:#bf94ff"></i>State</span>
    </div>
  </main>
  <aside class="side">
    <div class="head">
      <h1>OntoGraph</h1>
      <div class="stats"><span id="nodeCount">0 nodes</span><span id="edgeCount">0 edges</span><span id="selectedKind" class="badge">none</span></div>
    </div>
    <div class="panel">
      <div class="section">
        <h2>Details</h2>
        <div id="details">Select a node.</div>
      </div>
      <div class="section">
        <h2>Relations</h2>
        <div id="relations">Select a node.</div>
      </div>
      <div id="memoryEditor" class="section hidden">
        <h2>Memory Editor</h2>
        <input id="memoryId" type="hidden">
        <label>Title<input id="memoryTitle" placeholder="optional"></label>
        <label>Content</label>
        <textarea id="memoryContent"></textarea>
        <div class="row">
          <label>Type<select id="memoryType"><option>fact</option><option>preference</option><option>procedure</option><option>correction</option><option>anti_pattern</option></select></label>
          <label>Scope<select id="memoryScope"><option>project</option><option>global</option></select></label>
        </div>
        <div class="row">
          <label>Confidence<input id="memoryConfidence" type="number" min="0" max="1" step="0.01" placeholder="optional"></label>
          <label>Severity<select id="memorySeverity"><option value="">none</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
        </div>
        <label>Context<input id="memoryContext" placeholder="optional"></label>
        <label>Rationale<textarea id="memoryRationale"></textarea></label>
        <label>Source<input id="memorySource" placeholder="optional"></label>
        <label><span><input id="memoryArchived" type="checkbox"> archived</span></label>
        <label>Related skills<textarea id="relatedSkills" placeholder="one skill id per line"></textarea></label>
        <label>Related intents<textarea id="relatedIntents" placeholder="one intent per line"></textarea></label>
        <label>Related topics<textarea id="relatedTopics" placeholder="one topic id per line"></textarea></label>
        <label>Related memories<textarea id="relatedMemories" placeholder="one memory id per line"></textarea></label>
        <label>Depends on memories<textarea id="dependsOnMemories" placeholder="one memory id per line"></textarea></label>
        <label>Supersedes memories<textarea id="supersedesMemories" placeholder="one memory id per line"></textarea></label>
        <div class="hint">Multi-value fields replace the current relationship arrays on save.</div>
        <div class="actions">
          <button id="saveMemory">Save</button>
          <button id="newMemory">New</button>
          <button id="archiveMemory">Archive</button>
          <button id="deleteMemory">Hard delete</button>
        </div>
      </div>
      <div class="section">
        <h2>Create Memory</h2>
        <textarea id="newContent" placeholder="Remember..."></textarea>
        <div class="row"><select id="newType"><option>fact</option><option>preference</option><option>procedure</option><option>correction</option><option>anti_pattern</option></select><select id="newScope"><option>project</option><option>global</option></select></div>
        <button id="createMemory">Create</button>
      </div>
    </div>
    <div class="foot" id="status">Ready</div>
  </aside>
</div>
<script>
const canvas=document.getElementById('graph'),gl=canvas.getContext('webgl',{antialias:true});
let graph={nodes:[],edges:[]},visible=[],selected=null,angle=0,tilt=.32,zoom=1,panX=0,panY=0,drag=false,lastX=0,lastY=0,moved=false;
const colors={skill:[0.2,0.62,1],memory:[0.98,0.64,0.22],knowledge_node:[0.48,0.82,0.42],intent:[0.95,0.48,0.77],topic:[0.15,0.78,0.74],state:[0.75,0.58,1]};
function setStatus(t){document.getElementById('status').textContent=t}
async function loadGraph(){setStatus('Loading graph...');const scope=val('scope'),arch=document.getElementById('archived').checked;const r=await fetch(`/api/graph?scope=${scope}&include_archived=${arch}`);graph=await r.json();layout();filter();setStatus('Loaded')}
function val(id){return document.getElementById(id).value}
function layout(){const n=graph.nodes.length||1;graph.nodes.forEach((node,i)=>{const a=i*2.399963;const r=1.6+Math.sqrt(i/n)*3.8;node.x=Math.cos(a)*r;node.y=Math.sin(a)*r;node.z=((i%17)/17-.5)*4;});document.getElementById('nodeCount').textContent=`${graph.nodes.length} nodes`;document.getElementById('edgeCount').textContent=`${graph.edges.length} edges`}
function filter(){const q=val('search').toLowerCase(),k=val('kind');visible=graph.nodes.filter(n=>(!k||n.kind===k)&&JSON.stringify(n).toLowerCase().includes(q));draw()}
function project(n){const rect=overlay.getBoundingClientRect();const ca=Math.cos(angle),sa=Math.sin(angle),ct=Math.cos(tilt),st=Math.sin(tilt);let x=n.x*ca-n.z*sa,z=n.x*sa+n.z*ca,y=n.y*ct-z*st;z=n.y*st+z*ct+9;const s=rect.height*.72*zoom/Math.max(z,1.4);return {x:rect.width/2+panX+x*s,y:rect.height/2+panY-y*s,s,z}}
function draw(){if(!gl)return;resize();gl.viewport(0,0,canvas.width,canvas.height);gl.clearColor(.08,.1,.12,1);gl.clear(gl.COLOR_BUFFER_BIT);const ctx=canvas.getContext('2d');}
function draw2d(){const ctx=canvas.getContext('2d');}
const overlay=document.createElement('canvas');overlay.style.position='absolute';overlay.style.inset='0';overlay.style.zIndex='1';overlay.style.cursor='grab';canvas.parentElement.appendChild(overlay);const ctx=overlay.getContext('2d');
function render(){resize();ctx.clearRect(0,0,overlay.width,overlay.height);const ids=new Set(visible.map(n=>n.id));const byId=new Map(graph.nodes.map(n=>[n.id,n]));const memoryChain=selected&&selected.kind==='memory'?chainFor(selected.id):new Set();const linked=selected?new Set(graph.edges.filter(e=>e.source===selected.id||e.target===selected.id||memoryChain.has(e.source)||memoryChain.has(e.target)).flatMap(e=>[e.source,e.target])):new Set();for(const e of graph.edges){if(!ids.has(e.source)||!ids.has(e.target))continue;const a=byId.get(e.source),b=byId.get(e.target);if(!a||!b)continue;const pa=project(a),pb=project(b);const chainEdge=memoryChain.has(e.source)&&memoryChain.has(e.target)&&(e.relation==='depends_on_memory'||e.relation==='supersedes_memory');const active=selected&&(selected.id===e.source||selected.id===e.target||chainEdge);ctx.globalAlpha=active?1:.82;ctx.strokeStyle=chainEdge?'#fff0a8':active?'#ffd166':relationColor(e.relation);ctx.lineWidth=chainEdge?4:active?3.5:2.2;ctx.beginPath();ctx.moveTo(pa.x,pa.y);ctx.lineTo(pb.x,pb.y);ctx.stroke();drawArrow(pa,pb,active,e.relation);if(active)drawEdgeLabel(pa,pb,e.relation)}ctx.globalAlpha=1;for(const n of visible){const p=project(n),c=colors[n.kind]||[.8,.8,.8],isSelected=selected&&selected.id===n.id,isChain=memoryChain.has(n.id),isLinked=linked.has(n.id),r=isSelected?11:isChain?10:isLinked?9:7;ctx.fillStyle='rgba(0,0,0,.48)';ctx.beginPath();ctx.arc(p.x+1,p.y+2,r+2,0,Math.PI*2);ctx.fill();ctx.fillStyle=`rgb(${c.map(v=>Math.round(v*255)).join(',')})`;ctx.beginPath();ctx.arc(p.x,p.y,r,0,Math.PI*2);ctx.fill();ctx.strokeStyle=isSelected?'#fff':isChain?'#fff0a8':isLinked?'#ffd166':'#18212b';ctx.lineWidth=isSelected?3:isChain?3:isLinked?2.5:1.5;ctx.stroke();if(p.s>58||isSelected||isLinked||isChain){ctx.fillStyle='#f2f6fa';ctx.font='12px system-ui';ctx.fillText(n.label.slice(0,42),p.x+12,p.y+4)}}requestAnimationFrame(render)}
function chainFor(start){const chain=new Set([start]);let changed=true;while(changed){changed=false;for(const e of graph.edges){if(e.relation!=='depends_on_memory'&&e.relation!=='supersedes_memory')continue;if(chain.has(e.source)&&!chain.has(e.target)){chain.add(e.target);changed=true}if(chain.has(e.target)&&!chain.has(e.source)){chain.add(e.source);changed=true}}}return chain}
function relationColor(r){return r==='related_to_skill'?'#ffb454':r==='related_to_intent'?'#f27ac4':r==='related_to_topic'?'#26c7bd':r.includes('memory')?'#ff7f6e':r.includes('state')?'#b590ff':r==='imparts_knowledge'?'#7ddc78':r==='resolves_intent'?'#f27ac4':'#adc0d2'}
function drawArrow(a,b,active,relation){const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy);if(len<24)return;const ux=dx/len,uy=dy/len,x=b.x-ux*12,y=b.y-uy*12,size=active?10:8;ctx.fillStyle=active?'#ffd166':relationColor(relation);ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x-ux*size-uy*size*.6,y-uy*size+ux*size*.6);ctx.lineTo(x-ux*size+uy*size*.6,y-uy*size-ux*size*.6);ctx.closePath();ctx.fill()}
function drawEdgeLabel(a,b,label){const x=(a.x+b.x)/2,y=(a.y+b.y)/2,text=label.replaceAll('_',' ');ctx.font='11px system-ui';const w=ctx.measureText(text).width+10;ctx.fillStyle='rgba(16,21,27,.88)';ctx.fillRect(x-w/2,y-10,w,18);ctx.fillStyle='#ffe2a3';ctx.fillText(text,x-w/2+5,y+3)}
function resize(){const rect=canvas.getBoundingClientRect();for(const c of [canvas,overlay]){if(c.width!==rect.width*devicePixelRatio||c.height!==rect.height*devicePixelRatio){c.width=rect.width*devicePixelRatio;c.height=rect.height*devicePixelRatio;c.style.width=rect.width+'px';c.style.height=rect.height+'px'}}ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0)}
function pick(e){const rect=overlay.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;let best=null,bd=24;for(const n of visible){const p=project(n),d=Math.hypot(p.x-x,p.y-y);if(d<bd){bd=d;best=n}}if(best)select(best)}
function select(n){selected=n;document.getElementById('selectedKind').textContent=n.kind;details(n);relations(n);drawMemory(n)}
function esc(s){return String(s??'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))}
function details(n){const d=n.data||{};document.getElementById('details').innerHTML=`<div class="kv"><div>ID</div><div>${esc(n.id)}</div><div>Kind</div><div>${esc(n.kind)}</div><div>Label</div><div>${esc(n.label)}</div><div>Group</div><div>${esc(n.group||'')}</div></div><p class="content">${esc(d.content||d.directive_content||d.differentia||d.note||'')}</p><pre class="content">${esc(JSON.stringify(d,null,2))}</pre>`}
function relations(n){const byId=new Map(graph.nodes.map(node=>[node.id,node]));const rows=graph.edges.filter(e=>e.source===n.id||e.target===n.id).map(e=>{const outgoing=e.source===n.id,target=byId.get(outgoing?e.target:e.source);return `<div>${esc(outgoing?'outgoing':'incoming')}</div><div>${esc(e.relation)} -> ${esc(target?.label||target?.id||'missing')}</div>`}).join('');document.getElementById('relations').innerHTML=rows?`<div class="rel">${rows}</div>`:'No visible relations.'}
function asLines(values){return (values||[]).join('\n')}
function lines(id){return val(id).split(/\r?\n|,/).map(s=>s.trim()).filter(Boolean)}
function drawMemory(n){const show=n.kind==='memory';document.getElementById('memoryEditor').classList.toggle('hidden',!show);if(!show)return;const d=n.data;document.getElementById('memoryId').value=d.memory_id||'';document.getElementById('memoryTitle').value=d.title||'';document.getElementById('memoryContent').value=d.content||'';document.getElementById('memoryType').value=d.memory_type||'fact';document.getElementById('memoryScope').value=d.scope||'project';document.getElementById('memoryConfidence').value=d.confidence??'';document.getElementById('memorySeverity').value=d.severity_level||'';document.getElementById('memoryContext').value=d.applies_to_context||'';document.getElementById('memoryRationale').value=d.rationale||'';document.getElementById('memorySource').value=d.source||'';document.getElementById('memoryArchived').checked=!!d.is_archived;document.getElementById('relatedSkills').value=asLines(d.related_skill_ids);document.getElementById('relatedIntents').value=asLines(d.related_intents);document.getElementById('relatedTopics').value=asLines(d.related_topic_ids);document.getElementById('relatedMemories').value=asLines(d.related_memory_ids);document.getElementById('dependsOnMemories').value=asLines(d.depends_on_memory_ids);document.getElementById('supersedesMemories').value=asLines(d.supersedes_memory_ids)}
async function memory(args){setStatus('Saving...');const r=await fetch('/api/memory',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(args)});const j=await r.json();if(!r.ok)throw new Error(j.error||'Memory request failed');await loadGraph();return j}
document.getElementById('reload').onclick=loadGraph;document.getElementById('resetView').onclick=()=>{angle=0;tilt=.32;zoom=1;panX=0;panY=0};document.getElementById('search').oninput=filter;document.getElementById('kind').onchange=filter;document.getElementById('scope').onchange=loadGraph;document.getElementById('archived').onchange=loadGraph;
document.getElementById('createMemory').onclick=()=>memory({action:'remember',content:val('newContent'),memory_type:val('newType'),scope:val('newScope')}).then(()=>document.getElementById('newContent').value='').catch(e=>setStatus(e.message));
document.getElementById('saveMemory').onclick=()=>{const id=val('memoryId'),confidence=val('memoryConfidence');const args={action:id?'update':'remember',memory_id:id||undefined,title:val('memoryTitle')||null,content:val('memoryContent'),memory_type:val('memoryType'),scope:val('memoryScope'),applies_to_context:val('memoryContext')||null,rationale:val('memoryRationale')||null,source:val('memorySource')||null,severity_level:val('memorySeverity')||null,confidence:confidence===''?null:Number(confidence),is_archived:document.getElementById('memoryArchived').checked,related_skill_ids:lines('relatedSkills'),related_intents:lines('relatedIntents'),related_topic_ids:lines('relatedTopics'),related_memory_ids:lines('relatedMemories'),depends_on_memory_ids:lines('dependsOnMemories'),supersedes_memory_ids:lines('supersedesMemories')};memory(args).catch(e=>setStatus(e.message))};
document.getElementById('newMemory').onclick=()=>{selected=null;for(const id of ['memoryId','memoryTitle','memoryContent','memoryConfidence','memorySeverity','memoryContext','memoryRationale','memorySource','relatedSkills','relatedIntents','relatedTopics','relatedMemories','dependsOnMemories','supersedesMemories'])document.getElementById(id).value='';document.getElementById('memoryEditor').classList.remove('hidden')};
document.getElementById('archiveMemory').onclick=()=>memory({action:'forget',memory_id:val('memoryId')}).catch(e=>setStatus(e.message));
document.getElementById('deleteMemory').onclick=()=>memory({action:'forget',memory_id:val('memoryId'),hard_delete:true}).catch(e=>setStatus(e.message));
overlay.addEventListener('click',e=>{if(!moved)pick(e)});
overlay.addEventListener('mousedown',e=>{drag=true;moved=false;lastX=e.clientX;lastY=e.clientY;overlay.style.cursor='grabbing'});
window.addEventListener('mouseup',()=>{drag=false;overlay.style.cursor='grab'});
window.addEventListener('mousemove',e=>{if(!drag)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;moved=moved||Math.abs(dx)+Math.abs(dy)>3;if(e.shiftKey){panX+=dx;panY+=dy}else{angle+=dx*.01;tilt=Math.max(-1.05,Math.min(1.05,tilt+dy*.008))}lastX=e.clientX;lastY=e.clientY});
overlay.addEventListener('wheel',e=>{if(e.shiftKey){panX-=e.deltaX;panY-=e.deltaY}else{zoom=Math.max(.35,Math.min(3.5,zoom-e.deltaY*.0012))}e.preventDefault()},{passive:false});
loadGraph();render();
</script>
</body>
</html>"#;
