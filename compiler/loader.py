"""
RDF Ontology Loader Module.

Handles OWL 2 RDF/Turtle serialization, intelligent merging,
and atomic writes for the skill ontology.
"""

import hashlib
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import owlrl
import rdflib
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload
from compiler.exceptions import OntologyLoadError
from compiler.config import BASE_URI, CORE_STATES, FAILURE_STATES, SKILLS_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)


def mirror_skill_path(skill_dir: Path, output_base: Path) -> Path:
    """
    Mirror the skills directory structure to the output directory.

    Mirroring rule:
        skills/{path}/SKILL.md → semantic-skills/{path}/skill.ttl

    Args:
        skill_dir: Path to skill directory (e.g., skills/xlsx/pdf/pptx)
        output_base: Base output directory (e.g., semantic-skills/)

    Returns:
        Path to output skill.ttl file (e.g., semantic-skills/xlsx/pdf/pptx/skill.ttl)
    """
    # Convert to absolute paths if needed
    skill_dir = skill_dir.resolve()
    output_base = output_base.resolve()

    # Get relative path from skills directory
    # If skill_dir is /path/to/skills/xlsx/pdf/pptx
    # and SKILLS_DIR is /path/to/skills
    # relative should be xlsx/pdf/pptx
    try:
        skills_base = Path(SKILLS_DIR).resolve()
        relative = skill_dir.relative_to(skills_base)
    except ValueError:
        # If skill_dir is not under SKILLS_DIR, try to extract relative path
        # Check if it looks like a path under a "skills" directory
        parts = skill_dir.parts
        if 'skills' in parts:
            # Extract path after 'skills' directory
            skills_idx = parts.index('skills')
            relative = Path(*parts[skills_idx + 1:])
        else:
            # Fall back to using the skill directory name
            relative = skill_dir.name

    # Mirror the path structure
    output_path = output_base / relative / "skill.ttl"
    return output_path


def get_output_path(skill_dir: Path, output_base: Optional[Path] = None) -> Path:
    """
    Get the output path for a skill module.

    Args:
        skill_dir: Path to skill directory containing SKILL.md
        output_base: Base output directory (default: from config)

    Returns:
        Path where skill.ttl should be written
    """
    if output_base is None:
        output_base = Path(OUTPUT_DIR).resolve()

    return mirror_skill_path(skill_dir, output_base)


def create_output_directory(skill_dir: Path, output_base: Optional[Path] = None) -> Path:
    """
    Create the output directory for a skill module.

    Args:
        skill_dir: Path to skill directory containing SKILL.md
        output_base: Base output directory (default: from config)

    Returns:
        Path to created output directory
    """
    output_path = get_output_path(skill_dir, output_base)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path.parent


def get_oc_namespace() -> Namespace:
    """Get the OntoClaw namespace using configured BASE_URI."""
    return Namespace(BASE_URI)


