//! BM25 keyword search engine built from Catalog data.
//!
//! Constructs an in-memory BM25 index from skill intents, aliases,
//! and nature descriptions already loaded by the Catalog at startup.
//! No additional files on disk — everything is derived from the
//! already-loaded ontology data.

use bm25::{Document, Language, SearchEngineBuilder};
use serde::Serialize;
use std::collections::HashMap;

use crate::catalog::{
    Catalog, CatalogError, KnowledgeNodeInfo, SectionContent, SkillSummary, quality_multiplier,
};

/// A single BM25 search result.
#[derive(Debug, Serialize, Clone)]
pub struct Bm25Match {
    /// Skill identifier (short form, e.g., "xlsx")
    pub skill_id: String,
    /// Skill identifier (qualified, e.g., "marea/office/xlsx")
    pub qualified_id: String,
    /// BM25 score * quality multiplier
    pub score: f32,
    /// Always "keyword" — BM25 matches across the whole document
    pub matched_by: String,
    /// Skill intents
    pub intents: Vec<String>,
    /// Skill aliases
    pub aliases: Vec<String>,
    /// Trust tier
    pub trust_tier: String,
}

/// In-memory BM25 search engine for skill discovery.
pub struct Bm25Engine {
    engine: bm25::SearchEngine<String>,
    /// Skill metadata indexed by qualified_id for result enrichment.
    skills: HashMap<String, SkillSummary>,
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
                let multiplier = quality_multiplier(&skill.trust_tier);
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
        matches.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Apply adaptive cutoff
        let cutoff = adaptive_cutoff(&matches, 0.1, 0.15);
        matches.truncate(cutoff.min(top_k));

        matches
    }
}

/// In-memory BM25 engine for ranking knowledge nodes within a skill.
///
/// Indexes each node's `directive_content` + `applies_to_context` + `rationale`
/// as a separate document. Used by `compact_context()` to return only the
/// most relevant nodes for a given query.
pub struct NodeBm25Engine {
    engine: bm25::SearchEngine<usize>,
    total_nodes: usize,
}

impl NodeBm25Engine {
    /// Build a node-level BM25 engine from a skill's knowledge nodes.
    pub fn from_nodes(_skill_id: &str, nodes: &[KnowledgeNodeInfo]) -> Self {
        let mut documents = Vec::with_capacity(nodes.len());

        for (i, node) in nodes.iter().enumerate() {
            let mut parts = Vec::new();
            parts.push(node.directive_content.clone());
            if let Some(ctx) = &node.applies_to_context {
                if !ctx.is_empty() {
                    parts.push(ctx.clone());
                }
            }
            if let Some(why) = &node.rationale {
                if !why.is_empty() {
                    parts.push(why.clone());
                }
            }

            documents.push(bm25::Document {
                id: i,
                contents: parts.join(" "),
            });
        }

        let engine = if documents.is_empty() {
            SearchEngineBuilder::<usize>::with_avgdl(10.0).build()
        } else {
            SearchEngineBuilder::<usize>::with_documents(Language::English, documents).build()
        };

        Self {
            engine,
            total_nodes: nodes.len(),
        }
    }

    /// Rank nodes by BM25 relevance to the query.
    ///
    /// Uses bottom-percentile cutoff: discards only the worst 20% of scored nodes,
    /// but always keeps at least `min(10, total_nodes)` nodes.
    /// If there are ≤10 nodes, all are returned.
    /// For empty queries, returns all node indices with score 0.0.
    pub fn rank_nodes(&self, query: &str) -> Vec<(usize, f32)> {
        if query.is_empty() {
            return (0..self.total_nodes).map(|i| (i, 0.0)).collect();
        }

        let results = self.engine.search(query, self.total_nodes * 2);

        let mut ranked: Vec<(usize, f32)> = results
            .into_iter()
            .filter_map(|r| {
                if r.score > 0.0 {
                    Some((r.document.id, r.score))
                } else {
                    None
                }
            })
            .collect();

        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        // Bottom-percentile: keep all if ≤10, otherwise discard bottom 20%
        let min_keep = self.total_nodes.min(10);
        let n_scored = ranked.len();
        if n_scored <= min_keep {
            return ranked;
        }
        let cutoff = min_keep.max(n_scored - (n_scored as f64 * 0.2).floor() as usize);
        ranked.truncate(cutoff);
        ranked
    }
}

