"""
RDF Serialization Module.

Handles serialization of skills to RDF/Turtle format.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from rdflib import Graph, Namespace, RDF, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload
from compiler.exceptions import OntologyValidationError
from compiler.config import BASE_URI, OUTPUT_DIR, resolve_ontology_root
from compiler.core_ontology import get_oc_namespace
from compiler.extractor import generate_skill_id
from compiler.validator import validate_and_raise

logger = logging.getLogger(__name__)


def skill_uri_for_id(skill_id: str) -> URIRef:
    """Build a stable skill URI from the canonical skill identifier."""
    oc = get_oc_namespace()
    return oc[f"skill_{generate_skill_id(skill_id)}"]


def skill_uri_for_skill(skill: ExtractedSkill) -> URIRef:
    """Build the stable URI for a skill model."""
    return skill_uri_for_id(skill.id)


def relation_uri_for_value(value: str) -> URIRef:
    """Convert a skill relation value into a skill URI reference."""
    raw = value.strip()
    oc = get_oc_namespace()
    if raw.startswith("http://") or raw.startswith("https://"):
        return URIRef(raw)
    if raw.startswith("oc:"):
        return oc[raw.removeprefix("oc:")]
    return skill_uri_for_id(raw)


def serialize_skill(graph: Graph, skill: ExtractedSkill) -> None:
    """
    Serialize a skill to RDF triples in the graph.

    Args:
        graph: RDF graph to add triples to
        skill: ExtractedSkill to serialize
    """
    oc = get_oc_namespace()

    # Create stable skill URI from canonical id
    skill_uri = skill_uri_for_skill(skill)

    # Basic properties
    graph.add((skill_uri, RDF.type, oc.Skill))

    # Add appropriate subclass type based on skill_type
    if skill.skill_type == "executable":
        graph.add((skill_uri, RDF.type, oc.ExecutableSkill))
    else:
        graph.add((skill_uri, RDF.type, oc.DeclarativeSkill))

    graph.add((skill_uri, DCTERMS.identifier, Literal(skill.id)))
    graph.add((skill_uri, oc.contentHash, Literal(skill.hash)))
    graph.add((skill_uri, oc.nature, Literal(skill.nature)))
    graph.add((skill_uri, SKOS.broader, Literal(skill.genus)))
    graph.add((skill_uri, oc.differentia, Literal(skill.differentia)))

    # Intents
    for intent in skill.intents:
        graph.add((skill_uri, oc.resolvesIntent, Literal(intent)))

    # Requirements (as blank nodes)
    for req in skill.requirements:
        req_hash = hashlib.sha256(f"{req.type}:{req.value}".encode()).hexdigest()[:8]
        req_uri = oc[f"req_{req_hash}"]

        # Requirement class based on type
        req_class = oc[f"Requirement{req.type}"]
        graph.add((req_uri, RDF.type, req_class))
        graph.add((req_uri, oc.requirementValue, Literal(req.value)))
        graph.add((req_uri, oc.isOptional, Literal(req.optional)))
        graph.add((skill_uri, oc.hasRequirement, req_uri))

    # Relations - serialize as object properties to stable skill URIs
    for dep in skill.depends_on:
        graph.add((skill_uri, oc.dependsOn, relation_uri_for_value(dep)))

    for ext in skill.extends:
        graph.add((skill_uri, oc.extends, relation_uri_for_value(ext)))

    for cont in skill.contradicts:
        graph.add((skill_uri, oc.contradicts, relation_uri_for_value(cont)))

    # State transitions (new schema feature)
    if skill.state_transitions:
        for state_uri in skill.state_transitions.requires_state:
            # Parse oc:StateName format and create full URI
            state_name = state_uri.replace('oc:', '')
            state_ref = oc[state_name]
            graph.add((skill_uri, oc.requiresState, state_ref))

        for state_uri in skill.state_transitions.yields_state:
            state_name = state_uri.replace('oc:', '')
            state_ref = oc[state_name]
            graph.add((skill_uri, oc.yieldsState, state_ref))

        for state_uri in skill.state_transitions.handles_failure:
            state_name = state_uri.replace('oc:', '')
            state_ref = oc[state_name]
            graph.add((skill_uri, oc.handlesFailure, state_ref))

    # LLM attestation
    if skill.generated_by and skill.generated_by != "unknown":
        graph.add((skill_uri, oc.generatedBy, Literal(skill.generated_by)))

    # Execution payload
    if skill.execution_payload:
        payload_uri = oc[f"payload_{skill.hash[:16]}"]
        graph.add((payload_uri, RDF.type, oc.ExecutionPayload))
        graph.add((payload_uri, oc.executor, Literal(skill.execution_payload.executor)))
        graph.add((payload_uri, oc.code, Literal(skill.execution_payload.code)))
        if skill.execution_payload.timeout:
            graph.add((payload_uri, oc.timeout, Literal(skill.execution_payload.timeout)))
        graph.add((skill_uri, oc.hasPayload, payload_uri))

    # Provenance
    if skill.provenance:
        graph.add((skill_uri, PROV.wasDerivedFrom, Literal(skill.provenance)))

    # Knowledge nodes (epistemic knowledge)
    for i, kn in enumerate(skill.knowledge_nodes):
        kn_hash = hashlib.sha256(f"{kn.node_type}:{kn.directive_content}".encode()).hexdigest()[:8]
        kn_uri = oc[f"kn_{kn_hash}"]

        # Add the knowledge node type as class
        graph.add((kn_uri, RDF.type, oc[kn.node_type]))
        graph.add((kn_uri, oc.directiveContent, Literal(kn.directive_content)))
        graph.add((kn_uri, oc.appliesToContext, Literal(kn.applies_to_context)))
        graph.add((kn_uri, oc.hasRationale, Literal(kn.has_rationale)))

        if kn.severity_level:
            graph.add((kn_uri, oc.severityLevel, Literal(kn.severity_level.value)))

        # Link skill to knowledge node
        graph.add((skill_uri, oc.impartsKnowledge, kn_uri))


def serialize_skill_to_module(
    skill: ExtractedSkill,
    output_path: Path,
    output_base: Optional[Path] = None
) -> None:
    """
    Serialize a skill to a standalone ontoskill.ttl module file.

    Creates a skill module that mirrors the skills directory structure:
    - skills/xlsx/pdf/pptx/SKILL.md -> ontoskills/xlsx/pdf/pptx/ontoskill.ttl

    Args:
        skill: ExtractedSkill to serialize
        output_path: Path where ontoskill.ttl should be written
        output_base: Base output directory for core ontology lookup (default: OUTPUT_DIR)
    """
    oc = get_oc_namespace()
    g = Graph()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", Namespace("http://www.w3.org/2000/01/rdf-schema#"))
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Add imports to core ontology
    if output_base is None:
        output_base = Path(OUTPUT_DIR).resolve()
    else:
        output_base = Path(output_base).resolve()

    core_ontology_path = resolve_ontology_root(output_base) / "ontoclaw-core.ttl"
    if core_ontology_path.exists():
        g.add((URIRef(BASE_URI.rstrip('#')), OWL.imports, URIRef(f"file://{core_ontology_path}")))

    # Serialize the skill
    serialize_skill(g, skill)

    # VALIDATE BEFORE WRITE
    try:
        validate_and_raise(g)
    except OntologyValidationError as e:
        logger.critical(f"Refusing to write invalid skill to {output_path}")
        raise

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(output_path, format="turtle")
    logger.info(f"Serialized skill module to {output_path}")
