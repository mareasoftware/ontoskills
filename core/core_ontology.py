"""
Core Ontology Module.

Contains the OntoClaw namespace and core ontology creation functions.
This module defines the TBox (terminology) for the skill ontology including:
- Core classes (Skill, ExecutableSkill, DeclarativeSkill, State, Attempt, ExecutionPayload)
- State transition properties (requiresState, yieldsState, handlesFailure, hasStatus)
- Execution payload properties (hasPayload, executor, code, timeout)
- LLM attestation (generatedBy)
- Skill relationship properties (dependsOn, extends, contradicts, etc.)
- Predefined core and failure states
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS, SKOS, PROV

from compiler.config import BASE_URI, CORE_STATES, FAILURE_STATES, OUTPUT_DIR

logger = logging.getLogger(__name__)


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

    # OWL 2 DL: DeclarativeSkill and ExecutableSkill are mutually exclusive
    g.add((oc.DeclarativeSkill, OWL.disjointWith, oc.ExecutableSkill))

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

    # oc:executionPath (DatatypeProperty) - Path to bundled executable asset
    g.add((oc.executionPath, RDF.type, OWL.DatatypeProperty))
    g.add((oc.executionPath, RDFS.domain, oc.ExecutionPayload))
    g.add((oc.executionPath, RDFS.label, Literal("execution path")))
    g.add((oc.executionPath, RDFS.comment, Literal(
        "Relative URI/path to the executable asset file copied by the compiler (e.g., './scripts/document.py')"
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
