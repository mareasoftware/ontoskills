use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::env;
use std::fmt::{Display, Formatter};
use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};

use oxigraph::io::RdfFormat;
use oxigraph::model::Term;
use oxigraph::sparql::{QueryResults, SparqlEvaluator};
use oxigraph::store::Store;
use serde::Serialize;
use serde::Deserialize;

use walkdir::WalkDir;

const DEFAULT_BASE_URI: &str = "https://ontoskills.sh/ontology#";
const DEFAULT_LIMIT: usize = 25;
const MAX_LIMIT: usize = 100;
const DEFAULT_MAX_DEPTH: usize = 10;
const MAX_SKILL_ID_LEN: usize = 64;

const KNOWLEDGE_DIMENSIONS: &[&str] = &[
    "https://ontoskills.sh/ontology#Observability",
    "https://ontoskills.sh/ontology#ResilienceTactic",
    "https://ontoskills.sh/ontology#ResourceProfile",
    "https://ontoskills.sh/ontology#TrustMetric",
    "https://ontoskills.sh/ontology#CognitiveBoundary",
    "https://ontoskills.sh/ontology#ExecutionPhysics",
    "https://ontoskills.sh/ontology#LifecycleHook",
    "https://ontoskills.sh/ontology#NormativeRule",
    "https://ontoskills.sh/ontology#SecurityGuardrail",
    "https://ontoskills.sh/ontology#StrategicInsight",
];

#[derive(Debug)]
pub enum CatalogError {
    Io(std::io::Error),
    Walk(walkdir::Error),
    Oxigraph(String),
    MissingOntologyRoot(PathBuf),
    SkillNotFound(String),
    InvalidInput(String),
    InvalidState(String),
}

impl Display for CatalogError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(err) => write!(f, "I/O error: {err}"),
            Self::Walk(err) => write!(f, "Walk error: {err}"),
            Self::Oxigraph(err) => write!(f, "Oxigraph error: {err}"),
            Self::MissingOntologyRoot(path) => {
                write!(f, "Ontology root not found: {}", path.display())
            }
            Self::SkillNotFound(skill_id) => write!(f, "Skill not found: {skill_id}"),
            Self::InvalidInput(message) => write!(f, "Invalid input: {message}"),
            Self::InvalidState(state) => write!(f, "Invalid state value: {state}"),
        }
    }
}

impl std::error::Error for CatalogError {}

