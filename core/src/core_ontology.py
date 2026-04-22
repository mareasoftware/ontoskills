"""
Core Ontology Module.

Contains the OntoSkills namespace and core ontology creation functions.
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

from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef, BNode, XSD
from rdflib.namespace import DCTERMS, SKOS, PROV
from rdflib.collection import Collection

from compiler.config import BASE_URI, CORE_ONTOLOGY_FILENAME, CORE_STATES, FAILURE_STATES, OUTPUT_DIR

logger = logging.getLogger(__name__)


def get_oc_namespace() -> Namespace:
    """Get the OntoSkills namespace using configured BASE_URI."""
    return Namespace(BASE_URI)


def _add_knowledge_hierarchy(g: Graph, oc: Namespace) -> None:
    """Add the 10-dimensional knowledge hierarchy to the ontology."""

    # Define hierarchy: (parent, [children])
    DIMENSIONS = {
        "KnowledgeNode": ["NormativeRule", "StrategicInsight", "ResilienceTactic",
                          "ExecutionPhysics", "Observability", "SecurityGuardrail",
                          "CognitiveBoundary", "ResourceProfile", "TrustMetric", "LifecycleHook"],
        "NormativeRule": ["Standard", "AntiPattern", "Constraint"],
        "StrategicInsight": ["Heuristic", "DesignPrinciple", "WorkflowStrategy"],
        "ResilienceTactic": ["KnownIssue", "RecoveryTactic"],
        "ExecutionPhysics": ["Idempotency", "SideEffect", "PerformanceProfile"],
        "Observability": ["SuccessIndicator", "TelemetryPattern"],
        "SecurityGuardrail": ["SecurityImplication", "DestructivePotential", "FallbackStrategy"],
        "CognitiveBoundary": ["RequiresHumanClarification", "AssumptionBoundary", "AmbiguityTolerance"],
        "ResourceProfile": ["TokenEconomy", "ComputeCost"],
        "TrustMetric": ["ExecutionDeterminism", "DataProvenance"],
        "LifecycleHook": ["PreFlightCheck", "PostFlightValidation", "RollbackProcedure"],
    }

    for parent_name, child_names in DIMENSIONS.items():
        parent_uri = oc[parent_name]
        for child_name in child_names:
            child_uri = oc[child_name]
            g.add((child_uri, RDF.type, OWL.Class))
            g.add((child_uri, RDFS.subClassOf, parent_uri))
            g.add((child_uri, RDFS.label, Literal(child_name)))


def _add_knowledge_rbox(g: Graph, oc: Namespace) -> None:
    """Add Role Box (RBox) axioms for epistemic properties."""

    # 1. Asymmetry and Irreflexivity
    # A skill imparts knowledge, but knowledge cannot impart a skill.
    g.add((oc.impartsKnowledge, RDF.type, OWL.AsymmetricProperty))
    g.add((oc.impartsKnowledge, RDF.type, OWL.IrreflexiveProperty))

    # 2. Knowledge Inheritance (Property Chain)
    # Define a super-property for inferred knowledge
    g.add((oc.inheritsKnowledge, RDF.type, OWL.ObjectProperty))
    g.add((oc.inheritsKnowledge, RDFS.label, Literal("inherits knowledge")))

    # Base knowledge is a sub-property of inherited knowledge
    g.add((oc.impartsKnowledge, RDFS.subPropertyOf, oc.inheritsKnowledge))

    # CHAIN AXIOM: oc:extends ∘ oc:impartsKnowledge ⊑ oc:inheritsKnowledge
    # If Skill A extends Skill B, and B imparts Knowledge X, then A inherits Knowledge X.
    # Create RDF list for property chain: (extends, impartsKnowledge)
    chain_head = BNode()
    chain_second = BNode()
    g.add((oc.inheritsKnowledge, OWL.propertyChainAxiom, chain_head))
    g.add((chain_head, RDF.first, oc.extends))
    g.add((chain_head, RDF.rest, chain_second))
    g.add((chain_second, RDF.first, oc.impartsKnowledge))
    g.add((chain_second, RDF.rest, RDF.nil))


def _add_extracted_block_classes(g: Graph, oc: Namespace) -> None:
    """Add LLM-extracted content block classes (CodeExample, Table, Flowchart, Template) and their properties."""

    # ========== Content Block Classes ==========

    g.add((oc.CodeExample, RDF.type, OWL.Class))
    g.add((oc.CodeExample, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.CodeExample, RDFS.label, Literal("Code Example")))
    g.add((oc.CodeExample, RDFS.comment, Literal(
        "Inline code block extracted from skill markdown"
    )))

    g.add((oc.Table, RDF.type, OWL.Class))
    g.add((oc.Table, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.Table, RDFS.label, Literal("Table")))
    g.add((oc.Table, RDFS.comment, Literal(
        "Markdown table extracted from skill content"
    )))

    g.add((oc.Flowchart, RDF.type, OWL.Class))
    g.add((oc.Flowchart, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.Flowchart, RDFS.label, Literal("Flowchart")))
    g.add((oc.Flowchart, RDFS.comment, Literal(
        "Graphviz or Mermaid diagram extracted from skill content"
    )))

    g.add((oc.Template, RDF.type, OWL.Class))
    g.add((oc.Template, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.Template, RDFS.label, Literal("Template")))
    g.add((oc.Template, RDFS.comment, Literal(
        "Reusable template with variable placeholders"
    )))

    # ========== Content Block Object Properties ==========

    for prop_name, range_name, label, comment in [
        ("hasCodeExample", "CodeExample", "has code example", "Links a skill to an inline code example"),
        ("hasTable", "Table", "has table", "Links a skill to a markdown table"),
        ("hasFlowchart", "Flowchart", "has flowchart", "Links a skill to a flowchart diagram"),
        ("hasTemplate", "Template", "has template", "Links a skill to a reusable template"),
    ]:
        prop_uri = oc[prop_name]
        range_class = oc[range_name]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.domain, oc.Skill))
        g.add((prop_uri, RDFS.range, range_class))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))

    # ========== CodeExample Datatype Properties ==========

    for prop_name, label, comment in [
        ("codeLanguage", "code language", "Programming language of the code block"),
        ("codeContent", "code content", "Full source code of the inline example"),
        ("codePurpose", "code purpose", "LLM annotation: what this code does"),
        ("codeContext", "code context", "LLM annotation: when to reference this code"),
        ("sourceLocation", "source location", "Line range in original markdown"),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.CodeExample))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))

    # ========== Table Datatype Properties ==========

    for prop_name, label, comment, has_range in [
        ("tableCaption", "table caption", "Caption or title of the table", False),
        ("tableMarkdown", "table markdown", "Original markdown source of the table", False),
        ("tablePurpose", "table purpose", "LLM annotation: what this table represents", False),
        ("rowCount", "row count", "Number of data rows in the table", True),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.Table))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))
        if has_range:
            g.add((prop_uri, RDFS.range, XSD.integer))

    # ========== Flowchart Datatype Properties ==========

    for prop_name, label, comment in [
        ("flowchartSource", "flowchart source", "Original graphviz or mermaid source"),
        ("flowchartType", "flowchart type", "Diagram type: graphviz or mermaid"),
        ("flowchartDescription", "flowchart description", "LLM annotation: what decision flow this represents"),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.Flowchart))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))

    # ========== Template Datatype Properties ==========

    for prop_name, label, comment in [
        ("templateContent", "template content", "Full template source text"),
        ("templateType", "template type", "Kind of template: prompt, output, or boilerplate"),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.Template))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))

    g.add((oc.templateVariables, RDF.type, OWL.DatatypeProperty))
    g.add((oc.templateVariables, RDFS.domain, oc.Template))
    g.add((oc.templateVariables, RDFS.label, Literal("template variables")))
    g.add((oc.templateVariables, RDFS.comment, Literal(
        "Variable placeholder name (repeatable)"
    )))

    # ========== stepOrder for WorkflowStep ==========

    g.add((oc.stepOrder, RDF.type, OWL.DatatypeProperty))
    g.add((oc.stepOrder, RDFS.domain, oc.WorkflowStep))
    g.add((oc.stepOrder, RDFS.range, XSD.integer))
    g.add((oc.stepOrder, RDFS.label, Literal("step order")))
    g.add((oc.stepOrder, RDFS.comment, Literal(
        "Position of this step in a linear procedure (1-based)"
    )))


def _add_content_model_classes(g: Graph, oc: Namespace) -> None:
    """Add content model classes for document structure preservation."""

    # ========== ContentBlock superclass ==========
    g.add((oc.ContentBlock, RDF.type, OWL.Class))
    g.add((oc.ContentBlock, RDFS.label, Literal("Content Block")))
    g.add((oc.ContentBlock, RDFS.comment, Literal(
        "Abstract superclass for all typed content blocks in a document"
    )))

    g.add((oc.blockType, RDF.type, OWL.DatatypeProperty))
    g.add((oc.blockType, RDFS.domain, oc.ContentBlock))
    g.add((oc.blockType, RDFS.range, XSD.string))
    g.add((oc.blockType, RDFS.label, Literal("block type")))
    g.add((oc.blockType, RDFS.comment, Literal(
        "Discriminator string matching the Pydantic block_type literal"
    )))

    # ========== Section (container, not a ContentBlock) ==========
    g.add((oc.Section, RDF.type, OWL.Class))
    g.add((oc.Section, RDFS.label, Literal("Section")))
    g.add((oc.Section, RDFS.comment, Literal(
        "A section of the document, identified by a header"
    )))

    for prop_name, label, comment, has_range in [
        ("sectionTitle", "section title", "Header text of the section", False),
        ("sectionLevel", "section level", "Header level 1-6", True),
        ("sectionOrder", "section order", "Position among sibling sections", True),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.Section))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))
        if has_range:
            g.add((prop_uri, RDFS.range, XSD.integer))

    # ========== Paragraph ==========
    g.add((oc.Paragraph, RDF.type, OWL.Class))
    g.add((oc.Paragraph, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.Paragraph, RDFS.label, Literal("Paragraph")))
    g.add((oc.Paragraph, RDFS.comment, Literal(
        "Free-form text paragraph preserving inline formatting"
    )))

    for prop_name, label, comment, has_range in [
        ("textContent", "text content", "Raw markdown text of the paragraph", False),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.Paragraph))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))
        if has_range:
            g.add((prop_uri, RDFS.range, XSD.integer))

    # contentOrder — no domain restriction because it applies to all ContentBlock subtypes
    # (Paragraph, BulletList, BlockQuote, CodeExample, Table, Flowchart, Template, Workflow,
    # HTMLBlock, FrontmatterBlock). A union domain would be correct but adds OWL complexity
    # for no practical gain; SHACL shapes enforce per-type constraints instead.
    g.add((oc.contentOrder, RDF.type, OWL.DatatypeProperty))
    g.add((oc.contentOrder, RDFS.label, Literal("content order")))
    g.add((oc.contentOrder, RDFS.comment, Literal("Position within parent section")))
    g.add((oc.contentOrder, RDFS.range, XSD.integer))

    # ========== BulletList + BulletItem ==========
    g.add((oc.BulletList, RDF.type, OWL.Class))
    g.add((oc.BulletList, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.BulletList, RDFS.label, Literal("Bullet List")))
    g.add((oc.BulletList, RDFS.comment, Literal(
        "Unordered list of items"
    )))

    g.add((oc.BulletItem, RDF.type, OWL.Class))
    g.add((oc.BulletItem, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.BulletItem, RDFS.label, Literal("Bullet Item")))
    g.add((oc.BulletItem, RDFS.comment, Literal(
        "Single item in a bullet list"
    )))

    for prop_name, label, comment, has_range in [
        ("itemText", "item text", "Text content of the bullet item", False),
        ("itemOrder", "item order", "Position within the bullet list", True),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.BulletItem))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))
        if has_range:
            g.add((prop_uri, RDFS.range, XSD.integer))

    # ========== BlockQuote ==========
    g.add((oc.BlockQuote, RDF.type, OWL.Class))
    g.add((oc.BlockQuote, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.BlockQuote, RDFS.label, Literal("Block Quote")))
    g.add((oc.BlockQuote, RDFS.comment, Literal(
        "Blockquote from markdown, optionally with attribution"
    )))

    for prop_name, label, comment in [
        ("quoteContent", "quote content", "Full text of the blockquote"),
        ("quoteAttribution", "quote attribution", "Optional source/attribution of the quote"),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        g.add((prop_uri, RDFS.domain, oc.BlockQuote))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))

    # ========== Content Model Object Properties ==========
    for prop_name, domain, range_cls, label, comment in [
        ("hasSection", oc.Skill, oc.Section, "has section", "Top-level section of a skill document"),
        ("hasSubsection", oc.Section, oc.Section, "has subsection", "Nested section within a section"),
        ("hasContent", oc.Section, OWL.Thing, "has content", "Content block within a section"),
        ("hasItem", oc.BulletList, oc.BulletItem, "has item", "Item in a bullet list"),
    ]:
        prop_uri = oc[prop_name]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.domain, domain))
        if range_cls is not None:
            g.add((prop_uri, RDFS.range, range_cls))
        g.add((prop_uri, RDFS.label, Literal(label)))
        g.add((prop_uri, RDFS.comment, Literal(comment)))


def _add_content_block_classes(g: Graph, oc: Namespace) -> None:
    """Add additional content block classes: HTMLBlock, FrontmatterBlock, hasChild."""

    # ========== HTMLBlock ==========
    g.add((oc.HTMLBlock, RDF.type, OWL.Class))
    g.add((oc.HTMLBlock, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.HTMLBlock, RDFS.label, Literal("HTML Block")))
    g.add((oc.HTMLBlock, RDFS.comment, Literal(
        "Raw HTML block from markdown"
    )))

    g.add((oc.htmlContent, RDF.type, OWL.DatatypeProperty))
    g.add((oc.htmlContent, RDFS.domain, oc.HTMLBlock))
    g.add((oc.htmlContent, RDFS.label, Literal("html content")))
    g.add((oc.htmlContent, RDFS.comment, Literal("Raw HTML content of the block")))

    # ========== FrontmatterBlock ==========
    g.add((oc.FrontmatterBlock, RDF.type, OWL.Class))
    g.add((oc.FrontmatterBlock, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.FrontmatterBlock, RDFS.label, Literal("Frontmatter Block")))
    g.add((oc.FrontmatterBlock, RDFS.comment, Literal(
        "YAML frontmatter from the document header"
    )))

    g.add((oc.rawYaml, RDF.type, OWL.DatatypeProperty))
    g.add((oc.rawYaml, RDFS.domain, oc.FrontmatterBlock))
    g.add((oc.rawYaml, RDFS.label, Literal("raw yaml")))
    g.add((oc.rawYaml, RDFS.comment, Literal("Raw YAML content of the frontmatter")))

    # ========== hasChild ==========
    g.add((oc.hasChild, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasChild, RDFS.range, OWL.Thing))
    g.add((oc.hasChild, RDFS.label, Literal("has child")))
    g.add((oc.hasChild, RDFS.comment, Literal(
        "Nested content block within a list item or procedure step"
    )))


def create_core_ontology(output_path: Optional[Path] = None) -> Graph:
    """
    Create the core OntoSkills ontology (TBox) with state transition system.

    Generates core.ttl containing:
    - Core classes (Skill, State, Attempt, ExecutionPayload)
    - State transition properties (requiresState, yieldsState, handlesFailure, hasStatus)
    - Execution payload properties (hasPayload, executor, code, timeout)
    - LLM attestation (generatedBy)
    - Predefined core and failure states

    Args:
        output_path: Path where core.ttl will be saved (default: OUTPUT_DIR/core.ttl)

    Returns:
        Graph with core ontology definitions
    """
    if output_path is None:
        output_base = Path(OUTPUT_DIR).resolve()
        output_path = output_base / CORE_ONTOLOGY_FILENAME

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
    g.add((base_uri, DCTERMS.title, Literal("OntoSkills Core Ontology")))
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

    # ========== Knowledge Node Foundation ==========

    # oc:KnowledgeNode - Base class for epistemic knowledge
    g.add((oc.KnowledgeNode, RDF.type, OWL.Class))
    g.add((oc.KnowledgeNode, RDFS.label, Literal("Knowledge Node")))
    g.add((oc.KnowledgeNode, RDFS.comment, Literal(
        "Epistemic knowledge imparted by a skill to an agent"
    )))

    # oc:impartsKnowledge (ObjectProperty) - Skill → KnowledgeNode
    g.add((oc.impartsKnowledge, RDF.type, OWL.ObjectProperty))
    g.add((oc.impartsKnowledge, RDFS.domain, oc.Skill))
    g.add((oc.impartsKnowledge, RDFS.range, oc.KnowledgeNode))
    g.add((oc.impartsKnowledge, RDFS.label, Literal("imparts knowledge")))
    g.add((oc.impartsKnowledge, RDFS.comment, Literal(
        "Links a skill to epistemic knowledge it imparts to the agent"
    )))

    # oc:directiveContent (DatatypeProperty)
    g.add((oc.directiveContent, RDF.type, OWL.DatatypeProperty))
    g.add((oc.directiveContent, RDFS.domain, oc.KnowledgeNode))
    g.add((oc.directiveContent, RDFS.label, Literal("directive content")))
    g.add((oc.directiveContent, RDFS.comment, Literal(
        "The actual rule/guideline text"
    )))

    # oc:appliesToContext (DatatypeProperty)
    g.add((oc.appliesToContext, RDF.type, OWL.DatatypeProperty))
    g.add((oc.appliesToContext, RDFS.domain, oc.KnowledgeNode))
    g.add((oc.appliesToContext, RDFS.label, Literal("applies to context")))
    g.add((oc.appliesToContext, RDFS.comment, Literal(
        "When this rule applies"
    )))

    # oc:hasRationale (DatatypeProperty)
    g.add((oc.hasRationale, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasRationale, RDFS.domain, oc.KnowledgeNode))
    g.add((oc.hasRationale, RDFS.label, Literal("has rationale")))
    g.add((oc.hasRationale, RDFS.comment, Literal(
        "Why this rule exists"
    )))

    # oc:severityLevel (DatatypeProperty)
    g.add((oc.severityLevel, RDF.type, OWL.DatatypeProperty))
    g.add((oc.severityLevel, RDFS.domain, oc.KnowledgeNode))
    g.add((oc.severityLevel, RDFS.label, Literal("severity level")))
    g.add((oc.severityLevel, RDFS.comment, Literal(
        "Must be one of: CRITICAL, HIGH, MEDIUM, LOW"
    )))

    # Add the 10-dimensional hierarchy
    _add_knowledge_hierarchy(g, oc)

    # Add RBox axioms for knowledge inheritance
    _add_knowledge_rbox(g, oc)

    # Add LLM-extracted content block classes and properties
    _add_extracted_block_classes(g, oc)

    # Add content model classes for document structure preservation
    _add_content_model_classes(g, oc)

    # Add additional content block classes (HTMLBlock, FrontmatterBlock, hasChild)
    _add_content_block_classes(g, oc)

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

    # ========== Optional Metadata Properties ==========

    # oc:hasCategory (DatatypeProperty)
    g.add((oc.hasCategory, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasCategory, RDFS.domain, oc.Skill))
    g.add((oc.hasCategory, RDFS.range, XSD.string))
    g.add((oc.hasCategory, RDFS.label, Literal("has category")))
    g.add((oc.hasCategory, RDFS.comment, Literal(
        "Skill category (e.g., automation, document, marketing)"
    )))

    # oc:hasVersion (DatatypeProperty)
    g.add((oc.hasVersion, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasVersion, RDFS.domain, oc.Skill))
    g.add((oc.hasVersion, RDFS.range, XSD.string))
    g.add((oc.hasVersion, RDFS.label, Literal("has version")))
    g.add((oc.hasVersion, RDFS.comment, Literal(
        "Skill version string"
    )))

    # oc:hasLicense (DatatypeProperty)
    g.add((oc.hasLicense, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasLicense, RDFS.domain, oc.Skill))
    g.add((oc.hasLicense, RDFS.range, XSD.string))
    g.add((oc.hasLicense, RDFS.label, Literal("has license")))
    g.add((oc.hasLicense, RDFS.comment, Literal(
        "License identifier (e.g., MIT, Apache-2.0)"
    )))

    # oc:hasAuthor (DatatypeProperty)
    g.add((oc.hasAuthor, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasAuthor, RDFS.domain, oc.Skill))
    g.add((oc.hasAuthor, RDFS.range, XSD.string))
    g.add((oc.hasAuthor, RDFS.label, Literal("has author")))
    g.add((oc.hasAuthor, RDFS.comment, Literal(
        "Author/source name (e.g., anthropics, claude-office-skills)"
    )))

    # oc:hasPackageName (DatatypeProperty)
    g.add((oc.hasPackageName, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasPackageName, RDFS.domain, oc.Skill))
    g.add((oc.hasPackageName, RDFS.range, XSD.string))
    g.add((oc.hasPackageName, RDFS.label, Literal("has package name")))
    g.add((oc.hasPackageName, RDFS.comment, Literal(
        "Package ID this skill belongs to"
    )))

    # oc:isUserInvocable (DatatypeProperty)
    g.add((oc.isUserInvocable, RDF.type, OWL.DatatypeProperty))
    g.add((oc.isUserInvocable, RDFS.domain, oc.Skill))
    g.add((oc.isUserInvocable, RDFS.range, XSD.boolean))
    g.add((oc.isUserInvocable, RDFS.label, Literal("is user invocable")))
    g.add((oc.isUserInvocable, RDFS.comment, Literal(
        "Whether the skill is directly invocable by users"
    )))

    # oc:hasArgumentHint (DatatypeProperty)
    g.add((oc.hasArgumentHint, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasArgumentHint, RDFS.domain, oc.Skill))
    g.add((oc.hasArgumentHint, RDFS.range, XSD.string))
    g.add((oc.hasArgumentHint, RDFS.label, Literal("has argument hint")))
    g.add((oc.hasArgumentHint, RDFS.comment, Literal(
        "Argument hint string (e.g., repo-url, query)"
    )))

    # oc:hasAllowedTool (DatatypeProperty) — repeatable
    g.add((oc.hasAllowedTool, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasAllowedTool, RDFS.domain, oc.Skill))
    g.add((oc.hasAllowedTool, RDFS.range, XSD.string))
    g.add((oc.hasAllowedTool, RDFS.label, Literal("has allowed tool")))
    g.add((oc.hasAllowedTool, RDFS.comment, Literal(
        "Allowed tool (repeatable — one triple per tool)"
    )))

    # oc:hasAlias (DatatypeProperty) — repeatable
    g.add((oc.hasAlias, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasAlias, RDFS.domain, oc.Skill))
    g.add((oc.hasAlias, RDFS.range, XSD.string))
    g.add((oc.hasAlias, RDFS.label, Literal("has alias")))
    g.add((oc.hasAlias, RDFS.comment, Literal(
        "Alias name (repeatable — one triple per alias)"
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

    # oc:dependsOn (ObjectProperty) — DEPRECATED, use oc:dependsOnSkill
    g.add((oc.dependsOn, RDF.type, OWL.ObjectProperty))
    g.add((oc.dependsOn, RDF.type, OWL.AsymmetricProperty))
    g.add((oc.dependsOn, RDFS.domain, oc.Skill))
    g.add((oc.dependsOn, RDFS.range, oc.Skill))
    g.add((oc.dependsOn, RDFS.label, Literal("depends on")))
    g.add((oc.dependsOn, RDFS.comment, Literal(
        "DEPRECATED: use oc:dependsOnSkill instead. Legacy skill-to-skill dependency."
    )))
    g.add((oc.dependsOn, OWL.deprecated, Literal(True)))
    g.add((oc.dependsOn, OWL.inverseOf, oc.enables))

    # oc:dependsOnSkill (ObjectProperty) — unambiguous skill-to-skill dependency
    g.add((oc.dependsOnSkill, RDF.type, OWL.ObjectProperty))
    g.add((oc.dependsOnSkill, RDF.type, OWL.AsymmetricProperty))
    g.add((oc.dependsOnSkill, RDFS.domain, oc.Skill))
    g.add((oc.dependsOnSkill, RDFS.range, oc.Skill))
    g.add((oc.dependsOnSkill, RDFS.label, Literal("depends on skill")))
    g.add((oc.dependsOnSkill, RDFS.comment, Literal(
        "Declares a dependency on another skill (skill-to-skill prerequisite)"
    )))
    g.add((oc.dependsOnSkill, OWL.inverseOf, oc.enablesSkill))

    # oc:enables (ObjectProperty) - inverse of dependsOn (legacy)
    g.add((oc.enables, RDF.type, OWL.ObjectProperty))
    g.add((oc.enables, RDFS.domain, oc.Skill))
    g.add((oc.enables, RDFS.range, oc.Skill))
    g.add((oc.enables, RDFS.label, Literal("enables")))
    g.add((oc.enables, RDFS.comment, Literal(
        "Skill enables another skill (inverse of dependsOn)"
    )))

    # oc:enablesSkill (ObjectProperty) - inverse of dependsOnSkill
    g.add((oc.enablesSkill, RDF.type, OWL.ObjectProperty))
    g.add((oc.enablesSkill, RDFS.domain, oc.Skill))
    g.add((oc.enablesSkill, RDFS.range, oc.Skill))
    g.add((oc.enablesSkill, RDFS.label, Literal("enables skill")))
    g.add((oc.enablesSkill, RDFS.comment, Literal(
        "Skill enables another skill (inverse of dependsOnSkill)"
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

    # ========== Phase 2: Progressive Disclosure Classes ==========

    # oc:ReferenceFile - Reference file for progressive disclosure
    g.add((oc.ReferenceFile, RDF.type, OWL.Class))
    g.add((oc.ReferenceFile, RDFS.label, Literal("Reference File")))
    g.add((oc.ReferenceFile, RDFS.comment, Literal(
        "A reference file for progressive disclosure (e.g., API docs, examples)"
    )))

    # oc:hasReferenceFile (ObjectProperty)
    g.add((oc.hasReferenceFile, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasReferenceFile, RDFS.domain, oc.Skill))
    g.add((oc.hasReferenceFile, RDFS.range, oc.ReferenceFile))
    g.add((oc.hasReferenceFile, RDFS.label, Literal("has reference file")))
    g.add((oc.hasReferenceFile, RDFS.comment, Literal(
        "Links a skill to a reference file for progressive disclosure"
    )))

    # oc:purpose (DatatypeProperty)
    g.add((oc.purpose, RDF.type, OWL.DatatypeProperty))
    g.add((oc.purpose, RDFS.domain, oc.ReferenceFile))
    g.add((oc.purpose, RDFS.label, Literal("purpose")))
    g.add((oc.purpose, RDFS.comment, Literal(
        "Purpose of a reference file (api-reference, examples, guide, domain-specific, other)"
    )))

    # ========== Phase 2: File Properties ==========
    # Create union domain class for file properties (ReferenceFile OR ExecutableScript)
    # Use named URI for deterministic serialization (avoid BNode churn in diffs)
    file_domain = oc.FileResource
    g.add((file_domain, RDF.type, OWL.Class))
    file_union_list = oc.FileResourceUnion
    Collection(g, file_union_list, [oc.ReferenceFile, oc.ExecutableScript])
    g.add((file_domain, OWL.unionOf, file_union_list))

    # oc:filePath - Relative path from skill directory
    g.add((oc.filePath, RDF.type, OWL.DatatypeProperty))
    g.add((oc.filePath, RDFS.label, Literal("file path")))
    g.add((oc.filePath, RDFS.comment, Literal(
        "Relative path from skill directory"
    )))
    g.add((oc.filePath, RDFS.domain, file_domain))
    g.add((oc.filePath, RDFS.range, XSD.string))

    # oc:fileHash - SHA-256 hash of file content
    g.add((oc.fileHash, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileHash, RDFS.label, Literal("file hash")))
    g.add((oc.fileHash, RDFS.comment, Literal(
        "SHA-256 hash of file content"
    )))
    g.add((oc.fileHash, RDFS.domain, file_domain))
    g.add((oc.fileHash, RDFS.range, XSD.string))

    # oc:fileSize - File size in bytes
    g.add((oc.fileSize, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileSize, RDFS.label, Literal("file size")))
    g.add((oc.fileSize, RDFS.comment, Literal(
        "File size in bytes"
    )))
    g.add((oc.fileSize, RDFS.domain, file_domain))
    g.add((oc.fileSize, RDFS.range, XSD.integer))

    # oc:fileMimeType - MIME type of the file
    g.add((oc.fileMimeType, RDF.type, OWL.DatatypeProperty))
    g.add((oc.fileMimeType, RDFS.label, Literal("file MIME type")))
    g.add((oc.fileMimeType, RDFS.comment, Literal(
        "MIME type of the file"
    )))
    g.add((oc.fileMimeType, RDFS.domain, file_domain))
    g.add((oc.fileMimeType, RDFS.range, XSD.string))

    # ========== Phase 2: Executable Script Classes ==========

    # oc:ExecutableScript - Executable script associated with skill
    g.add((oc.ExecutableScript, RDF.type, OWL.Class))
    g.add((oc.ExecutableScript, RDFS.label, Literal("Executable Script")))
    g.add((oc.ExecutableScript, RDFS.comment, Literal(
        "An executable script associated with a skill"
    )))

    # oc:hasExecutableScript (ObjectProperty)
    g.add((oc.hasExecutableScript, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasExecutableScript, RDFS.domain, oc.Skill))
    g.add((oc.hasExecutableScript, RDFS.range, oc.ExecutableScript))
    g.add((oc.hasExecutableScript, RDFS.label, Literal("has executable script")))
    g.add((oc.hasExecutableScript, RDFS.comment, Literal(
        "Links a skill to an executable script"
    )))

    # oc:requirementType (DatatypeProperty)
    g.add((oc.requirementType, RDF.type, OWL.DatatypeProperty))
    g.add((oc.requirementType, RDFS.domain, oc.Requirement))
    g.add((oc.requirementType, RDFS.label, Literal("requirement type")))
    g.add((oc.requirementType, RDFS.comment, Literal(
        "Type of requirement (Tool, EnvVar, Hardware, API, Knowledge)"
    )))

    # ========== Phase 2: Executable Script Properties ==========

    # oc:scriptExecutor - Executor for script (python, bash, node)
    g.add((oc.scriptExecutor, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptExecutor, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptExecutor, RDFS.label, Literal("script executor")))
    g.add((oc.scriptExecutor, RDFS.comment, Literal(
        "Executor for the script (python, bash, node, etc.)"
    )))
    g.add((oc.scriptExecutor, RDFS.range, XSD.string))

    # oc:scriptIntent - Whether script should be executed or read-only
    g.add((oc.scriptIntent, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptIntent, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptIntent, RDFS.label, Literal("script intent")))
    g.add((oc.scriptIntent, RDFS.comment, Literal(
        "Whether script should be executed or is read-only"
    )))
    g.add((oc.scriptIntent, RDFS.range, XSD.string))

    # oc:scriptCommand - Command template for executing the script
    g.add((oc.scriptCommand, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptCommand, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptCommand, RDFS.label, Literal("script command")))
    g.add((oc.scriptCommand, RDFS.comment, Literal(
        "Command template for executing the script"
    )))
    g.add((oc.scriptCommand, RDFS.range, XSD.string))

    # oc:scriptOutput - Description of script output
    g.add((oc.scriptOutput, RDF.type, OWL.DatatypeProperty))
    g.add((oc.scriptOutput, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptOutput, RDFS.label, Literal("script output")))
    g.add((oc.scriptOutput, RDFS.comment, Literal(
        "Description of what the script produces"
    )))
    g.add((oc.scriptOutput, RDFS.range, XSD.string))

    # oc:scriptHasRequirement - Links script to its requirements
    g.add((oc.scriptHasRequirement, RDF.type, OWL.ObjectProperty))
    g.add((oc.scriptHasRequirement, RDFS.domain, oc.ExecutableScript))
    g.add((oc.scriptHasRequirement, RDFS.range, oc.Requirement))
    g.add((oc.scriptHasRequirement, RDFS.label, Literal("script has requirement")))
    g.add((oc.scriptHasRequirement, RDFS.comment, Literal(
        "Links an executable script to its requirements"
    )))

    # ========== Phase 2: Workflow Classes ==========

    # oc:Workflow - Sequential workflow with dependencies
    g.add((oc.Workflow, RDF.type, OWL.Class))
    g.add((oc.Workflow, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.Workflow, RDFS.label, Literal("Workflow")))
    g.add((oc.Workflow, RDFS.comment, Literal(
        "A sequential workflow with dependencies between steps"
    )))

    # oc:WorkflowStep - Single step in a workflow
    g.add((oc.WorkflowStep, RDF.type, OWL.Class))
    g.add((oc.WorkflowStep, RDFS.subClassOf, oc.ContentBlock))
    g.add((oc.WorkflowStep, RDFS.label, Literal("Workflow Step")))
    g.add((oc.WorkflowStep, RDFS.comment, Literal(
        "A single step in a workflow with optional dependencies"
    )))

    # oc:hasWorkflow (ObjectProperty)
    g.add((oc.hasWorkflow, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasWorkflow, RDFS.domain, oc.Skill))
    g.add((oc.hasWorkflow, RDFS.range, oc.Workflow))
    g.add((oc.hasWorkflow, RDFS.label, Literal("has workflow")))
    g.add((oc.hasWorkflow, RDFS.comment, Literal(
        "Links a skill to a workflow"
    )))

    # oc:workflowId (DatatypeProperty)
    g.add((oc.workflowId, RDF.type, OWL.DatatypeProperty))
    g.add((oc.workflowId, RDFS.domain, oc.Workflow))
    g.add((oc.workflowId, RDFS.label, Literal("workflow ID")))
    g.add((oc.workflowId, RDFS.comment, Literal(
        "Unique identifier for a workflow"
    )))

    # oc:workflowName (DatatypeProperty)
    g.add((oc.workflowName, RDF.type, OWL.DatatypeProperty))
    g.add((oc.workflowName, RDFS.domain, oc.Workflow))
    g.add((oc.workflowName, RDFS.label, Literal("workflow name")))
    g.add((oc.workflowName, RDFS.comment, Literal(
        "Human-readable name for a workflow"
    )))

    # oc:hasStep (ObjectProperty)
    g.add((oc.hasStep, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasStep, RDFS.domain, oc.Workflow))
    g.add((oc.hasStep, RDFS.range, oc.WorkflowStep))
    g.add((oc.hasStep, RDFS.label, Literal("has step")))
    g.add((oc.hasStep, RDFS.comment, Literal(
        "Links a workflow to its steps"
    )))

    # oc:stepId (DatatypeProperty)
    g.add((oc.stepId, RDF.type, OWL.DatatypeProperty))
    g.add((oc.stepId, RDFS.domain, oc.WorkflowStep))
    g.add((oc.stepId, RDFS.label, Literal("step ID")))
    g.add((oc.stepId, RDFS.comment, Literal(
        "Unique identifier for a workflow step"
    )))

    # oc:expectedOutcome (DatatypeProperty)
    g.add((oc.expectedOutcome, RDF.type, OWL.DatatypeProperty))
    g.add((oc.expectedOutcome, RDFS.domain, oc.WorkflowStep))
    g.add((oc.expectedOutcome, RDFS.label, Literal("expected outcome")))
    g.add((oc.expectedOutcome, RDFS.comment, Literal(
        "Expected outcome of a workflow step"
    )))

    # ========== Phase 2: Workflow Step Dependencies ==========

    # oc:stepDependsOn - Dependency between workflow steps (ObjectProperty!)
    g.add((oc.stepDependsOn, RDF.type, OWL.ObjectProperty))
    g.add((oc.stepDependsOn, RDFS.domain, oc.WorkflowStep))
    g.add((oc.stepDependsOn, RDFS.range, oc.WorkflowStep))
    g.add((oc.stepDependsOn, RDFS.label, Literal("step depends on")))
    g.add((oc.stepDependsOn, RDFS.comment, Literal(
        "Indicates that one workflow step depends on another step"
    )))

    # ========== Phase 2: Example Classes ==========

    # oc:Example - Input/output example for pattern matching
    g.add((oc.Example, RDF.type, OWL.Class))
    g.add((oc.Example, RDFS.label, Literal("Example")))
    g.add((oc.Example, RDFS.comment, Literal(
        "An input/output example for pattern matching"
    )))

    # oc:hasExample (ObjectProperty)
    g.add((oc.hasExample, RDF.type, OWL.ObjectProperty))
    g.add((oc.hasExample, RDFS.domain, oc.Skill))
    g.add((oc.hasExample, RDFS.range, oc.Example))
    g.add((oc.hasExample, RDFS.label, Literal("has example")))
    g.add((oc.hasExample, RDFS.comment, Literal(
        "Links a skill to an input/output example"
    )))

    # oc:exampleName (DatatypeProperty)
    g.add((oc.exampleName, RDF.type, OWL.DatatypeProperty))
    g.add((oc.exampleName, RDFS.domain, oc.Example))
    g.add((oc.exampleName, RDFS.label, Literal("example name")))
    g.add((oc.exampleName, RDFS.comment, Literal(
        "Name of an example"
    )))

    # oc:inputDescription (DatatypeProperty)
    g.add((oc.inputDescription, RDF.type, OWL.DatatypeProperty))
    g.add((oc.inputDescription, RDFS.domain, oc.Example))
    g.add((oc.inputDescription, RDFS.label, Literal("input description")))
    g.add((oc.inputDescription, RDFS.comment, Literal(
        "Description of input for an example"
    )))

    # oc:outputExample (DatatypeProperty)
    g.add((oc.outputExample, RDF.type, OWL.DatatypeProperty))
    g.add((oc.outputExample, RDFS.domain, oc.Example))
    g.add((oc.outputExample, RDFS.label, Literal("output example")))
    g.add((oc.outputExample, RDFS.comment, Literal(
        "Example output"
    )))

    # oc:hasTag (DatatypeProperty)
    g.add((oc.hasTag, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasTag, RDFS.domain, oc.Example))
    g.add((oc.hasTag, RDFS.label, Literal("has tag")))
    g.add((oc.hasTag, RDFS.comment, Literal(
        "Tag for categorizing examples"
    )))

    # ========== Phase 2: Frontmatter Properties ==========

    # oc:hasName (DatatypeProperty)
    g.add((oc.hasName, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasName, RDFS.domain, oc.Skill))
    g.add((oc.hasName, RDFS.label, Literal("has name")))
    g.add((oc.hasName, RDFS.comment, Literal(
        "Name from frontmatter"
    )))

    # oc:hasDescription (DatatypeProperty)
    g.add((oc.hasDescription, RDF.type, OWL.DatatypeProperty))
    g.add((oc.hasDescription, RDFS.domain, oc.Skill))
    g.add((oc.hasDescription, RDFS.label, Literal("has description")))
    g.add((oc.hasDescription, RDFS.comment, Literal(
        "Description from frontmatter"
    )))

    # ========== Phase 2: Generic Requirement Class ==========

    # oc:Requirement - Generic requirement
    g.add((oc.Requirement, RDF.type, OWL.Class))
    g.add((oc.Requirement, RDFS.label, Literal("Requirement")))
    g.add((oc.Requirement, RDFS.comment, Literal(
        "A generic requirement (tool, environment variable, etc.)"
    )))

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(output_path, format="turtle")
    logger.info(f"Created core ontology at {output_path} with {len(g)} triples")

    return g
