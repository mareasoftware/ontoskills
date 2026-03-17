use std::collections::{BTreeSet, HashMap, HashSet};
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
use walkdir::WalkDir;

const DEFAULT_BASE_URI: &str = "http://ontoclaw.marea.software/ontology#";

#[derive(Debug)]
pub enum CatalogError {
    Io(std::io::Error),
    Walk(walkdir::Error),
    Oxigraph(String),
    MissingOntologyRoot(PathBuf),
    SkillNotFound(String),
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
    pub skill_type: SkillType,
    pub nature: String,
    pub intents: Vec<String>,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
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
pub struct ApplicabilityResult {
    pub skill_id: String,
    pub applicable: bool,
    pub current_states: Vec<String>,
    pub required_states: Vec<String>,
    pub missing_states: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlanStep {
    pub skill_id: String,
    pub purpose: String,
    pub requires_state: Vec<String>,
    pub yields_state: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlanResult {
    pub intent: String,
    pub matching_skills: Vec<String>,
    pub recommended_skill: Option<String>,
    pub missing_states: Vec<String>,
    pub plan_steps: Vec<PlanStep>,
    pub reasoning_summary: String,
}

#[derive(Clone)]
pub struct Catalog {
    store: Store,
    base_uri: String,
}

#[derive(Debug, Clone)]
struct PlanCandidate {
    target_skill: String,
    unresolved_states: BTreeSet<String>,
    steps: Vec<PlanStep>,
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

        for entry in WalkDir::new(ontology_root) {
            let entry = entry?;
            if !entry.file_type().is_file() {
                continue;
            }

            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("ttl") {
                continue;
            }

            let reader = BufReader::new(File::open(path)?);
            store
                .load_from_reader(RdfFormat::Turtle, reader)
                .map_err(|err| CatalogError::Oxigraph(format!("{} ({})", err, path.display())))?;
            loaded_any = true;
        }

        if !loaded_any {
            return Err(CatalogError::MissingOntologyRoot(
                ontology_root.to_path_buf(),
            ));
        }

        let base_uri =
            env::var("ONTOCLAW_BASE_URI").unwrap_or_else(|_| DEFAULT_BASE_URI.to_string());

        Ok(Self { store, base_uri })
    }

    pub fn list_skills(&self) -> Result<Vec<SkillSummary>, CatalogError> {
        let query = r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?skill ?id ?nature ?type
            WHERE {
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       oc:nature ?nature .
                OPTIONAL { ?skill a ?type . FILTER (?type IN (oc:ExecutableSkill, oc:DeclarativeSkill)) }
            }
            ORDER BY ?id
        "#;

        let mut skills = Vec::new();
        for row in self.select_rows(query)? {
            let skill_id = row.required_literal("id")?;
            let details = self.get_skill(&skill_id)?;
            skills.push(SkillSummary {
                id: details.id,
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
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT DISTINCT ?id
            WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       oc:resolvesIntent ?intent .
                FILTER(LCASE(STR(?intent)) = LCASE({intent_literal}))
            }}
            ORDER BY ?id
        "#,
            intent_literal = sparql_string(intent)
        );

        let mut results = Vec::new();
        for row in self.select_rows(&query)? {
            let skill_id = row.required_literal("id")?;
            let details = self.get_skill(&skill_id)?;
            results.push(SkillSummary {
                id: details.id,
                skill_type: details.skill_type,
                nature: details.nature,
                intents: details.intents,
                requires_state: details.requires_state,
                yields_state: details.yields_state,
            });
        }

        Ok(results)
    }

    pub fn get_skill(&self, skill_id: &str) -> Result<SkillDetails, CatalogError> {
        let skill_uri = self.find_skill_uri(skill_id)?;
        let type_query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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
            skill_id_literal = sparql_string(skill_id)
        );
        let scalar = self
            .select_rows(&scalar_query)?
            .into_iter()
            .next()
            .ok_or_else(|| CatalogError::SkillNotFound(skill_id.to_string()))?;

        Ok(SkillDetails {
            id: skill_id.to_string(),
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

    pub fn get_skill_requirements(
        &self,
        skill_id: &str,
    ) -> Result<Vec<RequirementInfo>, CatalogError> {
        let skill_uri = self.find_skill_uri(skill_id)?;
        self.get_requirements_for_uri(&skill_uri)
    }

    pub fn get_skill_payload(&self, skill_id: &str) -> Result<PayloadInfo, CatalogError> {
        let skill_uri = self.find_skill_uri(skill_id)?;
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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
                skill_id: skill_id.to_string(),
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
                skill_id: skill_id.to_string(),
                available: false,
                executor: None,
                code: None,
                timeout: None,
                safety_notes: vec!["Skill has no execution payload.".to_string()],
            })
        }
    }

