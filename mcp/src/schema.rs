//! Schema resource for ontology://schema URI.
//!
//! Provides a compact JSON schema describing classes, properties,
//! and example queries for LLM agents.

use serde_json::{json, Value};

/// Get the schema resource as JSON.
///
/// Returns a compact schema (<4KB) describing the ontology structure
/// for LLM agents to understand available properties and conventions.
pub fn get_schema_resource() -> Value {
    json!({
        "version": "0.1.0",
        "base_uri": "https://ontoskills.sh/ontology#",
        "prefix": "oc",
        "classes": {
            "Skill": {
                "description": "Base class for all skills",
                "properties": ["resolvesIntent", "requiresState", "yieldsState", "handlesFailure", "generatedBy"]
            },
            "ExecutableSkill": {
                "description": "Skill with code payload",
                "properties": ["hasPayload"]
            },
            "DeclarativeSkill": {
                "description": "Knowledge-only skill",
                "properties": []
            },
            "ExecutionPayload": {
                "description": "Container for executable code",
                "properties": ["executor", "code", "executionPath", "timeout"]
            },
            "State": {
                "description": "System state node",
                "properties": []
            },
            "KnowledgeNode": {
                "description": "Epistemic knowledge",
                "properties": ["directiveContent", "appliesToContext", "hasRationale", "severityLevel"]
            }
        },
        "properties": {
            "resolvesIntent": {
                "type": "string",
                "description": "User intent this skill handles",
                "convention": "verb_noun (e.g., create_pdf, send_email)"
            },
            "requiresState": {
                "type": "IRI",
                "description": "Precondition state"
            },
            "yieldsState": {
                "type": "IRI",
                "description": "Postcondition state after success"
            },
            "handlesFailure": {
                "type": "IRI",
                "description": "State after failure"
            },
            "dependsOnSkill": {
                "type": "IRI",
                "description": "Skill prerequisite"
            },
            "contradicts": {
                "type": "IRI",
                "description": "Mutually exclusive skill"
            }
        },
        "example_queries": [
            "SELECT ?skill WHERE { ?skill oc:resolvesIntent \"create_pdf\" }",
            "SELECT ?skill WHERE { ?skill oc:requiresState oc:FileExists }",
            "SELECT ?skill ?intent WHERE { ?skill oc:resolvesIntent ?intent }"
        ]
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_schema_size() {
        let schema = get_schema_resource();
        let json_str = serde_json::to_string(&schema).unwrap();
        // Should be under 4KB uncompressed
        assert!(json_str.len() < 4096, "Schema too large: {} bytes", json_str.len());
    }

    #[test]
    fn test_schema_has_required_fields() {
        let schema = get_schema_resource();
        assert!(schema.get("version").is_some());
        assert!(schema.get("classes").is_some());
        assert!(schema.get("properties").is_some());
        assert!(schema.get("example_queries").is_some());
    }
}
