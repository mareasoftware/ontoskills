//! Embedding engine for semantic intent search.
//!
//! Uses ONNX Runtime and tokenizers to compute embeddings on-the-fly
//! and perform semantic search via cosine similarity.

use anyhow::Result;
use ndarray::{Array1, Array2};
use ort::session::Session;
use ort::value::TensorRef;
use serde::{Deserialize, Serialize};
use std::path::Path;
use tokenizers::Tokenizer;

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
    pub intent: String,
    /// Cosine similarity score
    pub score: f32,
    /// Skills that resolve this intent
    pub skills: Vec<String>,
}

/// Embedding engine for semantic intent search.
///
/// Uses ONNX Runtime for inference and tokenizers for text processing.
/// Loads pre-computed intent embeddings and computes query embeddings on-the-fly.
pub struct EmbeddingEngine {
    session: Session,
    tokenizer: Tokenizer,
    intents: Vec<(String, Array1<f32>, Vec<String>)>,
    dimension: usize,
    input_names: Vec<String>,
}

impl EmbeddingEngine {
    /// Load engine from embedding directory.
    ///
    /// # Arguments
    /// * `embeddings_dir` - Directory containing model.onnx, tokenizer.json, and intents.json
    ///
    /// # Errors
    /// Returns error if any required file is missing or invalid.
    pub fn load(embeddings_dir: &Path) -> Result<Self> {
        // Load ONNX model
        let model_path = embeddings_dir.join("model.onnx");
        if !model_path.exists() {
            anyhow::bail!("ONNX model not found at {:?}", model_path);
        }

        // Build session with explicit error handling
        let session = Session::builder()
            .map_err(|e| anyhow::anyhow!("Failed to create session builder: {}", e))?
            .with_intra_threads(1)
            .map_err(|e| anyhow::anyhow!("Failed to set thread count: {}", e))?
            .commit_from_file(&model_path)
            .map_err(|e| anyhow::anyhow!("Failed to load ONNX model: {}", e))?;

        // Get input names from model metadata
        let input_names: Vec<String> = session
            .inputs()
            .iter()
            .map(|i| i.name().to_string())
            .collect();

        // Validate model inputs using extracted helper
        match validate_model_inputs(&input_names) {
            InputValidation::Valid { has_token_type_ids } => {
                if has_token_type_ids {
                    eprintln!(
                        "Warning: Model requires 'token_type_ids' - will use zeros (single sequence)"
                    );
                }
            }
            InputValidation::MissingRequired { missing } => {
                anyhow::bail!(
                    "Model requires 'input_ids' and 'attention_mask' inputs. Missing: {:?}, found: {:?}",
                    missing,
                    input_names
                );
            }
            InputValidation::Unsupported { unsupported } => {
                anyhow::bail!(
                    "Model has unsupported inputs {:?}. Only 'input_ids', 'attention_mask', and 'token_type_ids' are supported.",
                    unsupported
                );
            }
        }

        // Load tokenizer
        let tokenizer_path = embeddings_path(embeddings_dir, "tokenizer.json");
        if !tokenizer_path.exists() {
            anyhow::bail!("Tokenizer not found at {:?}", tokenizer_path);
        }
        let tokenizer = Tokenizer::from_file(&tokenizer_path)
            .map_err(|e| anyhow::anyhow!("Failed to load tokenizer: {}", e))?;

        // Load pre-computed intents
        let intents_path = embeddings_dir.join("intents.json");
        if !intents_path.exists() {
            anyhow::bail!("Intents file not found at {:?}", intents_path);
        }

        let intents_file: IntentsFile =
            serde_json::from_str(&std::fs::read_to_string(&intents_path)?)?;

        let dimension = intents_file.dimension;
        let mut intents: Vec<(String, Array1<f32>, Vec<String>)> = Vec::new();

        for entry in intents_file.intents {
            // Validate embedding dimension matches expected
            if entry.embedding.len() != dimension {
                anyhow::bail!(
                    "Intent '{}' has embedding dimension {} but expected {}",
                    entry.intent,
                    entry.embedding.len(),
                    dimension
                );
            }
            // Normalize embedding for cosine similarity (in case intents.json wasn't normalized)
            let emb = normalize_embedding(&Array1::from_vec(entry.embedding));
            intents.push((entry.intent, emb, entry.skills));
        }

        Ok(Self {
            session,
            tokenizer,
            intents,
            dimension,
            input_names,
        })
    }

    /// Tokenize a query string for ONNX inference.
    fn tokenize(&self, query: &str) -> Result<(Vec<i64>, Vec<i64>)> {
        let encoded = self
            .tokenizer
            .encode(query, true)
            .map_err(|e| anyhow::anyhow!("Tokenization failed: {}", e))?;

        let input_ids: Vec<i64> = encoded.get_ids().iter().map(|&id| id as i64).collect();
        let attention_mask: Vec<i64> = encoded
            .get_attention_mask()
            .iter()
            .map(|&m| m as i64)
            .collect();

        Ok((input_ids, attention_mask))
    }