impl From<std::io::Error> for CatalogError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<walkdir::Error> for CatalogError {
    fn from(value: walkdir::Error) -> Self {
        Self::Walk(value)
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SkillType {
    Executable,
    Declarative,
    Unknown,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillSummary {
    pub id: String,
    pub qualified_id: String,
    pub package_id: String,
    pub trust_tier: String,
    pub version: Option<String>,
    pub source: Option<String>,
    pub skill_type: SkillType,
    pub nature: String,
    pub intents: Vec<String>,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillSearchResult {
    pub id: String,
    pub qualified_id: String,
    pub package_id: String,
    pub trust_tier: String,
    pub version: Option<String>,
    pub source: Option<String>,
    pub skill_type: SkillType,
    pub nature: String,
    pub intents: Vec<String>,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
    pub matched_by: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequirementInfo {
    pub requirement_type: String,
    pub value: String,
    pub optional: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillDetails {
    pub id: String,
    pub qualified_id: String,
    pub package_id: String,
    pub trust_tier: String,
    pub version: Option<String>,
    pub source: Option<String>,
    pub aliases: Vec<String>,
    pub uri: String,
    pub skill_type: SkillType,
    pub nature: String,
    pub genus: Option<String>,
    pub differentia: Option<String>,
    pub intents: Vec<String>,
    pub requirements: Vec<RequirementInfo>,
    pub depends_on: Vec<String>,
    pub extends: Vec<String>,
    pub contradicts: Vec<String>,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
    pub handles_failure: Vec<String>,
    pub generated_by: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PayloadInfo {
    pub skill_id: String,
    pub available: bool,
    pub executor: Option<String>,
    pub code: Option<String>,
    pub timeout: Option<i64>,
    pub safety_notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct KnowledgeNodeInfo {
    pub uri: String,
    pub label: Option<String>,
    pub kind: String,
    pub dimension: Option<String>,
    pub directive_content: String,
    pub rationale: Option<String>,
    pub applies_to_context: Option<String>,
    pub severity_level: Option<String>,
    pub source_skill_id: String,
    pub source_qualified_id: Option<String>,
    pub inherited: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillContextResult {
    pub skill: SkillDetails,
    pub payload: PayloadInfo,
    pub knowledge_nodes: Vec<KnowledgeNodeInfo>,
    pub include_inherited_knowledge: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlanStep {
    pub skill_id: String,
    pub purpose: String,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExecutionPlanEvaluation {
    pub intent: Option<String>,
    pub requested_skill: Option<String>,
    pub matching_skills: Vec<String>,
    pub recommended_skill: Option<String>,
    pub applicable: bool,
    pub current_states: Vec<String>,
    pub required_states: Vec<String>,
    pub missing_states: Vec<String>,
    pub dependency_warnings: Vec<String>,
    pub conflict_warnings: Vec<String>,
    pub plan_steps: Vec<PlanStep>,
    pub reasoning_summary: String,
}

#[derive(Debug, Clone)]
pub struct SearchSkillsParams {
    pub intent: Option<String>,
    pub requires_state: Option<String>,
    pub yields_state: Option<String>,
    pub skill_type: Option<SkillType>,
    pub limit: usize,
}

#[derive(Debug, Clone)]
pub struct EvaluateExecutionPlanParams {
    pub intent: Option<String>,
    pub skill_id: Option<String>,
    pub current_states: Vec<String>,
    pub max_depth: usize,
}

#[derive(Debug, Clone)]
pub struct EpistemicQueryParams {
    pub skill_id: Option<String>,
    pub kind: Option<String>,
    pub dimension: Option<String>,
    pub severity_level: Option<String>,
    pub applies_to_context: Option<String>,
    pub include_inherited: bool,
    pub limit: usize,
}

#[derive(Clone)]
pub struct Catalog {
    store: Store,
    base_uri: String,
    skill_index: Vec<SkillRecord>,
}

#[derive(Debug, Clone)]
struct SkillRecord {
    id: String,
    qualified_id: String,
    package_id: String,
    trust_tier: String,
    version: Option<String>,
    source: Option<String>,
    aliases: Vec<String>,
    uri: String,
}

#[derive(Debug, Clone, Deserialize)]
struct RegistryLockFile {
    packages: HashMap<String, RegistryPackageState>,
}

#[derive(Debug, Clone, Deserialize)]
struct RegistryPackageState {
    package_id: String,
    version: String,
    trust_tier: String,
    source: Option<String>,
    skills: Vec<RegistrySkillState>,
}

#[derive(Debug, Clone, Deserialize)]
struct RegistrySkillState {
    #[allow(dead_code)]
    skill_id: String,
    module_path: String,
    aliases: Vec<String>,
}

#[derive(Debug, Clone)]
struct PlanCandidate {
    target_skill: String,
    unresolved_states: BTreeSet<String>,
    steps: Vec<PlanStep>,
}

#[derive(Debug, Clone)]
struct PlanningFrame {
    skill_id: String,
    details: SkillDetails,
    simulated_states: BTreeSet<String>,
    unresolved: BTreeSet<String>,
    steps: Vec<PlanStep>,
    added_skills: HashSet<String>,
    remaining_required: Vec<String>,
    pending_requirement: Option<PendingRequirement>,
    depth: usize,
}

#[derive(Debug, Clone)]
struct PendingRequirement {
    required_state: String,
    candidate_ids: Vec<String>,
    next_candidate_index: usize,
    best_subplan: Option<PlanCandidate>,
}

impl Catalog {
    pub fn load(ontology_root: &Path) -> Result<Self, CatalogError> {
        if !ontology_root.exists() {
            return Err(CatalogError::MissingOntologyRoot(
                ontology_root.to_path_buf(),
            ));
        }

        let store = Store::new().map_err(|err| CatalogError::Oxigraph(err.to_string()))?;
        let mut loaded_any = false;
        let registry_lookup = load_registry_lookup(ontology_root);
        let mut skill_index = Vec::new();
        let base_uri =
            env::var("ONTOSKILLS_BASE_URI").unwrap_or_else(|_| DEFAULT_BASE_URI.to_string());
        let enabled_manifest = ontology_root.join("system").join("index.enabled.ttl");
        let default_manifest = ontology_root.join("index.ttl");

        if enabled_manifest.exists() {
            let mut visited = HashSet::new();
            load_manifest_tree(
                &store,
                &enabled_manifest,
                &mut visited,
                ontology_root,
                &registry_lookup,
                &mut skill_index,
                &base_uri,
            )?;
            loaded_any = !visited.is_empty();
        } else if default_manifest.exists() {
            let mut visited = HashSet::new();
            load_manifest_tree(
                &store,
                &default_manifest,
                &mut visited,
                ontology_root,
                &registry_lookup,
                &mut skill_index,
                &base_uri,
            )?;
            loaded_any = !visited.is_empty();
        } else {
            for entry in WalkDir::new(ontology_root) {
                let entry = entry?;
                if !entry.file_type().is_file() {
                    continue;
                }

                let path = entry.path();
                if path.extension().and_then(|ext| ext.to_str()) != Some("ttl") {
                    continue;
                }

                load_turtle_file(&store, path)?;
                collect_skill_records_from_file(path, ontology_root, &registry_lookup, &mut skill_index, &base_uri)?;
                loaded_any = true;
            }
        }

        if !loaded_any {
            return Err(CatalogError::MissingOntologyRoot(
                ontology_root.to_path_buf(),
            ));
        }

        skill_index.sort_by(|left, right| left.qualified_id.cmp(&right.qualified_id));

        Ok(Self {
            store,
            base_uri,
            skill_index,
        })
    }

    pub fn search_skills(
        &self,
        mut params: SearchSkillsParams,
    ) -> Result<Vec<SkillSearchResult>, CatalogError> {
        params.limit = clamp_limit(params.limit);

        let mut results = Vec::new();
        for skill in self.list_skills()? {
            if let Some(filter_type) = &params.skill_type {
                if &skill.skill_type != filter_type {
                    continue;
                }
            }

            let mut matched_by = Vec::new();

            if let Some(intent) = params.intent.as_deref() {
                if skill
                    .intents
                    .iter()
                    .any(|candidate| eq_ignore_case(candidate, intent))
                {
                    matched_by.push(format!("intent:{intent}"));
                } else {
                    continue;
                }
            }

            if let Some(state) = params.requires_state.as_deref() {
                let expanded = self.expand_state_value(state)?;
                let compact = self.compact_uri(&expanded);
                if skill.requires_state.iter().any(|value| value == &compact) {
                    matched_by.push(format!("requires_state:{compact}"));
                } else {
                    continue;
                }
            }

            if let Some(state) = params.yields_state.as_deref() {
                let expanded = self.expand_state_value(state)?;
                let compact = self.compact_uri(&expanded);
                if skill.yields_state.iter().any(|value| value == &compact) {
                    matched_by.push(format!("yields_state:{compact}"));
                } else {
                    continue;
                }
            }

            if matched_by.is_empty() {
                matched_by.push("all".to_string());
            }

            results.push(SkillSearchResult {
                id: skill.id,
                qualified_id: skill.qualified_id,
                package_id: skill.package_id,
                trust_tier: skill.trust_tier,
                version: skill.version,
                source: skill.source,
                skill_type: skill.skill_type,
                nature: skill.nature,
                intents: skill.intents,
                requires_state: skill.requires_state,
                yields_state: skill.yields_state,
                matched_by,
            });

            if results.len() >= params.limit {
                break;
            }
        }

        Ok(results)
    }

    pub fn get_skill_context(
        &self,
        skill_id: &str,
        include_inherited_knowledge: bool,
    ) -> Result<SkillContextResult, CatalogError> {
        let skill = self.get_skill(skill_id)?;
        let payload = self.get_skill_payload(skill_id)?;
        let knowledge_nodes = self.get_knowledge_nodes(skill_id, include_inherited_knowledge)?;

        Ok(SkillContextResult {
            skill,
            payload,
            knowledge_nodes,
            include_inherited_knowledge,
        })
    }

    pub fn evaluate_execution_plan(
        &self,
        params: EvaluateExecutionPlanParams,
    ) -> Result<ExecutionPlanEvaluation, CatalogError> {
        let max_depth = clamp_max_depth(params.max_depth);
        let current_states = normalize_state_inputs(&params.current_states, self)?;

        let (matching_skills, recommended_skill, reasoning_prefix) =
            match (params.intent.as_deref(), params.skill_id.as_deref()) {
                (Some(intent), None) => {
                    let matching = self.find_skills_by_intent(intent)?;
                    let ids: Vec<String> = matching.into_iter().map(|skill| skill.id).collect();
                    if ids.is_empty() {
                        return Ok(ExecutionPlanEvaluation {
                            intent: Some(intent.to_string()),
                            requested_skill: None,
                            matching_skills: vec![],
                            recommended_skill: None,
                            applicable: false,
                            current_states,
                            required_states: vec![],
                            missing_states: vec![],
                            dependency_warnings: vec![],
                            conflict_warnings: vec![],
                            plan_steps: vec![],
                            reasoning_summary: format!("No skills resolve intent '{intent}'."),
                        });
                    }
                    let count = ids.len();
                    (
                        ids,
                        None,
                        format!("Evaluated {count} skills for intent '{intent}'."),
                    )
                }
                (None, Some(skill_id)) => {
                    validate_skill_id(skill_id)?;
                    let _ = self.find_skill_uri(skill_id)?;
                    (
                        vec![skill_id.to_string()],
                        Some(skill_id.to_string()),
                        format!("Evaluated requested skill '{skill_id}'."),
                    )
                }
                (Some(_), Some(_)) => {
                    return Err(CatalogError::InvalidInput(
                        "Provide either intent or skill_id, not both".to_string(),
                    ));
                }
                (None, None) => {
                    return Err(CatalogError::InvalidInput(
                        "Missing target: provide intent or skill_id".to_string(),
                    ));
                }
            };

        let current_state_set: BTreeSet<String> = current_states.iter().cloned().collect();
        let mut candidates = Vec::new();
        for skill_id in &matching_skills {
            candidates.push(self.build_plan_for_skill_iterative(
                skill_id,
                &current_state_set,
                max_depth,
            )?);
        }

        candidates.sort_by(|left, right| {
            left.unresolved_states
                .len()
                .cmp(&right.unresolved_states.len())
                .then(left.steps.len().cmp(&right.steps.len()))
                .then(left.target_skill.cmp(&right.target_skill))
        });

        let best = candidates.into_iter().next().ok_or_else(|| {
            CatalogError::InvalidInput("No candidate plan could be built".to_string())
        })?;

        let target_skill = recommended_skill.unwrap_or_else(|| best.target_skill.clone());
        let target_context = self.get_skill_context(&target_skill, true)?;
        let required_states: Vec<String> = sorted_vec(target_context.skill.requires_state.clone());
        let dependency_warnings = if target_context.skill.depends_on.is_empty() {
            vec![]
        } else {
            vec![format!(
                "Skill '{}' declares dependencies on: {}",
                target_skill,
                target_context.skill.depends_on.join(", ")
            )]
        };

        let conflict_warnings = target_context
            .skill
            .contradicts
            .iter()
            .map(|conflict| format!("Skill '{}' contradicts '{conflict}'", target_skill))
            .collect();

        let unresolved: Vec<String> = best.unresolved_states.into_iter().collect();
        let applicable = unresolved.is_empty();
        let reasoning_summary = if applicable {
            format!(
                "{reasoning_prefix} Recommended '{target_skill}' because all required states can be satisfied within depth {max_depth}."
            )
        } else {
            format!(
                "{reasoning_prefix} Recommended '{target_skill}' but these states remain unresolved within depth {max_depth}: {}.",
                unresolved.join(", ")
            )
        };

        Ok(ExecutionPlanEvaluation {
            intent: params.intent,
            requested_skill: params.skill_id,
            matching_skills,
            recommended_skill: Some(target_skill),
            applicable,
            current_states,
            required_states,
            missing_states: unresolved,
            dependency_warnings,
            conflict_warnings,
            plan_steps: best.steps,
            reasoning_summary,
        })
    }

    pub fn query_epistemic_rules(
        &self,
        mut params: EpistemicQueryParams,
    ) -> Result<Vec<KnowledgeNodeInfo>, CatalogError> {
        params.limit = clamp_limit(params.limit);

        let mut nodes = if let Some(skill_id) = params.skill_id.as_deref() {
            self.get_knowledge_nodes(skill_id, params.include_inherited)?
        } else {
            let mut aggregated = BTreeMap::new();
            for skill in self.list_skills()? {
                for node in self.get_knowledge_nodes(&skill.id, false)? {
                    aggregated
                        .entry(format!("{}::{}", node.source_skill_id, node.uri))
                        .or_insert(node);
                }
            }
            aggregated.into_values().collect()
        };

        if let Some(kind) = params.kind.as_deref() {
            let normalized = normalize_identifier(kind);
            nodes.retain(|node| node.kind == normalized);
        }

        if let Some(dimension) = params.dimension.as_deref() {
            let normalized = normalize_identifier(dimension);
            nodes.retain(|node| node.dimension.as_deref() == Some(normalized.as_str()));
        }

        if let Some(severity) = params.severity_level.as_deref() {
            let normalized = severity.trim().to_ascii_uppercase();
            nodes.retain(|node| node.severity_level.as_deref() == Some(normalized.as_str()));
        }

        if let Some(context) = params.applies_to_context.as_deref() {
            let normalized = context.to_ascii_lowercase();
            nodes.retain(|node| {
                node.applies_to_context
                    .as_deref()
                    .map(|value| value.to_ascii_lowercase().contains(&normalized))
                    .unwrap_or(false)
            });
        }

        nodes.sort_by(|left, right| {
            left.kind
                .cmp(&right.kind)
                .then(left.dimension.cmp(&right.dimension))
                .then(left.source_skill_id.cmp(&right.source_skill_id))
                .then(left.uri.cmp(&right.uri))
        });
        nodes.truncate(params.limit);

        Ok(nodes)
    }

    pub fn list_skills(&self) -> Result<Vec<SkillSummary>, CatalogError> {
        let mut skills = Vec::new();
        for record in &self.skill_index {
            let details = self.get_skill(&record.qualified_id)?;
            skills.push(SkillSummary {
                id: details.id,
                qualified_id: details.qualified_id,
                package_id: details.package_id,
                trust_tier: details.trust_tier,
                version: details.version,
                source: details.source,
                skill_type: details.skill_type,
                nature: details.nature,
                intents: details.intents,
                requires_state: details.requires_state,
                yields_state: details.yields_state,
            });
        }

        Ok(skills)
    }

    pub fn find_skills_by_intent(&self, intent: &str) -> Result<Vec<SkillSummary>, CatalogError> {
        let mut skills = Vec::new();
        for record in &self.skill_index {
            let details = self.get_skill(&record.qualified_id)?;
            if !details
                .intents
                .iter()
                .any(|candidate| eq_ignore_case(candidate, intent))
            {
                continue;
            }
            skills.push(SkillSummary {
                id: details.id,
                qualified_id: details.qualified_id,
                package_id: details.package_id,
                trust_tier: details.trust_tier,
                version: details.version,
                source: details.source,
                skill_type: details.skill_type,
                nature: details.nature,
                intents: details.intents,
                requires_state: details.requires_state,
                yields_state: details.yields_state,
            });
        }
        skills.sort_by(|left, right| left.qualified_id.cmp(&right.qualified_id));
        Ok(skills)
    }

    pub fn get_skill(&self, skill_id: &str) -> Result<SkillDetails, CatalogError> {
        validate_skill_id(skill_id)?;
        let record = self.resolve_skill_reference(skill_id)?;
        let skill_uri = record.uri.clone();

        let type_query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            SELECT ?type WHERE {{
                <{skill_uri}> a ?type .
                FILTER (?type IN (oc:ExecutableSkill, oc:DeclarativeSkill))
            }}
        "#
        );
        let skill_type = self
            .select_rows(&type_query)?
            .into_iter()
            .find_map(|row| row.optional_iri("type"))
            .map(|uri| self.skill_type_from_uri(&uri))
            .unwrap_or(SkillType::Unknown);

        let scalar_query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT ?nature ?genus ?differentia ?generatedBy
            WHERE {{
                <{skill_uri}> dcterms:identifier {skill_id_literal} ;
                              oc:nature ?nature .
                OPTIONAL {{ <{skill_uri}> skos:broader ?genus }}
                OPTIONAL {{ <{skill_uri}> oc:differentia ?differentia }}
                OPTIONAL {{ <{skill_uri}> oc:generatedBy ?generatedBy }}
            }}
            LIMIT 1
        "#,
            skill_id_literal = sparql_string(&record.id)
        );
        let scalar = self
            .select_rows(&scalar_query)?
            .into_iter()
            .next()
            .ok_or_else(|| CatalogError::SkillNotFound(skill_id.to_string()))?;

        Ok(SkillDetails {
            id: record.id.clone(),
            qualified_id: record.qualified_id.clone(),
            package_id: record.package_id.clone(),
            trust_tier: record.trust_tier.clone(),
            version: record.version.clone(),
            source: record.source.clone(),
            aliases: record.aliases.clone(),
            uri: skill_uri.clone(),
            skill_type,
            nature: scalar.required_literal("nature")?,
            genus: scalar.optional_literal("genus"),
            differentia: scalar.optional_literal("differentia"),
            intents: self.list_literal_values(&skill_uri, "oc:resolvesIntent")?,
            requirements: self.get_requirements_for_uri(&skill_uri)?,
            depends_on: self.get_related_skill_ids(&skill_uri, "oc:dependsOn")?,
            extends: self.get_related_skill_ids(&skill_uri, "oc:extends")?,
            contradicts: self.get_related_skill_ids(&skill_uri, "oc:contradicts")?,
            requires_state: self.get_related_state_values(&skill_uri, "oc:requiresState")?,
            yields_state: self.get_related_state_values(&skill_uri, "oc:yieldsState")?,
            handles_failure: self.get_related_state_values(&skill_uri, "oc:handlesFailure")?,
            generated_by: scalar.optional_literal("generatedBy"),
        })
    }

    pub fn get_skill_payload(&self, skill_id: &str) -> Result<PayloadInfo, CatalogError> {
        validate_skill_id(skill_id)?;
        let record = self.resolve_skill_reference(skill_id)?;
        let skill_uri = record.uri.clone();
        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            SELECT ?executor ?code ?timeout
            WHERE {{
                <{skill_uri}> oc:hasPayload ?payload .
                ?payload oc:executor ?executor ;
                         oc:code ?code .
                OPTIONAL {{ ?payload oc:timeout ?timeout }}
            }}
            LIMIT 1
        "#
        );

        let row = self.select_rows(&query)?.into_iter().next();
        if let Some(row) = row {
            Ok(PayloadInfo {
                skill_id: record.qualified_id.clone(),
                available: true,
                executor: row.optional_literal("executor"),
                code: row.optional_literal("code"),
                timeout: row.optional_i64("timeout"),
                safety_notes: vec![
                    "Payload execution is delegated to the calling agent.".to_string(),
                    "The MCP server does not execute code.".to_string(),
                ],
            })
        } else {
            Ok(PayloadInfo {
                skill_id: record.qualified_id.clone(),
                available: false,
                executor: None,
                code: None,
                timeout: None,
                safety_notes: vec!["Skill has no execution payload.".to_string()],
            })
        }
    }

    pub fn find_skills_yielding_state(
        &self,
        state: &str,
    ) -> Result<Vec<SkillSummary>, CatalogError> {
        let state_uri = self.expand_state_value(state)?;
        self.find_skills_by_state_relation("oc:yieldsState", &state_uri)
    }

    fn get_knowledge_nodes(
        &self,
        skill_id: &str,
        include_inherited: bool,
    ) -> Result<Vec<KnowledgeNodeInfo>, CatalogError> {
        validate_skill_id(skill_id)?;
        let record = self.resolve_skill_reference(skill_id)?;
        let skill_uri = record.uri.clone();
        let requested_skill_id = record.id.clone();
        let source_binding = if include_inherited {
            format!(
                r#"
                {{
                    BIND(<{skill_uri}> AS ?sourceSkill)
                    ?sourceSkill dcterms:identifier ?sourceSkillId ;
                                 oc:impartsKnowledge ?node .
                }}
                UNION
                {{
                    <{skill_uri}> oc:extends+ ?sourceSkill .
                    ?sourceSkill dcterms:identifier ?sourceSkillId ;
                                 oc:impartsKnowledge ?node .
                }}
            "#
            )
        } else {
            format!(
                r#"
                BIND(<{skill_uri}> AS ?sourceSkill)
                ?sourceSkill dcterms:identifier ?sourceSkillId ;
                             oc:impartsKnowledge ?node .
            "#
            )
        };

        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?sourceSkillId ?node ?nodeType ?nodeLabel ?directiveContent ?rationale ?appliesToContext ?severityLevel ?dimension
            WHERE {{
                {source_binding}
                ?node a ?nodeType ;
                      oc:directiveContent ?directiveContent .
                FILTER (?nodeType != oc:KnowledgeNode)
                OPTIONAL {{ ?node rdfs:label ?nodeLabel }}
                OPTIONAL {{ ?node oc:hasRationale ?rationale }}
                OPTIONAL {{ ?node oc:appliesToContext ?appliesToContext }}
                OPTIONAL {{ ?node oc:severityLevel ?severityLevel }}
                OPTIONAL {{
                    ?nodeType rdfs:subClassOf* ?dimension .
                    FILTER (?dimension IN ({dimensions}))
                }}
            }}
            ORDER BY ?sourceSkillId ?node
        "#,
            source_binding = source_binding,
            dimensions = KNOWLEDGE_DIMENSIONS
                .iter()
                .map(|dimension| format!("<{dimension}>"))
                .collect::<Vec<_>>()
                .join(", ")
        );

        let mut by_uri: BTreeMap<String, KnowledgeNodeInfo> = BTreeMap::new();
        for row in self.select_rows(&query)? {
            let uri = row.required_iri("node")?;
            let source_skill_id = row.required_literal("sourceSkillId")?;
            let inherited = source_skill_id != requested_skill_id;
            let candidate = KnowledgeNodeInfo {
                uri: uri.clone(),
                label: row.optional_literal("nodeLabel"),
                kind: row
                    .optional_iri("nodeType")
                    .map(|value| compact_fragment(&value))
                    .unwrap_or_else(|| "knowledge_node".to_string()),
                dimension: row
                    .optional_iri("dimension")
                    .map(|value| compact_fragment(&value)),
                directive_content: row.required_literal("directiveContent")?,
                rationale: row.optional_literal("rationale"),
                applies_to_context: row.optional_literal("appliesToContext"),
                severity_level: row
                    .optional_literal("severityLevel")
                    .map(|value| value.to_ascii_uppercase()),
                source_qualified_id: self.qualified_id_for(&source_skill_id),
                source_skill_id,
                inherited,
            };

            match by_uri.get(&uri) {
                Some(existing) if !existing.inherited && candidate.inherited => {}
                _ => {
                    by_uri.insert(uri, candidate);
                }
            }
        }

        Ok(by_uri.into_values().collect())
    }

    fn build_plan_for_skill_iterative(
        &self,
        skill_id: &str,
        current_states: &BTreeSet<String>,
        max_depth: usize,
    ) -> Result<PlanCandidate, CatalogError> {
        let details = self.get_skill(skill_id)?;
        let mut stack = vec![PlanningFrame::new(details, current_states.clone(), 0)];

        loop {
            let action = {
                let frame = stack.last_mut().ok_or_else(|| {
                    CatalogError::InvalidInput("Planner stack is empty".to_string())
                })?;

                if frame.depth >= max_depth {
                    mark_frame_depth_limited(frame);
                    PlannerAction::Finalize
                } else if let Some(pending) = frame.pending_requirement.as_mut() {
                    if pending.next_candidate_index < pending.candidate_ids.len() {
                        let candidate_id =
                            pending.candidate_ids[pending.next_candidate_index].clone();
                        pending.next_candidate_index += 1;
                        PlannerAction::Push {
                            skill_id: candidate_id,
                            simulated_states: frame.simulated_states.clone(),
                            depth: frame.depth + 1,
                        }
                    } else {
                        apply_best_subplan(frame);
                        PlannerAction::Continue
                    }
                } else if let Some(required_state) = frame.remaining_required.pop() {
                    if frame.simulated_states.contains(&required_state) {
                        PlannerAction::Continue
                    } else {
                        let yielding = self.find_skills_yielding_state(&required_state)?;
                        let candidate_ids: Vec<String> = yielding
                            .into_iter()
                            .filter(|skill| skill.id != frame.skill_id)
                            .map(|skill| skill.id)
                            .collect();

                        if candidate_ids.is_empty() {
                            frame.unresolved.insert(required_state);
                            PlannerAction::Continue
                        } else {
                            frame.pending_requirement = Some(PendingRequirement {
                                required_state,
                                candidate_ids,
                                next_candidate_index: 0,
                                best_subplan: None,
                            });
                            PlannerAction::Continue
                        }
                    }
                } else {
                    PlannerAction::Finalize
                }
            };

            match action {
                PlannerAction::Continue => continue,
                PlannerAction::Push {
                    skill_id,
                    simulated_states,
                    depth,
                } => {
                    if stack.iter().any(|frame| frame.skill_id == skill_id) {
                        continue;
                    }
                    let details = self.get_skill(&skill_id)?;
                    stack.push(PlanningFrame::new(details, simulated_states, depth));
                }
                PlannerAction::Finalize => {
                    let frame = stack.pop().ok_or_else(|| {
                        CatalogError::InvalidInput("Planner stack underflow".to_string())
                    })?;
                    let candidate = finalize_frame(frame);

                    if let Some(parent) = stack.last_mut() {
                        if let Some(pending) = parent.pending_requirement.as_mut() {
                            if is_better_candidate(&candidate, pending.best_subplan.as_ref()) {
                                pending.best_subplan = Some(candidate);
                            }
                        }
                    } else {
                        return Ok(candidate);
                    }
                }
            }
        }
    }

    fn find_skills_by_state_relation(
        &self,
        relation: &str,
        state_uri: &str,
    ) -> Result<Vec<SkillSummary>, CatalogError> {
        let mut results = Vec::new();
        for record in &self.skill_index {
            let details = self.get_skill(&record.qualified_id)?;
            let matches = match relation {
                "oc:yieldsState" => details.yields_state.iter().any(|value| value == state_uri || value == &self.compact_uri(state_uri)),
                "oc:requiresState" => details.requires_state.iter().any(|value| value == state_uri || value == &self.compact_uri(state_uri)),
                _ => false,
            };
            if !matches {
                continue;
            }
            results.push(SkillSummary {
                id: details.id,
                qualified_id: details.qualified_id,
                package_id: details.package_id,
                trust_tier: details.trust_tier,
                version: details.version,
                source: details.source,
                skill_type: details.skill_type,
                nature: details.nature,
                intents: details.intents,
                requires_state: details.requires_state,
                yields_state: details.yields_state,
            });
        }
        results.sort_by(|left, right| left.qualified_id.cmp(&right.qualified_id));
        Ok(results)
    }

    fn get_requirements_for_uri(
        &self,
        skill_uri: &str,
    ) -> Result<Vec<RequirementInfo>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            SELECT ?req ?type ?value ?optional
            WHERE {{
                <{skill_uri}> oc:hasRequirement ?req .
                ?req a ?type ;
                     oc:requirementValue ?value ;
                     oc:isOptional ?optional .
            }}
            ORDER BY ?req
        "#
        );

        let mut requirements = Vec::new();
        for row in self.select_rows(&query)? {
            let req_type_uri = row.required_iri("type")?;
            requirements.push(RequirementInfo {
                requirement_type: compact_requirement_type(&req_type_uri),
                value: row.required_literal("value")?,
                optional: row.optional_bool("optional").unwrap_or(false),
            });
        }
        Ok(requirements)
    }

    fn get_related_skill_ids(
        &self,
        skill_uri: &str,
        relation: &str,
    ) -> Result<Vec<String>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?target ?targetId
            WHERE {{
                <{skill_uri}> {relation} ?target .
                OPTIONAL {{ ?target dcterms:identifier ?targetId }}
            }}
            ORDER BY ?target
        "#
        );

        let mut values = Vec::new();
        for row in self.select_rows(&query)? {
            if let Some(id) = row.optional_literal("targetId") {
                values.push(id);
            } else if let Some(uri) = row.optional_iri("target") {
                values.push(self.compact_uri(&uri));
            }
        }
        Ok(values)
    }

    fn get_related_state_values(
        &self,
        skill_uri: &str,
        relation: &str,
    ) -> Result<Vec<String>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            SELECT ?target
            WHERE {{
                <{skill_uri}> {relation} ?target .
            }}
            ORDER BY ?target
        "#
        );

        let mut values = Vec::new();
        for row in self.select_rows(&query)? {
            values.push(self.compact_uri(&row.required_iri("target")?));
        }
        Ok(values)
    }

    fn list_literal_values(
        &self,
        skill_uri: &str,
        predicate: &str,
    ) -> Result<Vec<String>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <https://ontoskills.sh/ontology#>
            SELECT ?value
            WHERE {{
                <{skill_uri}> {predicate} ?value .
            }}
            ORDER BY ?value
        "#
        );

