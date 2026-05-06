use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use tempfile::tempdir;

struct McpProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl McpProcess {
    fn start(ontology_root: &Path, memory_root: &Path) -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_ontomcp"))
            .arg("--ontology-root")
            .arg(ontology_root)
            .env("ONTOMEMORY_ROOT", memory_root)
            .env("ONTOMEMORY_PROJECT_ID", "protocol-test")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn ontomcp");
        let stdin = child.stdin.take().expect("child stdin");
        let stdout = BufReader::new(child.stdout.take().expect("child stdout"));
        Self {
            child,
            stdin,
            stdout,
            next_id: 1,
        }
    }

    fn request(&mut self, method: &str, params: Value) -> Value {
        let id = self.next_id;
        self.next_id += 1;
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params
        });
        writeln!(self.stdin, "{}", request).expect("write request");
        self.stdin.flush().expect("flush request");

        let mut line = String::new();
        self.stdout.read_line(&mut line).expect("read response");
        let response: Value = serde_json::from_str(&line).expect("parse response");
        assert_eq!(response["id"], id);
        assert!(
            response.get("error").is_none(),
            "unexpected MCP error: {response}"
        );
        response["result"].clone()
    }
}

impl Drop for McpProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn write_minimal_ontology(root: &Path) {
    std::fs::create_dir_all(root).unwrap();
    std::fs::write(
        root.join("index.ttl"),
        r#"
@prefix oc: <https://ontoskills.sh/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_test a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "test-skill" ;
    oc:nature "Test skill" ;
    oc:resolvesIntent "test deployment bucket" .
"#,
    )
    .unwrap();
}

#[test]
fn mcp_server_handles_agent_style_memory_calls() {
    let dir = tempdir().unwrap();
    let ontology_root = dir.path().join("ontologies");
    let memory_root = dir.path().join("memories");
    write_minimal_ontology(&ontology_root);

    let mut mcp = McpProcess::start(&ontology_root, &memory_root);

    let init = mcp.request(
        "initialize",
        json!({
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {
                "name": "ontomemory-protocol-test",
                "version": "0.0.0"
            }
        }),
    );
    assert_eq!(init["serverInfo"]["name"], "ontomcp");

    let tools = mcp.request("tools/list", json!({}));
    let tool_names = tools["tools"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|tool| tool["name"].as_str())
        .collect::<Vec<_>>();
    assert_eq!(tool_names, vec!["ontoskill", "ontomemory", "ontograph"]);

    let remembered = mcp.request(
        "tools/call",
        json!({
            "name": "ontomemory",
            "arguments": {
                "action": "remember",
                "content": "Use the blue deployment bucket for staging",
                "memory_type": "fact",
                "related_skill_id": "test-skill",
                "severity_level": "high",
                "confidence": 0.9
            }
        }),
    );
    let memory_id = remembered["structuredContent"]["memory"]["memory_id"]
        .as_str()
        .expect("memory id");
    assert!(memory_id.starts_with("mem-"));
    assert!(
        remembered["content"][0]["text"]
            .as_str()
            .unwrap()
            .contains("Remembered:")
    );

    let search = mcp.request(
        "tools/call",
        json!({
            "name": "ontomemory",
            "arguments": {
                "action": "search",
                "query": "blue bucket",
                "scope": "both",
                "min_confidence": 0.8
            }
        }),
    );
    assert_eq!(
        search["structuredContent"]["memories"][0]["content"],
        "Use the blue deployment bucket for staging"
    );

    let ontoskill = mcp.request(
        "tools/call",
        json!({
            "name": "ontoskill",
            "arguments": {
                "q": "blue deployment bucket"
            }
        }),
    );
    assert_eq!(
        ontoskill["structuredContent"]["memories"][0]["content"],
        "Use the blue deployment bucket for staging"
    );
    assert!(
        ontoskill["content"][0]["text"]
            .as_str()
            .unwrap()
            .contains("Relevant memories")
    );
}