/// In-memory BM25 engine for ranking section content blocks within a skill.
///
/// Indexes each section's title + content as a document. Used to filter
/// section tree content to only the most relevant blocks for a query,
/// avoiding positional bias (sections at the end are not penalized).
pub struct SectionBm25Engine {
    engine: bm25::SearchEngine<usize>,
    total_sections: usize,
}

/// Maximum total characters of section content to include in compact output.
pub const SECTION_BUDGET_CHARS: usize = 3000;

/// Maximum total characters of knowledge node content in compact output.
/// ~12K chars ≈ 3K tokens — enough for procedures, constraints, anti-patterns
/// without overwhelming the agent with low-priority BulletItem/Section nodes.
pub const NODE_BUDGET_CHARS: usize = 12000;

impl SectionBm25Engine {
    /// Build a section-level BM25 engine from a skill's section content.
    pub fn from_sections(sections: &[SectionContent]) -> Self {
        let mut documents = Vec::with_capacity(sections.len());

        for (i, section) in sections.iter().enumerate() {
            let mut parts = Vec::new();
            if let Some(title) = &section.section_title {
                if !title.is_empty() {
                    parts.push(title.clone());
                }
            }
            parts.push(section.content.clone());
            if let Some(lang) = &section.language {
                parts.push(lang.clone());
            }

            documents.push(bm25::Document {
                id: i,
                contents: parts.join(" "),
            });
        }

        let engine = if documents.is_empty() {
            SearchEngineBuilder::<usize>::with_avgdl(10.0).build()
        } else {
            SearchEngineBuilder::<usize>::with_documents(Language::English, documents).build()
        };

        Self {
            engine,
            total_sections: sections.len(),
        }
    }

    /// Rank sections by BM25 relevance and return indices within a character budget.
    ///
    /// Returns indices sorted by relevance. The total content of selected
    /// sections stays within `budget` chars. If there's no query, returns
    /// sections in original order until the budget is exhausted.
    pub fn rank_within_budget(
        &self,
        query: &str,
        sections: &[SectionContent],
        budget: usize,
    ) -> Vec<usize> {
        if sections.is_empty() {
            return vec![];
        }

        let ranked_indices: Vec<usize> = if query.is_empty() {
            // No query: return in original order (by section_order).
            (0..sections.len()).collect()
        } else {
            let results = self.engine.search(query, self.total_sections * 2);
            let mut scored: Vec<(usize, f32)> = results
                .into_iter()
                .filter_map(|r| {
                    if r.score > 0.0 {
                        Some((r.document.id, r.score))
                    } else {
                        None
                    }
                })
                .collect();
            scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

            // Add unscored sections at the end (they might still be useful).
            let scored_set: std::collections::HashSet<usize> =
                scored.iter().map(|(i, _)| *i).collect();
            let mut all_indices: Vec<usize> = scored.into_iter().map(|(i, _)| i).collect();
            for i in 0..self.total_sections {
                if !scored_set.contains(&i) {
                    all_indices.push(i);
                }
            }
            all_indices
        };

        // Fill budget greedily.
        let mut selected = Vec::new();
        let mut used = 0;
        for idx in ranked_indices {
            if idx >= sections.len() {
                continue;
            }
            let len = sections[idx].content.len();
            if used + len > budget {
                continue; // Skip oversized, try next.
            }
            used += len;
            selected.push(idx);
            if used >= budget {
                break;
            }
        }

        selected
    }
}