        let mut values = Vec::new();
        for row in self.select_rows(&query)? {
            values.push(row.required_literal("value")?);
        }
        Ok(values)
    }

    fn find_skill_uri(&self, skill_id: &str) -> Result<String, CatalogError> {
        Ok(self.resolve_skill_reference(skill_id)?.uri.clone())
    }

    fn resolve_skill_reference(&self, skill_ref: &str) -> Result<&SkillRecord, CatalogError> {
        validate_skill_id(skill_ref)?;

        if let Some(record) = self
            .skill_index
            .iter()
            .find(|record| record.qualified_id.eq_ignore_ascii_case(skill_ref))
        {
            return Ok(record);
        }

        if let Some((package_id, short_id)) = skill_ref.split_once('/') {
            if let Some(record) = self.skill_index.iter().find(|record| {
                record.package_id.eq_ignore_ascii_case(package_id)
                    && record.id.eq_ignore_ascii_case(short_id)
            }) {
                return Ok(record);
            }
        }

        let mut candidates: Vec<&SkillRecord> = self
            .skill_index
            .iter()
            .filter(|record| {
                record.id.eq_ignore_ascii_case(skill_ref)
                    || record
                        .aliases
                        .iter()
                        .any(|alias| alias.eq_ignore_ascii_case(skill_ref))
            })
            .collect();

        candidates.sort_by(|left, right| {
            trust_rank(&left.trust_tier)
                .cmp(&trust_rank(&right.trust_tier))
                .then(left.package_id.cmp(&right.package_id))
                .then(left.id.cmp(&right.id))
        });

        candidates
            .into_iter()
            .next()
            .ok_or_else(|| CatalogError::SkillNotFound(skill_ref.to_string()))
    }

    fn qualified_id_for(&self, skill_id: &str) -> Option<String> {
        self.skill_index
            .iter()
            .find(|record| record.id == skill_id)
            .map(|record| record.qualified_id.clone())
    }

    fn select_rows(&self, query: &str) -> Result<Vec<QueryRow>, CatalogError> {
        let prepared = SparqlEvaluator::new()
            .parse_query(query)
            .map_err(|err| CatalogError::Oxigraph(err.to_string()))?;
        let results = prepared
            .on_store(&self.store)
            .execute()
            .map_err(|err| CatalogError::Oxigraph(err.to_string()))?;

        match results {
            QueryResults::Solutions(solutions) => {
                let mut rows = Vec::new();
                for solution in solutions {
                    let solution =
                        solution.map_err(|err| CatalogError::Oxigraph(err.to_string()))?;
                    let mut map = HashMap::new();
                    for (variable, term) in solution.iter() {
                        map.insert(variable.as_str().to_string(), term.to_owned());
                    }
                    rows.push(QueryRow { values: map });
                }
                Ok(rows)
            }
            _ => Err(CatalogError::Oxigraph(
                "Expected SELECT query results".to_string(),
            )),
        }
    }

    fn skill_type_from_uri(&self, uri: &str) -> SkillType {
        match uri {
            value if value.ends_with("ExecutableSkill") => SkillType::Executable,
            value if value.ends_with("DeclarativeSkill") => SkillType::Declarative,
            _ => SkillType::Unknown,
        }
    }

    fn compact_uri(&self, uri: &str) -> String {
        if uri.starts_with(&self.base_uri) {
            format!("oc:{}", &uri[self.base_uri.len()..])
        } else {
            uri.to_string()
        }
    }

    fn expand_state_value(&self, value: &str) -> Result<String, CatalogError> {
        if value.starts_with("oc:") {
            Ok(format!(
                "{}{}",
                self.base_uri,
                value.trim_start_matches("oc:")
            ))
        } else if value.starts_with("http://") || value.starts_with("https://") {
            Ok(value.to_string())
        } else {
            Err(CatalogError::InvalidState(value.to_string()))
        }
    }
}