def create_core_ontology(output_path: Optional[Path] = None) -> Graph:
    """
    Create the core OntoClaw ontology (TBox) with state transition system.

    Generates ontoclaw-core.ttl containing:
    - Core classes (Skill, State, Attempt, ExecutionPayload)
    - State transition properties (requiresState, yieldsState, handlesFailure, hasStatus)
    - Execution payload properties (hasPayload, executor, code, timeout)
    - LLM attestation (generatedBy)
    - Predefined core and failure states

    Args:
        output_path: Path where ontoclaw-core.ttl will be saved (default: OUTPUT_DIR/ontoclaw-core.ttl)

    Returns:
        Graph with core ontology definitions
    """
    if output_path is None:
        output_base = Path(OUTPUT_DIR).resolve()
        output_path = output_base / "ontoclaw-core.ttl"

    oc = get_oc_namespace()
    g = Graph()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Ontology header
    base_uri = URIRef(BASE_URI.rstrip('#'))
    g.add((base_uri, RDF.type, OWL.Ontology))
    g.add((base_uri, DCTERMS.title, Literal("OntoClaw Core Ontology")))
    g.add((base_uri, DCTERMS.description, Literal(
        "Core TBox ontology for skill state transitions and execution"
    )))
    g.add((base_uri, DCTERMS.created, Literal(datetime.now().isoformat())))

    # ========== Core Classes ==========

    # oc:Skill - Base class for all skills
    g.add((oc.Skill, RDF.type, OWL.Class))
    g.add((oc.Skill, RDFS.label, Literal("Skill")))
    g.add((oc.Skill, RDFS.comment, Literal(
        "Base class for all executable skills in the ontology"
    )))

    # oc:ExecutableSkill - Skills with execution payloads
    g.add((oc.ExecutableSkill, RDF.type, OWL.Class))
    g.add((oc.ExecutableSkill, RDFS.subClassOf, oc.Skill))
    g.add((oc.ExecutableSkill, RDFS.label, Literal("Executable Skill")))
    g.add((oc.ExecutableSkill, RDFS.comment, Literal(
        "A skill with an executable code payload"
    )))

    # oc:DeclarativeSkill - Skills without execution (knowledge only)
    g.add((oc.DeclarativeSkill, RDF.type, OWL.Class))
    g.add((oc.DeclarativeSkill, RDFS.subClassOf, oc.Skill))
    g.add((oc.DeclarativeSkill, RDFS.label, Literal("Declarative Skill")))
    g.add((oc.DeclarativeSkill, RDFS.comment, Literal(
        "A skill without executable code (declarative knowledge)"
    )))

    # oc:State - Abstract state class
    g.add((oc.State, RDF.type, OWL.Class))
    g.add((oc.State, RDFS.label, Literal("State")))
    g.add((oc.State, RDFS.comment, Literal(
        "Abstract class representing a system state (precondition, outcome, or failure)"
    )))

    # oc:Attempt - Execution attempt record
    g.add((oc.Attempt, RDF.type, OWL.Class))
    g.add((oc.Attempt, RDFS.label, Literal("Attempt")))
    g.add((oc.Attempt, RDFS.comment, Literal(
        "Record of a skill execution attempt, used for negative memory"
    )))

    # oc:ExecutionPayload - Container for executable code
    g.add((oc.ExecutionPayload, RDF.type, OWL.Class))
    g.add((oc.ExecutionPayload, RDFS.label, Literal("Execution Payload")))
    g.add((oc.ExecutionPayload, RDFS.comment, Literal(
        "Container for executable code and execution metadata"
    )))

    # ========== State Transition Properties ==========

    # oc:requiresState (Skill → State) - Pre-conditions
    g.add((oc.requiresState, RDF.type, OWL.ObjectProperty))
    g.add((oc.requiresState, RDFS.domain, oc.Skill))
    g.add((oc.requiresState, RDFS.range, oc.State))
    g.add((oc.requiresState, RDFS.label, Literal("requires state")))
    g.add((oc.requiresState, RDFS.comment, Literal(
        "Pre-condition state that must be satisfied before skill execution"
    )))

    # oc:yieldsState (Skill → State) - Success outcomes
    g.add((oc.yieldsState, RDF.type, OWL.ObjectProperty))
    g.add((oc.yieldsState, RDFS.domain, oc.Skill))
    g.add((oc.yieldsState, RDFS.range, oc.State))
    g.add((oc.yieldsState, RDFS.label, Literal("yields state")))
    g.add((oc.yieldsState, RDFS.comment, Literal(
        "State that results from successful skill execution"
    )))

    # oc:handlesFailure (Skill → State) - Failure states
    g.add((oc.handlesFailure, RDF.type, OWL.ObjectProperty))
    g.add((oc.handlesFailure, RDFS.domain, oc.Skill))
    g.add((oc.handlesFailure, RDFS.range, oc.State))
    g.add((oc.handlesFailure, RDFS.label, Literal("handles failure")))
    g.add((oc.handlesFailure, RDFS.comment, Literal(
        "Failure state that this skill can handle or recover from"
    )))

    # oc:hasStatus (Attempt → State) - Execution status
    g.add((oc.hasStatus, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasStatus, RDFS.domain, oc.Attempt))
    g.add((oc.hasStatus, RDFS.range, oc.State))
    g.add((oc.hasStatus, RDFS.label, Literal("has status")))
    g.add((oc.hasStatus, RDFS.comment, Literal(
        "Current status state of an execution attempt"
    )))

    # ========== Execution Payload Properties ==========

    # oc:hasPayload (Skill → ExecutionPayload)
    g.add((oc.hasPayload, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasPayload, RDFS.domain, oc.Skill))
    g.add((oc.hasPayload, RDFS.range, oc.ExecutionPayload))
    g.add((oc.hasPayload, RDFS.label, Literal("has payload")))
    g.add((oc.hasPayload, RDFS.comment, Literal(
        "Links a skill to its execution payload"
    )))

    # oc:executor (DatatypeProperty)
    g.add((oc.executor, RDF.type, OWL.DatatypeProperty))
    g.add((oc.executor, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.executor, RDFS.label, Literal("executor")))
    g.add((oc.executor, RDFS.comment, Literal(
        "Executor type (e.g., 'shell', 'python', 'javascript')"
    )))

    # oc:code (DatatypeProperty)
    g.add((oc.code, RDF.type, OWL.DatatypeProperty))
    g.add((oc.code, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.code, RDFS.label, Literal("code")))
    g.add((oc.code, RDFS.comment, Literal(
        "Executable code as a string"
    )))

    # oc:timeout (DatatypeProperty)
    g.add((oc.timeout, RDF.type, OWL.DatatypeProperty))
    g.add((oc.timeout, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.timeout, RDFS.label, Literal("timeout")))
    g.add((oc.timeout, RDFS.comment, Literal(
        "Execution timeout in seconds"
    )))

    # ========== LLM Attestation ==========

    # oc:generatedBy (DatatypeProperty)
    g.add((oc.generatedBy, RDF.type, OWL.DatatypeProperty))
    g.add((oc.generatedBy, RDFS.domain, oc.Skill))
    g.add((oc.generatedBy, RDFS.label, Literal("generated by")))
    g.add((oc.generatedBy, RDFS.comment, Literal(
        "LLM model identifier that generated this skill (e.g., 'claude-sonnet-4-6-20250514')"
    )))

    # ========== Additional Skill Properties ==========

    # oc:contentHash (DatatypeProperty)
    g.add((oc.contentHash, RDF.type, OWL.DatatypeProperty))
    g.add((oc.contentHash, RDFS.domain, oc.Skill))
    g.add((oc.contentHash, RDFS.label, Literal("content hash")))
    g.add((oc.contentHash, RDFS.comment, Literal(
        "SHA-256 hash of skill content for deduplication"
    )))

    # oc:nature (DatatypeProperty)
    g.add((oc.nature, RDF.type, OWL.DatatypeProperty))
    g.add((oc.nature, RDFS.domain, oc.Skill))
    g.add((oc.nature, RDFS.label, Literal("nature")))
    g.add((oc.nature, RDFS.comment, Literal(
        "Definition/differentia of the skill (what makes it unique)"
    )))

    # oc:differentia (DatatypeProperty)
    g.add((oc.differentia, RDF.type, OWL.DatatypeProperty))
    g.add((oc.differentia, RDFS.domain, oc.Skill))
    g.add((oc.differentia, RDFS.label, Literal("differentia")))
    g.add((oc.differentia, RDFS.comment, Literal(
        "Specific characteristics that differentiate this skill"
    )))

    # oc:resolvesIntent (DatatypeProperty)
    g.add((oc.resolvesIntent, RDF.type, OWL.DatatypeProperty))
    g.add((oc.resolvesIntent, RDFS.domain, oc.Skill))
    g.add((oc.resolvesIntent, RDFS.label, Literal("resolves intent")))
    g.add((oc.resolvesIntent, RDFS.comment, Literal(
        "User intent that this skill can resolve"
    )))

    # oc:hasConstraint (DatatypeProperty)
    g.add((oc.hasConstraint, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasConstraint, RDFS.domain, oc.Skill))
    g.add((oc.hasConstraint, RDFS.label, Literal("has constraint")))
    g.add((oc.hasConstraint, RDFS.comment, Literal(
        "Constraints or limitations on skill execution"
    )))

    # ========== Requirement Properties ==========

    # oc:hasRequirement (ObjectProperty)
    g.add((oc.hasRequirement, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasRequirement, RDFS.domain, oc.Skill))
    g.add((oc.hasRequirement, RDFS.label, Literal("has requirement")))
    g.add((oc.hasRequirement, RDFS.comment, Literal(
        "Links a skill to its requirements"
    )))

    # oc:requirementValue (DatatypeProperty)
    g.add((oc.requirementValue, RDF.type, OWL.DatatypeProperty))
    g.add((oc.requirementValue, RDFS.label, Literal("requirement value")))
    g.add((oc.requirementValue, RDFS.comment, Literal(
        "Value of a requirement (e.g., tool name, version)"
    )))

    # oc:isOptional (DatatypeProperty)
    g.add((oc.isOptional, RDF.type, OWL.DatatypeProperty))
    g.add((oc.isOptional, RDFS.label, Literal("is optional")))
    g.add((oc.isOptional, RDFS.comment, Literal(
        "Whether a requirement is optional or required"
    )))

    # ========== Skill Relationship Properties ==========

    # oc:dependsOn (ObjectProperty) - asymmetric
    g.add((oc.dependsOn, RDF.type, OWL.ObjectProperty))
    g.add((oc.dependsOn, RDF.type, OWL.AsymmetricProperty))
    g.add((oc.dependsOn, RDFS.domain, oc.Skill))
    g.add((oc.dependsOn, RDFS.range, oc.Skill))
    g.add((oc.dependsOn, RDFS.label, Literal("depends on")))
    g.add((oc.dependsOn, RDFS.comment, Literal(
        "Skill depends on another skill (prerequisite)"
    )))
    g.add((oc.dependsOn, OWL.inverseOf, oc.enables))

    # oc:enables (ObjectProperty) - inverse of dependsOn
    g.add((oc.enables, RDF.type, OWL.ObjectProperty))
    g.add((oc.enables, RDFS.domain, oc.Skill))
    g.add((oc.enables, RDFS.range, oc.Skill))
    g.add((oc.enables, RDFS.label, Literal("enables")))
    g.add((oc.enables, RDFS.comment, Literal(
        "Skill enables another skill (inverse of dependsOn)"
    )))

    # oc:extends (ObjectProperty) - transitive
    g.add((oc.extends, RDF.type, OWL.ObjectProperty))
    g.add((oc.extends, RDF.type, OWL.TransitiveProperty))
    g.add((oc.extends, RDFS.domain, oc.Skill))
    g.add((oc.extends, RDFS.range, oc.Skill))
    g.add((oc.extends, RDFS.label, Literal("extends")))
    g.add((oc.extends, RDFS.comment, Literal(
        "Skill extends another skill (inheritance)"
    )))
    g.add((oc.extends, OWL.inverseOf, oc.isExtendedBy))

    # oc:isExtendedBy (ObjectProperty) - inverse of extends
    g.add((oc.isExtendedBy, RDF.type, OWL.ObjectProperty))
    g.add((oc.isExtendedBy, RDFS.domain, oc.Skill))
    g.add((oc.isExtendedBy, RDFS.range, oc.Skill))
    g.add((oc.isExtendedBy, RDFS.label, Literal("is extended by")))
    g.add((oc.isExtendedBy, RDFS.comment, Literal(
        "Inverse of extends"
    )))

    # oc:contradicts (ObjectProperty) - symmetric
    g.add((oc.contradicts, RDF.type, OWL.ObjectProperty))
    g.add((oc.contradicts, RDF.type, OWL.SymmetricProperty))
    g.add((oc.contradicts, RDFS.domain, oc.Skill))
    g.add((oc.contradicts, RDFS.range, oc.Skill))
    g.add((oc.contradicts, RDFS.label, Literal("contradicts")))
    g.add((oc.contradicts, RDFS.comment, Literal(
        "Skill contradicts another skill (mutually exclusive)"
    )))

    # ========== Predefined Core States ==========

    for state_name, state_fragment in CORE_STATES.items():
        state_uri = oc[state_fragment.lstrip('#')]
        g.add((state_uri, RDF.type, OWL.Class))
        g.add((state_uri, RDFS.subClassOf, oc.State))
        g.add((state_uri, RDFS.label, Literal(state_name)))
        g.add((state_uri, SKOS.prefLabel, Literal(state_name)))

    # ========== Predefined Failure States ==========

    for state_name, state_fragment in FAILURE_STATES.items():
        state_uri = oc[state_fragment.lstrip('#')]
        g.add((state_uri, RDF.type, OWL.Class))
        g.add((state_uri, RDFS.subClassOf, oc.State))
        g.add((state_uri, RDFS.label, Literal(state_name)))
        g.add((state_uri, SKOS.prefLabel, Literal(state_name)))

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output_path, format="turtle")
    logger.info(f"Created core ontology at {output_path} with {len(g)} triples")

    return g


