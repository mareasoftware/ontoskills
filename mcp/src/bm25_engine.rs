//! BM25 keyword search engine built from Catalog data.
//!
//! Constructs an in-memory BM25 index from skill intents, aliases,
//! and nature descriptions already loaded by the Catalog at startup.
//! No additional files on disk — everything is derived from the
//! already-loaded ontology data.

use bm25::{Document, Language, SearchEngineBuilder};
use serde::Serialize;
use std::collections::HashMap;

use crate::catalog::{Catalog, CatalogError, SkillSummary};

/// A single BM25 search result.
#[derive(Debug, Serialize, Clone)]
pub struct Bm25Match {
    /// Skill identifier (short form, e.g., "xlsx")
    pub skill_id: String,
    /// Skill identifier (qualified, e.g., "marea/office/xlsx")
    pub qualified_id: String,
    /// BM25 score * quality multiplier
    pub score: f32,
    /// Which field matched best: "intent", "alias", or "nature"
    pub matched_by: String,
    /// Skill intents
    pub intents: Vec<String>,
    /// Skill aliases
    pub aliases: Vec<String>,
    /// Trust tier
    pub trust_tier: String,
}

/// Quality multiplier based on trust tier.
fn quality_multiplier(trust_tier: &str) -> f32 {
    match trust_tier {
        "official" => 1.2,
        "local" => 1.0,
        "verified" => 1.0,
        "community" => 0.8,
        _ => 1.0,
    }
}

/// In-memory BM25 search engine for skill discovery.
pub struct Bm25Engine {
    engine: bm25::SearchEngine<String>,
    /// Skill metadata indexed by qualified_id for result enrichment.
    skills: HashMap<String, SkillSummary>,
    trust_tiers: HashMap<String, String>,
}

impl Bm25Engine {
    /// Build a BM25 engine from the Catalog's loaded skill data.
    ///
    /// For each skill, concatenates intents, aliases, and nature into
    /// a single searchable document. Uses English stemming and stop words.
    pub fn from_catalog(catalog: &Catalog) -> Result<Self, CatalogError> {
        let skills = catalog.list_skills()?;
        let mut documents = Vec::with_capacity(skills.len());
        let mut skill_map = HashMap::new();
        let mut trust_tiers = HashMap::new();

        for skill in &skills {
            // Build searchable contents: intents + aliases + nature
            let mut parts = Vec::new();
            parts.extend(skill.intents.iter().cloned());
            parts.extend(skill.aliases.iter().cloned());
            parts.push(skill.nature.clone());

            let contents = parts.join(" ");

            documents.push(Document {
                id: skill.qualified_id.clone(),
                contents,
            });

            skill_map.insert(skill.qualified_id.clone(), skill.clone());
            trust_tiers.insert(skill.id.clone(), skill.trust_tier.clone());
        }

        let engine = if documents.is_empty() {
            // Build an empty engine with a sensible avgdl guess
            SearchEngineBuilder::<String>::with_avgdl(10.0).build()
        } else {
            SearchEngineBuilder::<String>::with_documents(Language::English, documents).build()
        };

        Ok(Self {
            engine,
            skills: skill_map,
            trust_tiers,
        })
    }

    /// Search for skills matching the query.
    ///
    /// Returns results sorted by score (descending), filtered by
    /// adaptive cutoff (minimum threshold + gap detection).
    pub fn search(&self, query: &str, top_k: usize) -> Vec<Bm25Match> {
        let results = self.engine.search(query, top_k * 2); // fetch extra for post-filtering

        let mut matches: Vec<Bm25Match> = results
            .into_iter()
            .filter_map(|result| {
                let skill = self.skills.get(&result.document.id)?;
                let tier = self
                    .trust_tiers
                    .get(&skill.id)
                    .map(|t| t.as_str())
                    .unwrap_or("verified");
                let multiplier = quality_multiplier(tier);
                let score = result.score * multiplier;

                Some(Bm25Match {
                    skill_id: skill.id.clone(),
                    qualified_id: skill.qualified_id.clone(),
                    score,
                    matched_by: "keyword".to_string(),
                    intents: skill.intents.clone(),
                    aliases: skill.aliases.clone(),
                    trust_tier: skill.trust_tier.clone(),
                })
            })
            .collect();

        // Sort by score descending
        matches.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));

        // Apply adaptive cutoff
        let cutoff = adaptive_cutoff(&matches, 0.1, 0.15);
        matches.truncate(cutoff.min(top_k));

        matches
    }

}

/// Adaptive cutoff for search results.
///
/// Returns the number of results to keep, based on:
/// - Minimum score threshold
/// - Gap detection (significant drop in score)
fn adaptive_cutoff(matches: &[Bm25Match], min_threshold: f32, gap_threshold: f32) -> usize {
    if matches.is_empty() {
        return 0;
    }

    // If top score is below threshold, return nothing
    if matches[0].score < min_threshold {
        return 0;
    }

    // Look for significant gap
    for i in 1..matches.len() {
        let gap = matches[i - 1].score - matches[i].score;
        if gap > gap_threshold && matches[i].score < min_threshold {
            return i;
        }
    }

    // No gap found - include all above minimum threshold
    matches
        .iter()
        .position(|m| m.score < min_threshold)
        .unwrap_or(matches.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quality_multiplier_tiers() {
        assert!((quality_multiplier("official") - 1.2).abs() < 0.001);
        assert!((quality_multiplier("local") - 1.0).abs() < 0.001);
        assert!((quality_multiplier("verified") - 1.0).abs() < 0.001);
        assert!((quality_multiplier("community") - 0.8).abs() < 0.001);
        assert!((quality_multiplier("unknown") - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_adaptive_cutoff_empty() {
        let matches: Vec<Bm25Match> = vec![];
        assert_eq!(adaptive_cutoff(&matches, 0.1, 0.15), 0);
    }

    #[test]
    fn test_adaptive_cutoff_all_below_threshold() {
        let matches = vec![fake_match("a", 0.05), fake_match("b", 0.03)];
        assert_eq!(adaptive_cutoff(&matches, 0.1, 0.15), 0);
    }

    #[test]
    fn test_adaptive_cutoff_all_above_threshold() {
        let matches = vec![fake_match("a", 0.9), fake_match("b", 0.8), fake_match("c", 0.7)];
        assert_eq!(adaptive_cutoff(&matches, 0.1, 0.15), 3);
    }

    #[test]
    fn test_adaptive_cutoff_gap_triggers() {
        let matches = vec![
            fake_match("a", 0.9),
            fake_match("b", 0.85),
            fake_match("c", 0.02),
        ];
        // Gap between b (0.85) and c (0.02) = 0.83 > 0.15, and c < 0.1
        assert_eq!(adaptive_cutoff(&matches, 0.1, 0.15), 2);
    }

    fn fake_match(id: &str, score: f32) -> Bm25Match {
        Bm25Match {
            skill_id: id.to_string(),
            qualified_id: format!("pkg/{id}"),
            score,
            matched_by: "keyword".to_string(),
            intents: vec![],
            aliases: vec![],
            trust_tier: "local".to_string(),
        }
    }
}