fn load_turtle_file(store: &Store, path: &Path) -> Result<(), CatalogError> {
    let reader = BufReader::new(File::open(path)?);
    store
        .load_from_reader(RdfFormat::Turtle, reader)
        .map_err(|err| CatalogError::Oxigraph(format!("{} ({})", err, path.display())))
}

fn load_manifest_tree(
    store: &Store,
    manifest_path: &Path,
    visited: &mut HashSet<PathBuf>,
    ontology_root: &Path,
    registry_lookup: &HashMap<String, RegistryLookupEntry>,
    skill_index: &mut Vec<SkillRecord>,
    base_uri: &str,
) -> Result<(), CatalogError> {
    let canonical = manifest_path.canonicalize()?;
    if !visited.insert(canonical.clone()) {
        return Ok(());
    }

    load_turtle_file(store, &canonical)?;
    collect_skill_records_from_file(&canonical, ontology_root, registry_lookup, skill_index, base_uri)?;

    let content = std::fs::read_to_string(&canonical)?;
    for imported in parse_import_paths(&content, ontology_root) {
        if imported.exists() {
            load_manifest_tree(
                store,
                &imported,
                visited,
                ontology_root,
                registry_lookup,
                skill_index,
                base_uri,
            )?;
        }
    }

    Ok(())
}

