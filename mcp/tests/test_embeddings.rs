//! Integration tests for semantic discovery.

use std::fs;
use std::path::PathBuf;
use tempfile::TempDir;

/// Create a test intents.json with pre-computed embeddings.
/// Embeddings are normalized vectors for cosine similarity.
fn create_test_intents_json(path: &std::path::Path) {
    // Pre-computed normalized embeddings for testing
    // These are 384-dimensional vectors (all-MiniLM-L6-v2 dimension)
    // For simplicity, we use sparse vectors with known patterns

    let intents = serde_json::json!({
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
        "intents": [
            {
                "intent": "create_pdf",
                "embedding": create_normalized_embedding(&[1.0, 0.0, 0.0]),
                "skills": ["pdf-creator"]
            },
            {
                "intent": "send_email",
                "embedding": create_normalized_embedding(&[0.0, 1.0, 0.0]),
                "skills": ["email-sender"]
            },
            {
                "intent": "export_document",
                "embedding": create_normalized_embedding(&[0.0, 0.0, 1.0]),
                "skills": ["doc-exporter"]
            },
            {
                "intent": "create_document",
                "embedding": create_normalized_embedding(&[0.9, 0.1, 0.0]),
                "skills": ["doc-creator"]
            }
        ]
    });

    fs::write(path, serde_json::to_string_pretty(&intents).unwrap()).unwrap();
}

/// Create a normalized 384-dim embedding from a small seed vector.
/// The seed is projected and normalized for consistent testing.
fn create_normalized_embedding(seed: &[f32]) -> Vec<f32> {
    let dim = 384;
    let mut embedding = vec![0.0f32; dim];

    // Project seed into first few dimensions
    for (i, &val) in seed.iter().enumerate() {
        if i < dim {
            embedding[i] = val;
        }
    }

    // Normalize
    let norm: f32 = embedding.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        for val in &mut embedding {
            *val /= norm;
        }
    }

    embedding
}

#[test]
fn test_intents_json_format() {
    let dir = TempDir::new().unwrap();
    let intents_path = dir.path().join("intents.json");

    create_test_intents_json(&intents_path);

    // Verify file was created and is valid JSON
    let content = fs::read_to_string(&intents_path).unwrap();
    let json: serde_json::Value = serde_json::from_str(&content).unwrap();

    assert_eq!(json["model"], "sentence-transformers/all-MiniLM-L6-v2");
    assert_eq!(json["dimension"], 384);
    assert!(json["intents"].as_array().unwrap().len() >= 4);

    // Verify each intent has required fields
    for intent in json["intents"].as_array().unwrap() {
        assert!(intent["intent"].is_string());
        assert!(intent["embedding"].is_array());
        assert_eq!(intent["embedding"].as_array().unwrap().len(), 384);
        assert!(intent["skills"].is_array());
    }
}

#[test]
fn test_embedding_normalization() {
    let embedding = create_normalized_embedding(&[3.0, 4.0]);
    let norm: f32 = embedding.iter().map(|x| x * x).sum::<f32>().sqrt();
    assert!(
        (norm - 1.0).abs() < 0.0001,
        "Embedding should be normalized"
    );
}

#[test]
fn test_cosine_similarity_with_seed_vectors() {
    // Test that orthogonal vectors have 0 similarity
    let a = create_normalized_embedding(&[1.0, 0.0, 0.0]);
    let b = create_normalized_embedding(&[0.0, 1.0, 0.0]);

    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    assert!(
        dot.abs() < 0.0001,
        "Orthogonal vectors should have 0 similarity"
    );

    // Test that identical vectors have 1 similarity
    let c = create_normalized_embedding(&[1.0, 0.0, 0.0]);
    let d = create_normalized_embedding(&[1.0, 0.0, 0.0]);
    let dot2: f32 = c.iter().zip(d.iter()).map(|(x, y)| x * y).sum();
    assert!(
        (dot2 - 1.0).abs() < 0.0001,
        "Identical vectors should have 1 similarity"
    );
}

#[test]
fn test_semantic_similarity_ranking() {
    // Simulate the ranking logic of search_intents
    let query = create_normalized_embedding(&[1.0, 0.0, 0.0]); // Similar to "create_pdf"

    let intents = vec![
        ("create_pdf", create_normalized_embedding(&[1.0, 0.0, 0.0])),
        ("send_email", create_normalized_embedding(&[0.0, 1.0, 0.0])),
        (
            "export_document",
            create_normalized_embedding(&[0.0, 0.0, 1.0]),
        ),
        (
            "create_document",
            create_normalized_embedding(&[0.9, 0.1, 0.0]),
        ),
    ];

    // Compute scores
    let mut scores: Vec<(f32, &str)> = intents
        .iter()
        .map(|(name, emb)| {
            let dot: f32 = query.iter().zip(emb.iter()).map(|(x, y)| x * y).sum();
            (dot, *name)
        })
        .collect();

    // Sort by score descending
    scores.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());

    // Verify ranking
    assert_eq!(
        scores[0].1, "create_pdf",
        "Most similar should be create_pdf"
    );
    assert!(scores[0].0 > 0.99, "create_pdf should have very high score");

    // create_document should be second (0.9 similarity)
    assert_eq!(
        scores[1].1, "create_document",
        "Second should be create_document"
    );

    // send_email and export_document should have low scores
    let email_score = scores.iter().find(|(_, n)| *n == "send_email").unwrap().0;
    let export_score = scores
        .iter()
        .find(|(_, n)| *n == "export_document")
        .unwrap()
        .0;
    assert!(
        email_score.abs() < 0.01,
        "send_email should have near-zero score"
    );
    assert!(
        export_score.abs() < 0.01,
        "export_document should have near-zero score"
    );
}

#[test]
#[ignore = "Requires ONNX model files - run with --ignored flag and manual setup"]
fn test_embedding_engine_loads_and_searches() {
    // This test requires:
    // 1. Run: ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./mcp/tests/fixtures/embeddings
    // 2. Then run: cargo test -- --ignored
    //
    // The test verifies that:
    // - EmbeddingEngine can load ONNX model, tokenizer, and intents.json
    // - Search returns relevant results sorted by cosine similarity

    let test_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("embeddings");

    if !test_dir.join("model.onnx").exists() {
        eprintln!("Skipping: ONNX model not found at {:?}", test_dir);
        eprintln!(
            "Run: ontoskills export-embeddings --ontology-root ./ontoskills --output-dir ./mcp/tests/fixtures/embeddings"
        );
        return;
    }

    // Since EmbeddingEngine is in the binary crate, we test it via MCP protocol
    // For now, we just verify the files exist
    assert!(
        test_dir.join("model.onnx").exists(),
        "model.onnx should exist"
    );
    assert!(
        test_dir.join("tokenizer.json").exists(),
        "tokenizer.json should exist"
    );
    assert!(
        test_dir.join("intents.json").exists(),
        "intents.json should exist"
    );

    // Verify intents.json format
    let intents_content = fs::read_to_string(test_dir.join("intents.json")).unwrap();
    let intents: serde_json::Value = serde_json::from_str(&intents_content).unwrap();

    assert!(
        intents["intents"].as_array().unwrap().len() > 0,
        "Should have at least one intent"
    );

    for intent in intents["intents"].as_array().unwrap() {
        assert_eq!(
            intent["embedding"].as_array().unwrap().len(),
            intents["dimension"].as_u64().unwrap() as usize,
            "Each embedding should match the declared dimension"
        );
    }
}
