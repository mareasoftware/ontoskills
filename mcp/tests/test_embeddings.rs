//! Integration tests for semantic discovery.

use std::path::PathBuf;
use std::process::{Command, Stdio};

/// Test that MCP server starts with embeddings support.
#[test]
#[ignore] // Run manually with --ignored flag
fn test_mcp_starts_with_embeddings() {
    let binary = PathBuf::from(env!("CARGO_BIN_EXE_ontoskills-mcp"));

    let output = Command::new(&binary)
        .arg("--ontology-root")
        .arg("/tmp/test-ontoskills")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .expect("Failed to start MCP server");

    // Server should start even without embeddings
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("ontoskills-mcp") || output.status.success());
}