fn parse_import_paths(content: &str, ontology_root: &Path) -> Vec<PathBuf> {
    let mut imports = Vec::new();

    // Resolve file:// imports
    for segment in content.split("owl:imports <file://").skip(1) {
        if let Some(raw_path) = segment.split('>').next() {
            let normalized = if raw_path.starts_with('/') {
                raw_path.to_string()
            } else {
                format!("/{}", raw_path)
            };
            imports.push(PathBuf::from(normalized));
        }
    }

    // Resolve https:// imports — check if the file exists locally in ontology root
    for segment in content.split("owl:imports <https://").skip(1) {
        if let Some(raw_url) = segment.split('>').next() {
            // Extract filename from URL (e.g. "core.ttl" from "ontoskills.sh/ontology/core.ttl")
            if let Some(filename) = raw_url.rsplit('/').next() {
                let local_path = ontology_root.join(filename);
                if local_path.exists() {
                    imports.push(local_path);
                } else {
                    eprintln!("Warning: https import https://{} not found locally at {:?}", raw_url, local_path);
                }
            }
        }
    }

    imports
}

#[derive(Debug, Clone)]
struct RegistryLookupEntry {
    package_id: String,
    trust_tier: String,
    version: Option<String>,
    source: Option<String>,
    aliases: Vec<String>,
}