    pub fn check_skill_applicability(
        &self,
        skill_id: &str,
        current_states: &[String],
    ) -> Result<ApplicabilityResult, CatalogError> {
        let details = self.get_skill(skill_id)?;
        let current: BTreeSet<String> = current_states.iter().cloned().collect();
        let required: BTreeSet<String> = details.requires_state.iter().cloned().collect();
        let missing: Vec<String> = required.difference(&current).cloned().collect();

        Ok(ApplicabilityResult {
            skill_id: skill_id.to_string(),
            applicable: missing.is_empty(),
            current_states: sorted_vec(current_states.iter().cloned()),
            required_states: sorted_vec(required.into_iter()),
            missing_states: missing,
        })
    }

    pub fn find_skills_requiring_state(
        &self,
        state: &str,
    ) -> Result<Vec<SkillSummary>, CatalogError> {
        let state_uri = self.expand_state_value(state)?;
        self.find_skills_by_state_relation("oc:requiresState", &state_uri)
    }

    pub fn find_skills_yielding_state(
        &self,
        state: &str,
    ) -> Result<Vec<SkillSummary>, CatalogError> {
        let state_uri = self.expand_state_value(state)?;
        self.find_skills_by_state_relation("oc:yieldsState", &state_uri)
    }

    pub fn plan_from_intent(
        &self,
        intent: &str,
        current_states: &[String],
    ) -> Result<PlanResult, CatalogError> {
        let matching = self.find_skills_by_intent(intent)?;
        let matching_ids: Vec<String> = matching.iter().map(|skill| skill.id.clone()).collect();
        if matching_ids.is_empty() {
            return Ok(PlanResult {
                intent: intent.to_string(),
                matching_skills: vec![],
                recommended_skill: None,
                missing_states: vec![],
                plan_steps: vec![],
                reasoning_summary: format!("No skills resolve intent '{intent}'."),
            });
        }

        let current: BTreeSet<String> = current_states.iter().cloned().collect();
        let mut candidates = Vec::new();
        for skill_id in &matching_ids {
            let mut visiting = HashSet::new();
            let candidate = self.build_plan_for_skill(skill_id, &current, &mut visiting)?;
            candidates.push(candidate);
        }

        candidates.sort_by(|left, right| {
            left.unresolved_states
                .len()
                .cmp(&right.unresolved_states.len())
                .then(left.steps.len().cmp(&right.steps.len()))
                .then(left.target_skill.cmp(&right.target_skill))
        });

        let best = candidates
            .into_iter()
            .next()
            .ok_or_else(|| CatalogError::SkillNotFound(intent.to_string()))?;

        let reasoning_summary = if best.unresolved_states.is_empty() {
            format!(
                "Recommended '{}' because it resolves the intent and all required states can be satisfied from the provided state set or preparatory skills.",
                best.target_skill
            )
        } else {
            format!(
                "Recommended '{}' as the closest match, but some required states are still unresolved.",
                best.target_skill
            )
        };

        Ok(PlanResult {
            intent: intent.to_string(),
            matching_skills: matching_ids,
            recommended_skill: Some(best.target_skill),
            missing_states: best.unresolved_states.into_iter().collect(),
            plan_steps: best.steps,
            reasoning_summary,
        })
    }