    /// Find input index by name.
    fn find_input_index(&self, name: &str) -> Option<usize> {
        self.input_names.iter().position(|n| n == name)
    }

    /// Run ONNX inference to get query embedding.
    fn infer_embedding(&mut self, input_ids: &[i64], attention_mask: &[i64]) -> Result<Array1<f32>> {
        let seq_len = input_ids.len();

        // Create input tensors as owned arrays
        let input_ids_array: Array2<i64> =
            Array2::from_shape_vec((1, seq_len), input_ids.to_vec())?;
        let attention_mask_array: Array2<i64> =
            Array2::from_shape_vec((1, seq_len), attention_mask.to_vec())?;

        // Create tensor references from owned arrays
        let input_ids_tensor = TensorRef::from_array_view(&input_ids_array)
            .map_err(|e| anyhow::anyhow!("Failed to create input_ids tensor: {}", e))?;
        let attention_mask_tensor = TensorRef::from_array_view(&attention_mask_array)
            .map_err(|e| anyhow::anyhow!("Failed to create attention_mask tensor: {}", e))?;

        // Find input indices by name (not position)
        let input_ids_idx = self.find_input_index("input_ids")
            .ok_or_else(|| anyhow::anyhow!("Model missing 'input_ids' input"))?;
        let attention_mask_idx = self.find_input_index("attention_mask")
            .ok_or_else(|| anyhow::anyhow!("Model missing 'attention_mask' input"))?;

        // Check if model requires token_type_ids (common for BERT-like models)
        let has_token_type_ids = self.input_names.iter().any(|n| n == "token_type_ids");

        if has_token_type_ids {
            // Create zeros tensor for token_type_ids (single sequence, all tokens are type 0)
            let token_type_ids_array: Array2<i64> = Array2::zeros((1, seq_len));
            let token_type_ids_tensor = TensorRef::from_array_view(&token_type_ids_array)
                .map_err(|e| anyhow::anyhow!("Failed to create token_type_ids tensor: {}", e))?;
            let token_type_ids_idx = self.find_input_index("token_type_ids")
                .ok_or_else(|| anyhow::anyhow!("Model missing 'token_type_ids' input"))?;

            // Run inference with token_type_ids
            let outputs = self
                .session
                .run(ort::inputs![
                    &self.input_names[input_ids_idx] => input_ids_tensor,
                    &self.input_names[attention_mask_idx] => attention_mask_tensor,
                    &self.input_names[token_type_ids_idx] => token_type_ids_tensor,
                ])
                .map_err(|e| anyhow::anyhow!("ONNX inference failed: {}", e))?;

            Self::extract_embedding_from_outputs(self.dimension, outputs, attention_mask)
        } else {
            // Run inference with just input_ids and attention_mask
            let outputs = self
                .session
                .run(ort::inputs![
                    &self.input_names[input_ids_idx] => input_ids_tensor,
                    &self.input_names[attention_mask_idx] => attention_mask_tensor,
                ])
                .map_err(|e| anyhow::anyhow!("ONNX inference failed: {}", e))?;

            Self::extract_embedding_from_outputs(self.dimension, outputs, attention_mask)
        }
    }

    /// Extract embedding from ONNX outputs.
    fn extract_embedding_from_outputs(
        dimension: usize,
        outputs: ort::session::SessionOutputs,
        attention_mask: &[i64],
    ) -> Result<Array1<f32>> {
        // Extract embedding from first output
        let output = &outputs[0];

        // Get tensor data as (shape, data) tuple
        let (shape, data) = output
            .try_extract_tensor::<f32>()
            .map_err(|e| anyhow::anyhow!("Failed to extract tensor: {}", e))?;

        // Handle different output shapes
        match shape.len() {
            // 2D output [batch, hidden_dim] - already pooled (e.g., some sentence-transformers exports)
            2 => {
                let batch = shape[0] as usize;
                let hidden = shape[1] as usize;

                if hidden != dimension {
                    anyhow::bail!(
                        "Model output dimension {} does not match expected embedding dimension {}",
                        hidden, dimension
                    );
                }

                // Validate batch size is 1 (we only process single queries)
                if batch != 1 {
                    anyhow::bail!(
                        "Expected batch size 1 but got {}. This engine only supports single-query inference.",
                        batch
                    );
                }

                // Reshape to 1D (take first/only batch)
                let embedding = Array1::from_vec(data.to_vec());

                // Normalize for cosine similarity
                Ok(normalize_embedding(&embedding))
            }
            // 3D output [batch, seq_len, hidden_dim] - requires mean pooling
            3 => {
                let batch = shape[0] as usize;
                let seq = shape[1] as usize;
                let hidden = shape[2] as usize;

                // Validate batch size is 1 (we only process single queries)
                if batch != 1 {
                    anyhow::bail!(
                        "Expected batch size 1 but got {}. This engine only supports single-query inference.",
                        batch
                    );
                }

                // Reshape data to 3D array
                let tensor_3d: ndarray::Array3<f32> =
                    ndarray::ArrayBase::from_shape_vec((batch, seq, hidden), data.to_vec())?;

                // Mean pooling: average over sequence dimension
                let embedding = mean_pool_embedding(&tensor_3d, attention_mask, dimension)?;

                // Normalize for cosine similarity
                Ok(normalize_embedding(&embedding))
            }
            // Unsupported shape
            _ => {
                anyhow::bail!(
                    "Unsupported model output shape {:?}. Expected 2D [batch, hidden_dim] or 3D [batch, seq_len, hidden_dim]",
                    shape
                );
            }
        }
    }