fn load_registry_lookup(ontology_root: &Path) -> HashMap<String, RegistryLookupEntry> {
    let path = state_registry_lock_path(ontology_root);
    let Ok(content) = std::fs::read_to_string(path) else {
        return HashMap::new();
    };
    let Ok(lock) = serde_json::from_str::<RegistryLockFile>(&content) else {
        return HashMap::new();
    };

    let mut lookup = HashMap::new();
    for package in lock.packages.into_values() {
        for skill in package.skills {
            let module_path = skill.module_path.clone();
            let key = PathBuf::from(&module_path)
                .canonicalize()
                .unwrap_or_else(|_| PathBuf::from(&module_path))
                .display()
                .to_string();
            lookup.insert(
                key,
                RegistryLookupEntry {
                    package_id: package.package_id.clone(),
                    trust_tier: package.trust_tier.clone(),
                    version: Some(package.version.clone()),
                    source: package.source.clone(),
                    aliases: skill.aliases.clone(),
                },
            );
        }
    }
    lookup
}

fn state_registry_lock_path(ontology_root: &Path) -> PathBuf {
    if let Some(home_root) = ontology_root.parent() {
        let state_path = home_root.join("state").join("registry.lock.json");
        if state_path.exists() {
            return state_path;
        }
    }
    ontology_root.join("system").join("registry.lock.json")
}

fn collect_skill_records_from_file(
    path: &Path,
    ontology_root: &Path,
    registry_lookup: &HashMap<String, RegistryLookupEntry>,
    skill_index: &mut Vec<SkillRecord>,
    base_uri: &str,
) -> Result<(), CatalogError> {
    if path.file_name().and_then(|name| name.to_str()) == Some("core.ttl") {
        return Ok(());
    }

    let canonical = path.canonicalize()?;
    let content = std::fs::read_to_string(&canonical)?;
    let mut last_subject_uri: Option<String> = None;

    for raw_line in content.lines() {
        let line = raw_line.trim();
        if let Some(subject) = line.split_whitespace().next() {
            // Support both prefixed (oc:skill_xxx) and full IRI (<https://...#skill_xxx>)
            if subject.starts_with("oc:skill_") {
                // Use the runtime base_uri instead of DEFAULT_BASE_URI
                last_subject_uri = Some(format!("{}{}", base_uri, subject.trim_start_matches("oc:")));
            } else if subject.starts_with('<') && subject.contains("#skill_") {
                // Full IRI: <https://ontoskills.sh/ontology#skill_xxx>
                last_subject_uri = Some(subject.trim_matches(|c| c == '<' || c == '>').to_string());
            }
        }
        if let Some((_, suffix)) = line.split_once("dcterms:identifier ") {
            if let Some(skill_id) = extract_turtle_literal(suffix) {
                let record = build_skill_record(
                    &skill_id,
                    last_subject_uri.clone().unwrap_or_default(),
                    &canonical,
                    ontology_root,
                    registry_lookup,
                );
                if !skill_index
                    .iter()
                    .any(|existing| existing.qualified_id == record.qualified_id)
                {
                    skill_index.push(record);
                }
            }
        }
    }

    Ok(())
}