    fn build_plan_for_skill(
        &self,
        skill_id: &str,
        current_states: &BTreeSet<String>,
        visiting: &mut HashSet<String>,
    ) -> Result<PlanCandidate, CatalogError> {
        if !visiting.insert(skill_id.to_string()) {
            return Ok(PlanCandidate {
                target_skill: skill_id.to_string(),
                unresolved_states: BTreeSet::new(),
                steps: vec![],
            });
        }

        let details = self.get_skill(skill_id)?;
        let mut simulated_states = current_states.clone();
        let mut unresolved = BTreeSet::new();
        let mut steps = Vec::new();
        let mut added_skills = HashSet::new();

        for required_state in &details.requires_state {
            if simulated_states.contains(required_state) {
                continue;
            }

            let yielding = self.find_skills_yielding_state(required_state)?;
            let mut best_subplan = None;
            let candidate_ids: Vec<String> = yielding
                .into_iter()
                .filter(|skill| skill.id != skill_id && !visiting.contains(&skill.id))
                .map(|skill| skill.id)
                .collect();

            for candidate_id in candidate_ids {
                let subplan =
                    self.build_plan_for_skill(&candidate_id, &simulated_states, visiting)?;
                if is_better_candidate(&subplan, best_subplan.as_ref()) {
                    best_subplan = Some(subplan);
                }
            }

            if let Some(subplan) = best_subplan {
                unresolved.extend(subplan.unresolved_states.iter().cloned());
                for step in subplan.steps {
                    for yielded_state in &step.yields_state {
                        simulated_states.insert(yielded_state.clone());
                    }
                    if added_skills.insert(step.skill_id.clone()) {
                        steps.push(step);
                    }
                }
                if !simulated_states.contains(required_state) {
                    unresolved.insert(required_state.clone());
                }
            } else {
                unresolved.insert(required_state.clone());
            }
        }

        steps.push(PlanStep {
            skill_id: skill_id.to_string(),
            purpose: format!("Execute skill '{skill_id}'"),
            requires_state: details.requires_state.clone(),
            yields_state: details.yields_state.clone(),
        });

        visiting.remove(skill_id);

        Ok(PlanCandidate {
            target_skill: skill_id.to_string(),
            unresolved_states: unresolved,
            steps,
        })
    }

    fn find_skills_by_state_relation(
        &self,
        relation: &str,
        state_uri: &str,
    ) -> Result<Vec<SkillSummary>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT DISTINCT ?id
            WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       {relation} <{state_uri}> .
            }}
            ORDER BY ?id
        "#
        );

        let mut results = Vec::new();
        for row in self.select_rows(&query)? {
            let skill_id = row.required_literal("id")?;
            let details = self.get_skill(&skill_id)?;
            results.push(SkillSummary {
                id: details.id,
                skill_type: details.skill_type,
                nature: details.nature,
                intents: details.intents,
                requires_state: details.requires_state,
                yields_state: details.yields_state,
            });
        }
        Ok(results)
    }

    fn get_requirements_for_uri(
        &self,
        skill_uri: &str,
    ) -> Result<Vec<RequirementInfo>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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

        let mut results = Vec::new();
        for row in self.select_rows(&query)? {
            let req_type_uri = row.required_iri("type")?;
            results.push(RequirementInfo {
                requirement_type: compact_requirement_type(&req_type_uri),
                value: row.required_literal("value")?,
                optional: row.optional_bool("optional").unwrap_or(false),
            });
        }
        Ok(results)
    }

    fn get_related_skill_ids(
        &self,
        skill_uri: &str,
        relation: &str,
    ) -> Result<Vec<String>, CatalogError> {
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
            SELECT ?target
            WHERE {{
                <{skill_uri}> {relation} ?target .
            }}
            ORDER BY ?target
        "#
        );
        let mut values = Vec::new();
        for row in self.select_rows(&query)? {
            let uri = row.required_iri("target")?;
            values.push(self.compact_uri(&uri));
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
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
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
        let query = format!(
            r#"
            PREFIX oc: <http://ontoclaw.marea.software/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?skill
            WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier {skill_id_literal} .
            }}
            LIMIT 1
        "#,
            skill_id_literal = sparql_string(skill_id)
        );

        self.select_rows(&query)?
            .into_iter()
            .next()
            .and_then(|row| row.optional_iri("skill"))
            .ok_or_else(|| CatalogError::SkillNotFound(skill_id.to_string()))
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