    /// Compute cosine similarity between two embeddings.
    fn cosine_similarity(a: &Array1<f32>, b: &Array1<f32>) -> f32 {
        let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
        // Since embeddings are already normalized, dot product = cosine similarity
        dot
    }

    /// Search for intents matching the query.
    ///
    /// # Arguments
    /// * `query` - Natural language query
    /// * `top_k` - Maximum number of results
    ///
    /// # Returns
    /// List of matches sorted by similarity score (descending).
    pub fn search(&mut self, query: &str, top_k: usize) -> Result<Vec<IntentMatch>> {
        if self.intents.is_empty() {
            return Ok(Vec::new());
        }

        // Tokenize query
        let (input_ids, attention_mask) = self.tokenize(query)?;

        // Get query embedding via ONNX inference
        let query_embedding = self.infer_embedding(&input_ids, &attention_mask)?;

        // Compute cosine similarity with all intents
        let mut scores: Vec<(f32, &str, &Vec<String>)> = self
            .intents
            .iter()
            .map(|(intent, emb, skills)| {
                let score = Self::cosine_similarity(&query_embedding, emb);
                (score, intent.as_str(), skills)
            })
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

        // Return top_k
        Ok(scores
            .into_iter()
            .take(top_k)
            .map(|(score, intent, skills)| IntentMatch {
                intent: intent.to_string(),
                score,
                skills: skills.clone(),
            })
            .collect())
    }

    /// Get the number of loaded intents.
    pub fn intent_count(&self) -> usize {
        self.intents.len()
    }
}

/// Mean-pool embedding over sequence dimension with attention mask.
fn mean_pool_embedding(
    tensor: &ndarray::Array3<f32>,
    attention_mask: &[i64],
    dimension: usize,
) -> Result<Array1<f32>> {
    // tensor shape: [batch, seq_len, hidden_dim]
    let (_, seq_len, hidden_dim) = (tensor.shape()[0], tensor.shape()[1], tensor.shape()[2]);

    // Validate dimension matches expected
    if hidden_dim != dimension {
        anyhow::bail!(
            "Model output dimension {} does not match expected embedding dimension {}",
            hidden_dim,
            dimension
        );
    }

    let mut summed = Array1::zeros(hidden_dim);
    let mut count = 0.0f32;

    for i in 0..seq_len {
        // Default to 0 (exclude) if attention_mask is missing - padded tokens should be excluded
        if attention_mask.get(i).copied().unwrap_or(0) == 1 {
            for j in 0..hidden_dim {
                summed[j] += tensor[[0, i, j]];
            }
            count += 1.0;
        }
    }

    if count == 0.0 {
        anyhow::bail!(
            "Attention mask contains all zeros - no valid tokens to pool. This usually indicates empty or malformed input."
        );
    }
    summed.mapv_inplace(|x| x / count);

    Ok(summed)
}

/// L2 normalize embedding for cosine similarity.
fn normalize_embedding(embedding: &Array1<f32>) -> Array1<f32> {
    let norm: f32 = embedding.iter().map(|x| x * x).sum::<f32>().sqrt();
    if norm > 0.0 {
        embedding / norm
    } else {
        embedding.clone()
    }
}

/// Find tokenizer file with fallback locations.
fn embeddings_path(base: &Path, name: &str) -> std::path::PathBuf {
    // Try base path first
    let direct = base.join(name);
    if direct.exists() {
        return direct;
    }

    // Fallback: look in model subdirectory (HuggingFace format)
    base.join("model").join(name)
}