fn extract_turtle_literal(value: &str) -> Option<String> {
    let start = value.find('"')?;
    let rest = &value[start + 1..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn build_skill_record(
    skill_id: &str,
    uri: String,
    module_path: &Path,
    ontology_root: &Path,
    registry_lookup: &HashMap<String, RegistryLookupEntry>,
) -> SkillRecord {
    let canonical_key = module_path.display().to_string();
    if let Some(entry) = registry_lookup.get(&canonical_key) {
        return SkillRecord {
            id: skill_id.to_string(),
            qualified_id: format!("{}/{}", entry.package_id, skill_id),
            package_id: entry.package_id.clone(),
            trust_tier: entry.trust_tier.clone(),
            version: entry.version.clone(),
            source: entry.source.clone(),
            aliases: entry.aliases.clone(),
            uri,
        };
    }

    let rel = module_path
        .strip_prefix(ontology_root)
        .ok()
        .and_then(|path| path.components().next().map(|c| c.as_os_str().to_string_lossy().to_string()));
    let trust_tier = match rel.as_deref() {
        Some("vendor") => "verified",
        _ => "local",
    }
    .to_string();
    let package_id = if let Ok(relative) = module_path.strip_prefix(ontology_root.join("vendor")) {
        relative
            .components()
            .next()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .unwrap_or_else(|| "local".to_string())
    } else {
        "local".to_string()
    };

    SkillRecord {
        id: skill_id.to_string(),
        qualified_id: format!("{}/{}", package_id, skill_id),
        package_id,
        trust_tier,
        version: None,
        source: None,
        aliases: vec![],
        uri,
    }
}

enum PlannerAction {
    Continue,
    Push {
        skill_id: String,
        simulated_states: BTreeSet<String>,
        depth: usize,
    },
    Finalize,
}

impl PlanningFrame {
    fn new(details: SkillDetails, simulated_states: BTreeSet<String>, depth: usize) -> Self {
        let mut remaining_required = details.requires_state.clone();
        remaining_required.reverse();
        Self {
            skill_id: details.id.clone(),
            details,
            simulated_states,
            unresolved: BTreeSet::new(),
            steps: Vec::new(),
            added_skills: HashSet::new(),
            remaining_required,
            pending_requirement: None,
            depth,
        }
    }
}

#[derive(Debug, Clone)]
struct QueryRow {
    values: HashMap<String, Term>,
}

impl QueryRow {
    fn required_literal(&self, key: &str) -> Result<String, CatalogError> {
        self.optional_literal(key)
            .ok_or_else(|| CatalogError::Oxigraph(format!("Missing literal binding '{key}'")))
    }

    fn optional_literal(&self, key: &str) -> Option<String> {
        self.values.get(key).and_then(term_to_literal)
    }

    fn required_iri(&self, key: &str) -> Result<String, CatalogError> {
        self.optional_iri(key)
            .ok_or_else(|| CatalogError::Oxigraph(format!("Missing IRI binding '{key}'")))
    }

    fn optional_iri(&self, key: &str) -> Option<String> {
        self.values.get(key).and_then(term_to_iri)
    }

    fn optional_bool(&self, key: &str) -> Option<bool> {
        self.optional_literal(key)
            .and_then(|value| value.parse::<bool>().ok())
    }

    fn optional_i64(&self, key: &str) -> Option<i64> {
        self.optional_literal(key)
            .and_then(|value| value.parse::<i64>().ok())
    }
}

fn finalize_frame(frame: PlanningFrame) -> PlanCandidate {
    let mut steps = frame.steps;
    steps.push(PlanStep {
        skill_id: frame.skill_id.clone(),
        purpose: format!("Execute skill '{}'", frame.skill_id),
        requires_state: frame.details.requires_state.clone(),
        yields_state: frame.details.yields_state.clone(),
    });

    PlanCandidate {
        target_skill: frame.skill_id,
        unresolved_states: frame.unresolved,
        steps,
    }
}

fn mark_frame_depth_limited(frame: &mut PlanningFrame) {
    if let Some(pending) = frame.pending_requirement.take() {
        frame.unresolved.insert(pending.required_state);
    }
    for required_state in frame.remaining_required.clone() {
        if !frame.simulated_states.contains(&required_state) {
            frame.unresolved.insert(required_state);
        }
    }
    frame.remaining_required.clear();
}

fn apply_best_subplan(frame: &mut PlanningFrame) {
    let Some(pending) = frame.pending_requirement.take() else {
        return;
    };

    if let Some(subplan) = pending.best_subplan {
        frame
            .unresolved
            .extend(subplan.unresolved_states.iter().cloned());
        for step in subplan.steps {
            for yielded_state in &step.yields_state {
                frame.simulated_states.insert(yielded_state.clone());
            }
            if frame.added_skills.insert(step.skill_id.clone()) {
                frame.steps.push(step);
            }
        }
        if !frame.simulated_states.contains(&pending.required_state) {
            frame.unresolved.insert(pending.required_state);
        }
    } else {
        frame.unresolved.insert(pending.required_state);
    }
}

fn term_to_literal(term: &Term) -> Option<String> {
    match term {
        Term::Literal(literal) => Some(literal.value().to_string()),
        _ => None,
    }
}

fn term_to_iri(term: &Term) -> Option<String> {
    match term {
        Term::NamedNode(node) => Some(node.as_str().to_string()),
        _ => None,
    }
}

fn compact_requirement_type(uri: &str) -> String {
    uri.rsplit("Requirement").next().unwrap_or(uri).to_string()
}

fn normalize_state_inputs(
    current_states: &[String],
    catalog: &Catalog,
) -> Result<Vec<String>, CatalogError> {
    let mut normalized = BTreeSet::new();
    for state in current_states {
        normalized.insert(catalog.compact_uri(&catalog.expand_state_value(state)?));
    }
    Ok(normalized.into_iter().collect())
}

fn validate_skill_id(skill_id: &str) -> Result<(), CatalogError> {
    if skill_id.is_empty() {
        return Err(CatalogError::InvalidInput(
            "skill_id cannot be empty".to_string(),
        ));
    }
    if skill_id.len() > MAX_SKILL_ID_LEN {
        return Err(CatalogError::InvalidInput(format!(
            "skill_id exceeds maximum length of {MAX_SKILL_ID_LEN}"
        )));
    }
    if !skill_id
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'/' | b'.' | b'_'))
    {
        return Err(CatalogError::InvalidInput(
            "skill_id must match ^[A-Za-z0-9._/-]+$".to_string(),
        ));
    }
    Ok(())
}

fn trust_rank(trust_tier: &str) -> usize {
    match trust_tier {
        "local" => 0,
        "verified" => 1,
        "trusted" => 2,
        "community" => 3,
        _ => 4,
    }
}

fn sorted_vec<I>(iter: I) -> Vec<String>
where
    I: IntoIterator<Item = String>,
{
    let mut values: Vec<String> = iter.into_iter().collect();
    values.sort();
    values
}

fn clamp_limit(limit: usize) -> usize {
    let limit = if limit == 0 { DEFAULT_LIMIT } else { limit };
    limit.clamp(1, MAX_LIMIT)
}

fn clamp_max_depth(max_depth: usize) -> usize {
    if max_depth == 0 {
        DEFAULT_MAX_DEPTH
    } else {
        max_depth.min(DEFAULT_MAX_DEPTH)
    }
}

fn sparql_string(value: &str) -> String {
    let escaped = value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n");
    format!("\"{escaped}\"")
}

fn is_better_candidate(candidate: &PlanCandidate, current_best: Option<&PlanCandidate>) -> bool {
    match current_best {
        None => true,
        Some(best) => candidate
            .unresolved_states
            .len()
            .cmp(&best.unresolved_states.len())
            .then(candidate.steps.len().cmp(&best.steps.len()))
            .then(candidate.target_skill.cmp(&best.target_skill))
            .is_lt(),
    }
}

fn compact_fragment(uri: &str) -> String {
    let fragment = uri.rsplit(['#', '/']).next().unwrap_or(uri).trim();
    normalize_identifier(fragment)
}

fn normalize_identifier(value: &str) -> String {
    let mut normalized = String::new();
    let mut last_was_separator = false;

    for ch in value.chars() {
        if ch.is_ascii_uppercase() {
            if !normalized.is_empty() && !last_was_separator {
                normalized.push('_');
            }
            normalized.push(ch.to_ascii_lowercase());
            last_was_separator = false;
        } else if ch.is_ascii_alphanumeric() {
            normalized.push(ch.to_ascii_lowercase());
            last_was_separator = false;
        } else if !last_was_separator {
            normalized.push('_');
            last_was_separator = true;
        }
    }

    normalized.trim_matches('_').to_string()
}

