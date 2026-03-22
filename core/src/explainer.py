"""
Human-readable skill explainer for OntoSkills ontologies.

Reads a compiled skill from its .ttl file (or from the index) and renders
a structured summary card showing every relevant property — intents, states,
dependencies, executor, hash, and provenance.

Usage:
    from compiler.explainer import explain_skill, SkillSummary
    summary = explain_skill(ttl_path, skill_id="create-pdf")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import DCTERMS

OC = Namespace("https://ontoskills.sh/ontology#")


@dataclass
class KnowledgeNodeSummary:
    """Summary of a single knowledge node imparted by a skill."""
    node_id: str                       # Local ID (e.g., "kn_21eaa806")
    node_type: str                     # Type (e.g., "PreFlightCheck", "Heuristic")
    directive_content: str             # The actual rule/guideline
    applies_to_context: str            # When this rule applies
    has_rationale: str                 # Why this rule exists
    severity_level: str | None         # CRITICAL, HIGH, MEDIUM, LOW


@dataclass
class RequirementSummary:
    """Summary of a skill requirement."""
    requirement_id: str                # Local ID (e.g., "req_060db269")
    requirement_value: str             # The actual requirement (e.g., "pypdf")
    is_optional: bool                  # Whether the requirement is optional


@dataclass
class SkillSummary:
    skill_id: str
    skill_type: str                    # "ExecutableSkill" | "DeclarativeSkill" | "Skill"
    nature: str
    intents: list[str]                 = field(default_factory=list)
    requires_states: list[str]         = field(default_factory=list)
    yields_states: list[str]           = field(default_factory=list)
    handles_failures: list[str]        = field(default_factory=list)
    knowledge_nodes: list[KnowledgeNodeSummary] = field(default_factory=list)
    requirements: list[RequirementSummary] = field(default_factory=list)
    executor: str | None               = None
    content_hash: str | None           = None
    generated_by: str | None           = None


def explain_skill(ttl_path: str | Path, skill_id: str) -> SkillSummary | None:
    """
    Extract a SkillSummary for the given skill_id from a .ttl file.

    Args:
        ttl_path: Path to the compiled ontology (.ttl).
        skill_id: The local identifier of the skill (e.g. "create-pdf").

    Returns:
        SkillSummary if the skill is found, None otherwise.
    """
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    return _build_summary(g, skill_id)


def list_skill_ids(ttl_path: str | Path) -> list[str]:
    """Return all skill IDs present in the ontology file."""
    g = Graph()
    g.parse(str(ttl_path), format="turtle")
    ids: list[str] = []
    for s in g.subjects(OC.resolvesIntent):
        id_lit = g.value(s, DCTERMS.identifier)
        if id_lit:
            ids.append(str(id_lit))
        else:
            ids.append(_local(s))
    return sorted(set(ids))


# ─── Private helpers ──────────────────────────────────────────────────────────


def _local(uri) -> str:
    return str(uri).split("#")[-1].split("/")[-1]


def _skill_type(g: Graph, uri) -> str:
    if (uri, RDF.type, OC.ExecutableSkill) in g:
        return "ExecutableSkill"
    if (uri, RDF.type, OC.DeclarativeSkill) in g:
        return "DeclarativeSkill"
    return "Skill"


def _build_summary(g: Graph, skill_id: str) -> SkillSummary | None:
    """Locate the skill URI and populate a SkillSummary from its triples."""
    skill_uri = None

    # Try matching by dcterms:identifier first (most reliable)
    for s in g.subjects(DCTERMS.identifier, None):
        id_lit = g.value(s, DCTERMS.identifier)
        if id_lit and str(id_lit) == skill_id:
            skill_uri = s
            break

    # Fall back to local URI fragment
    if skill_uri is None:
        for s in g.subjects(OC.resolvesIntent):
            if _local(s) == skill_id or _local(s) == skill_id.replace("-", "").replace("_", "").lower():
                skill_uri = s
                break

    if skill_uri is None:
        return None

    nature_lit = g.value(skill_uri, OC.nature)
    nature = str(nature_lit) if nature_lit else ""

    intents         = [str(o) for o in g.objects(skill_uri, OC.resolvesIntent)]
    requires_states = [_local(o) for o in g.objects(skill_uri, OC.requiresState)]
    yields_states   = [_local(o) for o in g.objects(skill_uri, OC.yieldsState)]
    handles_failures= [_local(o) for o in g.objects(skill_uri, OC.handlesFailure)]

    # Extract knowledge nodes
    knowledge_nodes = _extract_knowledge_nodes(g, skill_uri)

    # Extract requirements
    requirements = _extract_requirements(g, skill_uri)

    # Executor lives inside oc:ExecutionPayload
    executor = None
    payload_uri = g.value(skill_uri, OC.hasPayload)
    if payload_uri:
        exec_lit = g.value(payload_uri, OC.executor)
        if exec_lit:
            executor = str(exec_lit)

    hash_lit = g.value(skill_uri, OC.contentHash)
    gen_lit  = g.value(skill_uri, OC.generatedBy)

    return SkillSummary(
        skill_id        = skill_id,
        skill_type      = _skill_type(g, skill_uri),
        nature          = nature,
        intents         = sorted(intents),
        requires_states = sorted(requires_states),
        yields_states   = sorted(yields_states),
        handles_failures= sorted(handles_failures),
        knowledge_nodes = knowledge_nodes,
        requirements    = requirements,
        executor        = executor,
        content_hash    = str(hash_lit)[:8] if hash_lit else None,
        generated_by    = str(gen_lit) if gen_lit else None,
    )


def _extract_knowledge_nodes(g: Graph, skill_uri) -> list[KnowledgeNodeSummary]:
    """Extract all knowledge nodes imparted by a skill."""
    nodes: list[KnowledgeNodeSummary] = []
    for kn_uri in g.objects(skill_uri, OC.impartsKnowledge):
        # Get the node type (the RDF class, e.g., oc:PreFlightCheck)
        node_type = _get_node_type(g, kn_uri)

        directive = g.value(kn_uri, OC.directiveContent)
        context = g.value(kn_uri, OC.appliesToContext)
        rationale = g.value(kn_uri, OC.hasRationale)
        severity = g.value(kn_uri, OC.severityLevel)

        nodes.append(KnowledgeNodeSummary(
            node_id=_local(kn_uri),
            node_type=node_type,
            directive_content=str(directive) if directive else "",
            applies_to_context=str(context) if context else "",
            has_rationale=str(rationale) if rationale else "",
            severity_level=str(severity) if severity else None,
        ))
    # Sort for deterministic output (avoid rdflib iteration order)
    nodes.sort(key=lambda n: (n.node_type, n.node_id))
    return nodes


def _get_node_type(g: Graph, kn_uri) -> str:
    """Get the knowledge node type (the specific subclass of KnowledgeNode)."""
    # Get all types and find the one that's a subclass of KnowledgeNode
    for type_uri in g.objects(kn_uri, RDF.type):
        type_local = _local(type_uri)
        # Skip generic "KnowledgeNode" type, return the specific subtype
        if type_local != "KnowledgeNode" and type_local != "Class":
            return type_local
    return "KnowledgeNode"


def _extract_requirements(g: Graph, skill_uri) -> list[RequirementSummary]:
    """Extract all requirements for a skill."""
    reqs: list[RequirementSummary] = []
    for req_uri in g.objects(skill_uri, OC.hasRequirement):
        value = g.value(req_uri, OC.requirementValue)
        optional = g.value(req_uri, OC.isOptional)

        reqs.append(RequirementSummary(
            requirement_id=_local(req_uri),
            requirement_value=str(value) if value else "",
            is_optional=str(optional).lower() == "true" if optional else False,
        ))
    # Sort for deterministic output (avoid rdflib iteration order)
    reqs.sort(key=lambda r: r.requirement_id)
    return reqs