fn sorted_vec<I>(iter: I) -> Vec<String>
where
    I: IntoIterator<Item = String>,
{
    let mut values: Vec<String> = iter.into_iter().collect();
    values.sort();
    values
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
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

oc:skill_install a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "install-tool" ;
    oc:nature "Installs the project toolchain" ;
    skos:broader "Setup" ;
    oc:differentia "Ensures the required CLI is available" ;
    oc:resolvesIntent "prepare_environment" ;
    oc:yieldsState oc:ToolInstalled ;
    oc:generatedBy "test-model" .

oc:payload_install a oc:ExecutionPayload ;
    oc:executor "shell" ;
    oc:code "tool install" ;
    oc:timeout 30 .

oc:skill_install oc:hasPayload oc:payload_install .

oc:skill_pdf a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "pdf-generator" ;
    oc:nature "Generates a PDF from an input document" ;
    skos:broader "Document transformation" ;
    oc:differentia "Creates a PDF artifact" ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:ToolInstalled ;
    oc:requiresState oc:FileExists ;
    oc:yieldsState oc:DocumentCreated ;
    oc:generatedBy "test-model" .
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
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

oc:skill_direct a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "direct-pdf" ;
    oc:nature "Direct PDF generation" ;
    skos:broader "Document transformation" ;
    oc:differentia "Runs without setup states" ;
    oc:resolvesIntent "create_pdf" ;
    oc:yieldsState oc:DocumentCreated ;
    oc:generatedBy "test-model" .

oc:skill_needs_setup a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "setup-pdf" ;
    oc:nature "PDF generation with setup" ;
    skos:broader "Document transformation" ;
    oc:differentia "Requires setup first" ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:ToolInstalled ;
    oc:yieldsState oc:DocumentCreated ;
    oc:generatedBy "test-model" .

oc:skill_setup a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "install-tool" ;
    oc:nature "Installs the toolchain" ;
    skos:broader "Setup" ;
    oc:differentia "Provides the tool state" ;
    oc:resolvesIntent "prepare_environment" ;
    oc:yieldsState oc:ToolInstalled ;
    oc:generatedBy "test-model" .
"#,
            base = DEFAULT_BASE_URI
        );

        fs::create_dir_all(root).unwrap();
        fs::write(root.join("index.ttl"), ttl).unwrap();
    }

    #[test]
    fn finds_skills_by_intent() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let skills = catalog.find_skills_by_intent("create_pdf").unwrap();
        assert_eq!(skills.len(), 1);
        assert_eq!(skills[0].id, "pdf-generator");
    }

    #[test]
    fn returns_payload() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let payload = catalog.get_skill_payload("install-tool").unwrap();
        assert!(payload.available);
        assert_eq!(payload.executor.as_deref(), Some("shell"));
    }

    #[test]
    fn plans_with_preparatory_skill() {
        let dir = tempdir().unwrap();
        write_test_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let plan = catalog
            .plan_from_intent("create_pdf", &[String::from("oc:FileExists")])
            .unwrap();

        assert_eq!(plan.recommended_skill.as_deref(), Some("pdf-generator"));
        assert_eq!(plan.plan_steps.len(), 2);
        assert_eq!(plan.plan_steps[0].skill_id, "install-tool");
        assert_eq!(plan.plan_steps[1].skill_id, "pdf-generator");
    }

    #[test]
    fn planning_prefers_direct_skill_when_available() {
        let dir = tempdir().unwrap();
        write_ranked_ontology(dir.path());
        let catalog = Catalog::load(dir.path()).unwrap();

        let plan = catalog.plan_from_intent("create_pdf", &[]).unwrap();

        assert_eq!(plan.recommended_skill.as_deref(), Some("direct-pdf"));
        assert_eq!(plan.plan_steps.len(), 1);
        assert_eq!(plan.plan_steps[0].skill_id, "direct-pdf");
    }
}