fn eq_ignore_case(left: &str, right: &str) -> bool {
    left.eq_ignore_ascii_case(right)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn write_test_ontology(root: &Path) {
        let ttl = format!(
            r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

oc:KnowledgeNode a rdfs:Class .
oc:NormativeRule a rdfs:Class ; rdfs:subClassOf oc:KnowledgeNode .
oc:StrategicInsight a rdfs:Class ; rdfs:subClassOf oc:KnowledgeNode .
oc:Standard a rdfs:Class ; rdfs:subClassOf oc:NormativeRule .
oc:Heuristic a rdfs:Class ; rdfs:subClassOf oc:StrategicInsight .

oc:skill_base a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "base-skill" ;
    oc:nature "Base semantic skill" ;
    oc:impartsKnowledge oc:kn_base ;
    oc:yieldsState oc:ToolInstalled .

oc:kn_base a oc:Standard ;
    oc:directiveContent "Always validate the environment first" ;
    oc:hasRationale "Validation prevents late failures" ;
    oc:severityLevel "HIGH" .

oc:skill_install a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "install-tool" ;
    oc:nature "Installs the project toolchain" ;
    skos:broader "Setup" ;
    oc:differentia "Ensures the required CLI is available" ;
    oc:resolvesIntent "prepare_environment" ;
    oc:yieldsState oc:ToolInstalled ;
    oc:generatedBy "test-model" ;
    oc:hasPayload oc:payload_install .

oc:payload_install a oc:ExecutionPayload ;
    oc:executor "shell" ;
    oc:code "tool install" ;
    oc:timeout 30 .

oc:skill_pdf a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "pdf-generator" ;
    oc:nature "Generates a PDF from an input document" ;
    skos:broader "Document transformation" ;
    oc:differentia "Creates a PDF artifact" ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:ToolInstalled ;
    oc:requiresState oc:FileExists ;
    oc:yieldsState oc:DocumentCreated ;
    oc:generatedBy "test-model" ;
    oc:extends oc:skill_base ;
    oc:impartsKnowledge oc:kn_pdf .

oc:kn_pdf a oc:Heuristic ;
    oc:directiveContent "Prefer direct generation when possible" ;
    oc:hasRationale "Fewer steps reduce risk" ;
    oc:appliesToContext "document generation" .
"#,
            base = DEFAULT_BASE_URI
        );

        fs::create_dir_all(root).unwrap();
        fs::write(root.join("index.ttl"), ttl).unwrap();
    }

    fn write_ranked_ontology(root: &Path) {
        let ttl = format!(
            r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_direct a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "direct-pdf" ;
    oc:nature "Direct PDF generation" ;
    oc:resolvesIntent "create_pdf" ;
    oc:yieldsState oc:DocumentCreated .

oc:skill_needs_setup a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "setup-pdf" ;
    oc:nature "PDF generation with setup" ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:ToolInstalled ;
    oc:yieldsState oc:DocumentCreated .

oc:skill_setup a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "install-tool" ;
    oc:nature "Installs the toolchain" ;
    oc:resolvesIntent "prepare_environment" ;
    oc:yieldsState oc:ToolInstalled .
"#,
            base = DEFAULT_BASE_URI
        );

        fs::create_dir_all(root).unwrap();
        fs::write(root.join("index.ttl"), ttl).unwrap();
    }

    fn write_enabled_registry(root: &Path) {
        fs::create_dir_all(root.join("system")).unwrap();
        fs::write(
            root.join("enabled.ttl"),
            format!(
                r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_enabled a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "enabled-skill" ;
    oc:nature "Enabled" .
"#,
                base = DEFAULT_BASE_URI
            ),
        )
        .unwrap();
        fs::write(
            root.join("disabled.ttl"),
            format!(
                r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_disabled a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "disabled-skill" ;
    oc:nature "Disabled" .
"#,
                base = DEFAULT_BASE_URI
            ),
        )
        .unwrap();
        fs::write(
            root.join("system").join("index.enabled.ttl"),
            format!(
                r#"
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<https://ontoskills.sh/ontology> owl:imports <file://{enabled}> .
"#,
                enabled = root.join("enabled.ttl").display()
            ),
        )
        .unwrap();
    }

    fn write_ambiguous_registry(root: &Path) {
        fs::create_dir_all(root.join("system")).unwrap();
        fs::create_dir_all(root.join("vendor").join("marea/office").join("skills")).unwrap();
        fs::create_dir_all(root.join("xlsx")).unwrap();
        fs::write(
            root.join("vendor").join("marea/office").join("skills").join("xlsx.ttl"),
            format!(
                r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx_verified a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Verified spreadsheet" .
"#,
                base = DEFAULT_BASE_URI
            ),
        )
        .unwrap();
        fs::write(
            root.join("xlsx").join("ontoskill.ttl"),
            format!(
                r#"
@prefix oc: <{base}> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx_local a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Local spreadsheet" .
"#,
                base = DEFAULT_BASE_URI
            ),
        )
        .unwrap();
        fs::write(
            root.join("system").join("registry.lock.json"),
            r#"{
  "packages": {
    "marea/office": {
      "package_id": "marea/office",
      "version": "1.0.0",
      "trust_tier": "verified",
      "source": "https://example.invalid/marea/office",
      "skills": [
        {
          "skill_id": "xlsx",
          "module_path": "__MODULE__",
          "aliases": ["excel"]
        }
      ]
    }
  }
}"#
            .replace(
                "__MODULE__",
                &root
                    .join("vendor")
                    .join("marea/office")
                    .join("skills")
                    .join("xlsx.ttl")
                    .display()
                    .to_string(),
            ),
        )
        .unwrap();
        fs::write(
            root.join("system").join("index.enabled.ttl"),
            format!(
                r#"
@prefix owl: <http://www.w3.org/2002/07/owl#> .

<https://ontoskills.sh/ontology> owl:imports <file://{verified}> ;
    owl:imports <file://{local}> .
"#,
                verified = root
                    .join("vendor")
                    .join("marea/office")
                    .join("skills")
                    .join("xlsx.ttl")
                    .display(),
                local = root.join("xlsx").join("ontoskill.ttl").display(),
            ),
        )
        .unwrap();
    }

    #[test]
    fn skill_context_includes_knowledge_nodes() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let context = catalog.get_skill_context("pdf-generator", true).unwrap();

        assert_eq!(context.skill.id, "pdf-generator");
        assert!(!context.payload.available);
        assert_eq!(context.knowledge_nodes.len(), 2);
        assert!(
            context
                .knowledge_nodes
                .iter()
                .any(|node| node.kind == "standard" && node.inherited)
        );
        assert!(
            context
                .knowledge_nodes
                .iter()
                .any(|node| node.kind == "heuristic" && !node.inherited)
        );
    }

    #[test]
    fn search_skills_filters_by_intent() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let results = catalog
            .search_skills(SearchSkillsParams {
                intent: Some("create_pdf".to_string()),
                requires_state: None,
                yields_state: None,
                skill_type: None,
                limit: 10,
            })
            .unwrap();

        assert_eq!(results.len(), 1);
        assert_eq!(results[0].id, "pdf-generator");
    }

    #[test]
    fn query_epistemic_rules_filters_by_kind() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let rules = catalog
            .query_epistemic_rules(EpistemicQueryParams {
                skill_id: Some("pdf-generator".to_string()),
                kind: Some("standard".to_string()),
                dimension: None,
                severity_level: None,
                applies_to_context: None,
                include_inherited: true,
                limit: 10,
            })
            .unwrap();

        assert_eq!(rules.len(), 1);
        assert_eq!(rules[0].kind, "standard");
        assert!(rules[0].inherited);
    }

    #[test]
    fn evaluate_execution_plan_prefers_direct_skill_when_available() {
        let dir = tempdir().unwrap();
        write_ranked_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let evaluation = catalog
            .evaluate_execution_plan(EvaluateExecutionPlanParams {
                intent: Some("create_pdf".to_string()),
                skill_id: None,
                current_states: vec![],
                max_depth: 10,
            })
            .unwrap();

        assert_eq!(evaluation.recommended_skill.as_deref(), Some("direct-pdf"));
        assert!(evaluation.applicable);
        assert_eq!(evaluation.plan_steps.len(), 1);
    }

    #[test]
    fn catalog_prefers_enabled_index_manifest_when_present() {
        let dir = tempdir().unwrap();
        write_enabled_registry(dir.path());

        let catalog = Catalog::load(dir.path()).unwrap();
        let skills = catalog.list_skills().unwrap();

        assert_eq!(skills.len(), 1);
        assert_eq!(skills[0].id, "enabled-skill");
    }

    #[test]
    fn catalog_resolves_short_id_with_local_precedence_and_exact_qualified_id() {
        let dir = tempdir().unwrap();
        write_ambiguous_registry(dir.path());

        let catalog = Catalog::load(dir.path()).unwrap();
        let preferred = catalog.get_skill("xlsx").unwrap();
        let imported = catalog.get_skill("marea/office/xlsx").unwrap();

        assert_eq!(preferred.qualified_id, "local/xlsx");
        assert_eq!(preferred.trust_tier, "local");
        assert_eq!(imported.qualified_id, "marea/office/xlsx");
        assert_eq!(imported.trust_tier, "verified");
    }
}