def serialize_skill(graph: Graph, skill: ExtractedSkill) -> None:
    """
    Serialize a skill to RDF triples in the graph.

    Args:
        graph: RDF graph to add triples to
        skill: ExtractedSkill to serialize
    """
    oc = get_oc_namespace()

    # Create skill URI from hash
    skill_uri = oc[f"skill_{skill.hash[:16]}"]

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

    # Relations
    for dep in skill.depends_on:
        graph.add((skill_uri, oc.dependsOn, oc[f"skill_{dep}"]))

    for ext in skill.extends:
        graph.add((skill_uri, oc.extends, oc[f"skill_{ext}"]))

    for cont in skill.contradicts:
        graph.add((skill_uri, oc.contradicts, oc[f"skill_{cont}"]))

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


def serialize_skill_to_module(skill: ExtractedSkill, output_path: Path) -> None:
    """
    Serialize a skill to a standalone skill.ttl module file.

    Creates a skill module that mirrors the skills directory structure:
    - skills/xlsx/pdf/pptx/SKILL.md → semantic-skills/xlsx/pdf/pptx/skill.ttl

    Args:
        skill: ExtractedSkill to serialize
        output_path: Path where skill.ttl should be written
    """
    oc = get_oc_namespace()
    g = Graph()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Add imports to core ontology
    core_ontology_path = Path(OUTPUT_DIR).resolve() / "ontoclaw-core.ttl"
    if core_ontology_path.exists():
        g.add((URIRef(BASE_URI.rstrip('#')), OWL.imports, URIRef(f"file://{core_ontology_path}")))

    # Serialize the skill
    serialize_skill(g, skill)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(output_path, format="turtle")
    logger.info(f"Serialized skill module to {output_path}")