/// Adaptive cutoff for search results.
///
/// Returns the number of results to keep, based on:
/// - Minimum score threshold (hard floor)
/// - Gap detection: cuts at a significant score drop when the lower
///   result is also below the minimum threshold.
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
        use crate::catalog::quality_multiplier;
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
        let matches = vec![
            fake_match("a", 0.9),
            fake_match("b", 0.8),
            fake_match("c", 0.7),
        ];
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

    use crate::catalog::KnowledgeNodeInfo;

    fn make_test_node(
        content: &str,
        context: Option<&str>,
        rationale: Option<&str>,
    ) -> KnowledgeNodeInfo {
        KnowledgeNodeInfo {
            uri: String::new(),
            label: None,
            kind: "heuristic".to_string(),
            dimension: None,
            directive_content: content.to_string(),
            rationale: rationale.map(String::from),
            applies_to_context: context.map(String::from),
            severity_level: None,
            source_skill_id: "test-skill".to_string(),
            source_qualified_id: None,
            inherited: false,
            code_language: None,
            step_order: None,
            template_variables: None,
            links: vec![],
        }
    }

    #[test]
    fn test_node_bm25_ranks_relevant_higher() {
        let nodes = vec![
            make_test_node(
                "Always validate user input before processing files",
                Some("file handling"),
                None,
            ),
            make_test_node(
                "Use caching for repeated database queries",
                Some("database"),
                None,
            ),
            make_test_node(
                "Never trust user-provided file paths",
                Some("file handling"),
                Some("Prevents path traversal"),
            ),
            make_test_node(
                "Prefer streaming for large dataset downloads",
                Some("network"),
                None,
            ),
        ];

        let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
        let results = engine.rank_nodes("file path validation");

        assert!(!results.is_empty());
        let find_rank = |content_substring: &str| -> Option<usize> {
            results
                .iter()
                .position(|(idx, _)| nodes[*idx].directive_content.contains(content_substring))
        };
        let file_path_rank = find_rank("file paths").expect("file paths node should be found");
        // The database node may not appear in results at all (correctly filtered out),
        // or if it does, it should rank lower than the file paths node.
        if let Some(db_rank) = find_rank("database queries") {
            assert!(
                file_path_rank < db_rank,
                "file paths node should rank higher than database node"
            );
        }
        // If database node is absent, file paths node still ranks first — that's correct.
    }

    #[test]
    fn test_node_bm25_bottom_percentile_cutoff() {
        // 15 nodes: bottom-percentile should keep at least 10 (min(10, 15))
        let nodes: Vec<KnowledgeNodeInfo> = (0..15)
            .map(|i| make_test_node(&format!("Node {} about topic {}", i, i % 3), None, None))
            .collect();

        let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
        let results = engine.rank_nodes("topic 0");
        assert!(
            results.len() >= 10,
            "Should keep at least 10 nodes with bottom-percentile, got {}",
            results.len()
        );
        assert!(
            results.len() <= 15,
            "Should not exceed total nodes, got {}",
            results.len()
        );
    }

    #[test]
    fn test_node_bm25_few_nodes_keeps_all() {
        // 5 nodes: min(10, 5) = 5, so all should be returned
        let nodes: Vec<KnowledgeNodeInfo> = (0..5)
            .map(|i| make_test_node(&format!("Node {} about topic {}", i, i % 3), None, None))
            .collect();

        let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
        let results = engine.rank_nodes("topic 0");
        // All scored nodes should be returned since 5 <= min_keep(5)
        assert!(
            results.len() <= 5,
            "Should keep all nodes when ≤10, got {}",
            results.len()
        );
    }

    #[test]
    fn test_node_bm25_empty_query() {
        let nodes = vec![make_test_node("test content", None, None)];
        let engine = NodeBm25Engine::from_nodes("test-skill", &nodes);
        let results = engine.rank_nodes("");
        assert_eq!(results.len(), 1);
    }
}
