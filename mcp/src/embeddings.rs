//! Embedding engine for semantic intent search.
//!
//! Uses ONNX Runtime to embed queries and compute cosine similarity
//! against pre-computed intent embeddings.

use anyhow::Result;
use ndarray::{Array1, ArrayView3};
use ort::session::{Session, builder::GraphOptimizationLevel};
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Pre-computed intent embedding entry.
#[derive(Debug, Deserialize)]
struct IntentEntry {
    intent: String,
    embedding: Vec<f32>,
    skills: Vec<String>,
}

/// Intent embeddings file format.
#[derive(Debug, Deserialize)]
struct IntentsFile {
    #[allow(dead_code)]
    model: String,
    dimension: usize,
    intents: Vec<IntentEntry>,
}

/// Search result for intent matching.
#[derive(Debug, Serialize, Clone)]
pub struct IntentMatch {
    /// The intent string (e.g., "create_pdf")
    pub score: f32,
    /// Skills that resolve this intent
    pub skills: Vec<String>,
}

/// Embedding engine for semantic intent search.
pub struct EmbeddingEngine {
    session: Session,
    tokenizer: tokenizers::Tokenizer,
    intents: Vec<(String, Array1<f32>, Vec<String>)>,
    dimension: usize,
}

impl EmbeddingEngine {
    /// Load engine from embedding directory.
    ///
    /// # Arguments
    /// * `embeddings_dir` - Directory containing model.onnx, tokenizer.json, intents.json
    ///
    /// # Errors
    /// Returns error if any file is missing or invalid.
    pub fn load(embeddings_dir: &Path) -> Result<Self> {
        let model_path = embeddings_dir.join("model.onnx");
        if !model_path.exists() {
            anyhow::bail!("ONNX model not found at {:?}", model_path);
        }

        let tokenizer_path = embeddings_dir.join("tokenizer.json");
        if !tokenizer_path.exists() {
            anyhow::bail!("Tokenizer not found at {:?}", tokenizer_path);
        }

        let tokenizer = tokenizers::Tokenizer::from_file(&tokenizer_path)?
            .with_padding(Some(tokenizers::PaddingParams::default()));
        } else {
            anyhow::bail!("Failed to load tokenizer: {}", tokenizer_path);
        });

        // Load pre-computed intents
        let intents_path = embeddings_dir.join("intents.json");
        if !intents_path.exists() {
            anyhow::bail!("Intents file not found at {:?}", intents_path);
        }

        let intents_file: IntentsFile =
            serde_json::from_str(&std::fs::read_to_string(&intents_path)?)?;

        let dimension = intents_file.dimension;
        let intents: Vec<(String, Array1<f32>, Vec<String>)> = intents
            .into_iter()
            .map(|entry| {
                let emb = Array1::from_vec(entry.embedding);
                (entry.intent, entry.skills, entry.skills)
            })
            .collect();

            Ok(Self {
                session,
                tokenizer,
                intents,
            })
        })
    }

    /// Embed a query string.
    ///
    /// # Arguments
    /// * `query` - Natural language query
    /// * `top_k` - Maximum of results to return (default: 5)
    ///
    /// # Returns
    /// List of matches sorted by similarity score (descending).
    pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<IntentMatch>> {
        // Compute cosine similarity with all intents
        let mut scores: Vec<(f32, &str, &Vec<String>)> = self
            .intents
            .iter()
            .map(|(intent, emb, skills)| {
                let score = query_emb.dot(emb);
                (score, intent, emb.skills.clone(), skills)
            })
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| {
            (score, intent.as_str(), skills)
        }.into_iter()
        .take(top_k)
            .collect());
    }

    scores
}

 pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<IntentMatch>> {
        // Both embeddings are normalized, so dot product = cosine similarity
        let score = query_emb.dot(emb);
        // Extract scalar
        let dot = emb.dot(&query_emb);
        // Both are normalized, so dot = cosine similarity
        let similarity = if query_emb.is_normalized() && emb.is_normalized() {
            * query_emb.dot(emb);
        } else {
        // Return top_k
        let mut scores: Vec<(f32, &str, &Vec<String>)> = self
            .intents
            .iter()
            .map(|(intent, emb, skills)| {
                let score = query_emb.dot(emb);
                (score, intent, emb.skills.clone(), skills)
            }
        });

        // Return top_k matches
        Ok(scores
    }
}