def load_skill_module(module_path: Path) -> Graph:
    """
    Load a skill module from a skill.ttl file.

    Args:
        module_path: Path to skill.ttl file

    Returns:
        RDF Graph containing the skill module

    Raises:
        OntologyLoadError: If file cannot be loaded
    """
    if not module_path.exists():
        raise OntologyLoadError(f"Skill module not found: {module_path}")

    try:
        graph = Graph()
        graph.parse(module_path, format="turtle")
        logger.info(f"Loaded skill module from {module_path} with {len(graph)} triples")
        return graph
    except Exception as e:
        raise OntologyLoadError(f"Failed to load skill module: {e}")


def load_ontology(ontology_path: Path) -> Graph:
    """
    Load an existing ontology from file.

    Args:
        ontology_path: Path to skills.ttl file

    Returns:
        RDF Graph with loaded ontology

    Raises:
        OntologyLoadError: If file cannot be loaded
    """
    if not ontology_path.exists():
        logger.info(f"Creating new ontology at {ontology_path}")
        # Create a minimal graph with namespace bindings
        g = Graph()
        oc = get_oc_namespace()
        g.bind("oc", oc)
        g.bind("owl", OWL)
        g.bind("rdf", RDF)
        g.bind("rdfs", RDFS)
        g.bind("dcterms", DCTERMS)
        g.bind("skos", SKOS)
        g.bind("prov", PROV)
        return g

    try:
        graph = Graph()
        graph.parse(ontology_path, format="turtle")
        logger.info(f"Loaded ontology with {len(graph)} triples")
        return graph
    except Exception as e:
        raise OntologyLoadError(f"Failed to load ontology: {e}")