/// Result of validating model input names.
#[derive(Debug, PartialEq)]
pub(crate) enum InputValidation {
    /// Inputs are valid, with optional token_type_ids support
    Valid { has_token_type_ids: bool },
    /// Missing required inputs
    MissingRequired { missing: Vec<String> },
    /// Has unsupported inputs that will cause failure
    Unsupported { unsupported: Vec<String> },
}

/// Validate model input names against supported inputs.
/// This is a pure function for easy testing without ONNX fixtures.
pub(crate) fn validate_model_inputs(input_names: &[String]) -> InputValidation {
    let has_input_ids = input_names.iter().any(|n| n == "input_ids");
    let has_attention_mask = input_names.iter().any(|n| n == "attention_mask");
    let has_token_type_ids = input_names.iter().any(|n| n == "token_type_ids");

    // Check for missing required inputs
    let mut missing = Vec::new();
    if !has_input_ids {
        missing.push("input_ids".to_string());
    }
    if !has_attention_mask {
        missing.push("attention_mask".to_string());
    }
    if !missing.is_empty() {
        return InputValidation::MissingRequired { missing };
    }

    // Check for unsupported inputs
    let unsupported: Vec<String> = input_names
        .iter()
        .filter(|n| !["input_ids", "attention_mask", "token_type_ids"].contains(&n.as_str()))
        .cloned()
        .collect();

    if !unsupported.is_empty() {
        return InputValidation::Unsupported { unsupported };
    }

    InputValidation::Valid { has_token_type_ids }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embedding_engine_load_missing_files() {
        let result = EmbeddingEngine::load(Path::new("/nonexistent"));
        assert!(result.is_err());
    }

    #[test]
    fn test_cosine_similarity_identical() {
        let a = Array1::from_vec(vec![1.0, 0.0, 0.0]);
        let b = Array1::from_vec(vec![1.0, 0.0, 0.0]);
        let sim = EmbeddingEngine::cosine_similarity(&a, &b);
        assert!((sim - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_cosine_similarity_orthogonal() {
        let a = Array1::from_vec(vec![1.0, 0.0, 0.0]);
        let b = Array1::from_vec(vec![0.0, 1.0, 0.0]);
        let sim = EmbeddingEngine::cosine_similarity(&a, &b);
        assert!(sim.abs() < 0.001);
    }

    #[test]
    fn test_normalize_embedding() {
        let emb = Array1::from_vec(vec![3.0, 4.0]);
        let normalized = normalize_embedding(&emb);
        let norm: f32 = normalized.iter().map(|x| x * x).sum::<f32>().sqrt();
        assert!((norm - 1.0).abs() < 0.001);
    }

    // Tests for input validation (addresses Copilot review comment)
    #[test]
    fn test_validate_inputs_valid_minimal() {
        let inputs = vec!["input_ids".to_string(), "attention_mask".to_string()];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::Valid { has_token_type_ids: false });
    }

    #[test]
    fn test_validate_inputs_valid_with_token_type_ids() {
        let inputs = vec![
            "input_ids".to_string(),
            "attention_mask".to_string(),
            "token_type_ids".to_string(),
        ];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::Valid { has_token_type_ids: true });
    }

    #[test]
    fn test_validate_inputs_missing_input_ids() {
        let inputs = vec!["attention_mask".to_string()];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::MissingRequired {
            missing: vec!["input_ids".to_string()]
        });
    }

    #[test]
    fn test_validate_inputs_missing_attention_mask() {
        let inputs = vec!["input_ids".to_string()];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::MissingRequired {
            missing: vec!["attention_mask".to_string()]
        });
    }

    #[test]
    fn test_validate_inputs_missing_both_required() {
        let inputs: Vec<String> = vec![];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::MissingRequired {
            missing: vec!["input_ids".to_string(), "attention_mask".to_string()]
        });
    }

    #[test]
    fn test_validate_inputs_unsupported_position_ids() {
        let inputs = vec![
            "input_ids".to_string(),
            "attention_mask".to_string(),
            "position_ids".to_string(),
        ];
        let result = validate_model_inputs(&inputs);
        assert_eq!(result, InputValidation::Unsupported {
            unsupported: vec!["position_ids".to_string()]
        });
    }

    #[test]
    fn test_validate_inputs_unsupported_multiple() {
        let inputs = vec![
            "input_ids".to_string(),
            "attention_mask".to_string(),
            "position_ids".to_string(),
            "token_type_embeddings".to_string(),
        ];
        let result = validate_model_inputs(&inputs);
        match result {
            InputValidation::Unsupported { unsupported } => {
                assert!(unsupported.contains(&"position_ids".to_string()));
                assert!(unsupported.contains(&"token_type_embeddings".to_string()));
            }
            _ => panic!("Expected Unsupported variant"),
        }
    }
}