def get_hash_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract hash → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping hashes to skill URIs
    """
    oc = get_oc_namespace()
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, oc.Skill):
        hash_literal = graph.value(skill_uri, oc.contentHash)
        if hash_literal:
            mapping[str(hash_literal)] = skill_uri
    return mapping


def get_id_mapping(graph: Graph) -> dict[str, URIRef]:
    """
    Extract ID → URI mapping from existing ontology.

    Args:
        graph: RDF graph to scan

    Returns:
        Dictionary mapping IDs to skill URIs
    """
    oc = get_oc_namespace()
    mapping = {}
    for skill_uri in graph.subjects(RDF.type, oc.Skill):
        id_literal = graph.value(skill_uri, DCTERMS.identifier)
        if id_literal:
            mapping[str(id_literal)] = skill_uri
    return mapping


def remove_skill(graph: Graph, skill_uri: URIRef) -> None:
    """
    Remove all triples for a skill from the graph.

    Args:
        graph: RDF graph to modify
        skill_uri: URI of skill to remove
    """
    oc = get_oc_namespace()

    # Remove all triples where skill is subject
    for predicate in set(graph.predicates(subject=skill_uri)):
        for obj in graph.objects(skill_uri, predicate):
            graph.remove((skill_uri, predicate, obj))

    # Remove requirement blank nodes
    for req_uri in graph.objects(skill_uri, oc.hasRequirement):
        for p, o in list(graph.predicate_objects(req_uri)):
            graph.remove((req_uri, p, o))

    # Remove payload blank node
    payload_uri = graph.value(skill_uri, oc.hasPayload)
    if payload_uri:
        for p, o in list(graph.predicate_objects(payload_uri)):
            graph.remove((payload_uri, p, o))


def merge_skill(ontology_path: Path, skill: ExtractedSkill) -> Graph:
    """
    Intelligently merge a skill into the ontology.

    - If hash exists → skip (unchanged)
    - If same ID but different hash → remove old, add new
    - If new ID → add

    Args:
        ontology_path: Path to ontology file
        skill: Skill to merge

    Returns:
        Updated graph (not saved to disk)
    """
    graph = load_ontology(ontology_path)
    hash_mapping = get_hash_mapping(graph)
    id_mapping = get_id_mapping(graph)

    # Check if unchanged (same hash)
    if skill.hash in hash_mapping:
        logger.info(f"Skill {skill.id} unchanged (hash match), skipping")
        return graph

    # Check if updated (same ID, different hash)
    if skill.id in id_mapping:
        old_uri = id_mapping[skill.id]
        logger.info(f"Skill {skill.id} updated, removing old version")
        remove_skill(graph, old_uri)

    # Add new/updated skill
    logger.info(f"Adding skill {skill.id} to ontology")
    serialize_skill(graph, skill)

    return graph


def save_ontology_atomic(
    ontology_path: Path,
    graph: Graph,
    backup_dir: Optional[Path] = None,
    max_backups: int = 5
) -> None:
    """
    Save ontology with atomic write and backup.

    1. Backup existing file
    2. Write to temp file
    3. Atomic rename
    4. Cleanup old backups

    Args:
        ontology_path: Path to skills.ttl
        graph: RDF graph to save
        backup_dir: Directory for backups (default: ontology_dir/backups/)
        max_backups: Maximum number of backups to keep
    """
    if backup_dir is None:
        backup_dir = ontology_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if ontology_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"skills_{timestamp}.ttl"
        shutil.copy2(ontology_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

    # Write to temp file
    temp_path = ontology_path.with_suffix(".ttl.tmp")
    graph.serialize(temp_path, format="turtle")

    # Atomic rename
    shutil.move(str(temp_path), str(ontology_path))
    logger.info(f"Saved ontology to {ontology_path}")

    # Cleanup old backups
    backups = sorted(backup_dir.glob("skills_*.ttl"))
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        oldest.unlink()
        logger.debug(f"Removed old backup: {oldest}")


def apply_reasoning(graph: Graph) -> Graph:
    """
    Apply OWL 2 RL reasoning to infer new triples.

    Inferences:
    - Inverse: A dependsOn B → B enables A
    - Transitive: A extends B, B extends C → A extends C
    - Symmetric: A contradicts B → B contradicts A

    Args:
        graph: RDF graph to expand

    Returns:
        Same graph with inferred triples added
    """
    logger.info("Applying OWL reasoning...")
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(graph)
    logger.info(f"Reasoning complete, graph now has {len(graph)} triples")
    return graph


def generate_index_manifest(
    skill_paths: list[Path],
    index_path: Path,
    output_base: Optional[Path] = None
) -> None:
    """
    Generate the index.ttl manifest that lists all skill modules.

    Creates an index manifest with owl:imports referencing all skill modules,
    enabling SPARQL queries against the combined ontology by loading index.ttl.

    Args:
        skill_paths: List of paths to skill.ttl module files
        index_path: Path where index.ttl will be written
        output_base: Base output directory for computing relative paths
    """
    if output_base is None:
        output_base = Path(OUTPUT_DIR).resolve()
    else:
        output_base = output_base.resolve()

    oc = get_oc_namespace()
    g = Graph()

    # Bind namespaces
    g.bind("oc", oc)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("prov", PROV)

    # Ontology header
    base_uri = URIRef(BASE_URI.rstrip('#'))
    g.add((base_uri, RDF.type, OWL.Ontology))
    g.add((base_uri, DCTERMS.title, Literal("OntoClaw Skill Index")))
    g.add((base_uri, DCTERMS.description, Literal(
        "Index manifest referencing all compiled skill modules"
    )))
    g.add((base_uri, DCTERMS.created, Literal(datetime.now().isoformat())))

    # Import core ontology
    core_path = output_base / "ontoclaw-core.ttl"
    if core_path.exists():
        g.add((base_uri, OWL.imports, URIRef(f"file://{core_path}")))

    # Import all skill modules
    for skill_path in skill_paths:
        skill_path = skill_path.resolve()
        g.add((base_uri, OWL.imports, URIRef(f"file://{skill_path}")))

    # Ensure output directory exists
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(index_path, format="turtle")
    logger.info(f"Generated index manifest at {index_path} with {len(skill_paths)} skill imports")
