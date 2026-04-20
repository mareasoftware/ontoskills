"""
RDF Serialization Module.

Handles serialization of skills to RDF/Turtle format.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from rdflib import Graph, Namespace, RDF, OWL, Literal, URIRef, BNode
from rdflib.namespace import DCTERMS, SKOS, PROV, XSD

from compiler.schemas import ExtractedSkill, FileInfo, ContentExtraction
from compiler.exceptions import OntologyValidationError
from compiler.config import BASE_URI, CORE_ONTOLOGY_FILENAME, CORE_ONTOLOGY_URL, OUTPUT_DIR, resolve_ontology_root
from compiler.core_ontology import get_oc_namespace
from compiler.extractor import generate_skill_id
from compiler.validator import validate_and_raise

logger = logging.getLogger(__name__)


def skill_uri_for_id(skill_id: str, qualified_id: str | None = None) -> URIRef:
    """
    Build a stable skill URI from identifiers.

    Args:
        skill_id: Short/local skill ID (e.g., "planning")
        qualified_id: Optional qualified ID including package path
                     (e.g., "marea/office/planning"). If provided, used for URI
                     to avoid collisions across packages.

    The URI is based on the qualified_id (if provided) or skill_id,
    slugified to be QName-compatible (lowercase, alphanumeric with underscores).
    The short skill_id is always stored in dcterms:identifier.
    """
    oc = get_oc_namespace()
    # Use qualified_id for URI if provided, otherwise use skill_id
    id_for_uri = qualified_id or skill_id

    # Defensive slugification for QName compatibility:
    # - lowercase
    # - replace / and @ (scoped packages) with _
    # - replace any non-alphanumeric (except _) with _
    # - collapse consecutive underscores
    import re
    slug = id_for_uri.lower()
    slug = re.sub(r'[/@]', '_', slug)  # slashes and scoped package prefix
    slug = re.sub(r'[^a-z0-9_]', '_', slug)  # any other non-alphanumeric
    slug = re.sub(r'_+', '_', slug)  # collapse consecutive underscores
    slug = slug.strip('_')

    return oc[f"skill_{slug}"]


def skill_uri_for_skill(skill: ExtractedSkill, qualified_id: str | None = None) -> URIRef:
    """Build the stable URI for a skill model.

    Args:
        skill: The extracted skill
        qualified_id: Optional qualified ID for URI (prevents collisions)
    """
    return skill_uri_for_id(skill.id, qualified_id)


def relation_uri_for_value(value: str) -> URIRef:
    """Convert a skill relation value into a skill URI reference."""
    raw = value.strip()
    oc = get_oc_namespace()
    if raw.startswith("http://") or raw.startswith("https://"):
        return URIRef(raw)
    if raw.startswith("oc:"):
        return oc[raw.removeprefix("oc:")]
    return skill_uri_for_id(raw)


def _serialize_section_tree(
    graph: Graph,
    skill_uri,
    content_extraction,
    make_bnode,
) -> None:
    """Serialize the DocGraph section tree to RDF triples."""
    oc = get_oc_namespace()

    def _serialize_section(section, parent_uri, is_subsection=False):
        section_node = make_bnode("section", f"{section.level}:{section.order}:{section.title}")

        if is_subsection:
            graph.add((parent_uri, oc.hasSubsection, section_node))
        else:
            graph.add((parent_uri, oc.hasSection, section_node))

        graph.add((section_node, RDF.type, oc.Section))
        graph.add((section_node, oc.sectionTitle, Literal(section.title)))
        graph.add((section_node, oc.sectionLevel, Literal(section.level)))
        graph.add((section_node, oc.sectionOrder, Literal(section.order)))

        for block in section.content:
            content_node = _serialize_content_block(graph, block, make_bnode)
            if content_node:
                graph.add((section_node, oc.hasContent, content_node))

        for sub in section.subsections:
            _serialize_section(sub, section_node, is_subsection=True)

    def _serialize_content_block(graph, block, make_bnode):
        """Serialize a single content block, return its BNode."""
        if block.block_type == "paragraph":
            node = make_bnode("para", f"{block.content_order}:{hash(block.text_content) & 0xFFFF}")
            graph.add((node, RDF.type, oc.Paragraph))
            graph.add((node, oc.textContent, Literal(block.text_content)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "bullet_list":
            node = make_bnode("blist", f"{block.content_order}:{len(block.items)}")
            graph.add((node, RDF.type, oc.BulletList))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            for item in block.items:
                item_node = make_bnode("bitem", f"{item.order}:{hash(item.text) & 0xFFFF}")
                graph.add((node, oc.hasItem, item_node))
                graph.add((item_node, RDF.type, oc.BulletItem))
                graph.add((item_node, oc.itemText, Literal(item.text)))
                graph.add((item_node, oc.itemOrder, Literal(item.order)))
                for child in item.children:
                    child_node = _serialize_content_block(graph, child, make_bnode)
                    if child_node:
                        graph.add((item_node, oc.hasChild, child_node))
            return node

        elif block.block_type == "blockquote":
            node = make_bnode("bquote", f"{block.content_order}:{hash(block.content) & 0xFFFF}")
            graph.add((node, RDF.type, oc.BlockQuote))
            graph.add((node, oc.quoteContent, Literal(block.content)))
            if block.attribution:
                graph.add((node, oc.quoteAttribution, Literal(block.attribution)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "html_block":
            node = make_bnode("html", f"{block.content_order}:{hash(block.content) & 0xFFFF}")
            graph.add((node, RDF.type, oc.HTMLBlock))
            graph.add((node, oc.htmlContent, Literal(block.content)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "frontmatter":
            node = make_bnode("fm", f"{block.content_order}:{hash(block.raw_yaml) & 0xFFFF}")
            graph.add((node, RDF.type, oc.FrontmatterBlock))
            graph.add((node, oc.rawYaml, Literal(block.raw_yaml)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "code_block":
            node = make_bnode("code", f"{block.content_order}:{block.language}")
            graph.add((node, RDF.type, oc.CodeExample))
            graph.add((node, oc.codeLanguage, Literal(block.language)))
            graph.add((node, oc.codeContent, Literal(block.content)))
            graph.add((node, oc.sourceLocation,
                       Literal(f"lines {block.source_line_start}-{block.source_line_end}")))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "table":
            node = make_bnode("table", f"{block.content_order}:{block.caption or 'untitled'}")
            graph.add((node, RDF.type, oc.Table))
            graph.add((node, oc.tableMarkdown, Literal(block.markdown_source)))
            if block.caption:
                graph.add((node, oc.tableCaption, Literal(block.caption)))
            graph.add((node, oc.rowCount, Literal(block.row_count)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "flowchart":
            node = make_bnode("flow", f"{block.content_order}:{block.chart_type}")
            graph.add((node, RDF.type, oc.Flowchart))
            graph.add((node, oc.flowchartSource, Literal(block.source)))
            graph.add((node, oc.flowchartType, Literal(block.chart_type)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "template":
            node = make_bnode("tmpl", f"{block.content_order}:{','.join(block.detected_variables)}")
            graph.add((node, RDF.type, oc.Template))
            graph.add((node, oc.templateContent, Literal(block.content)))
            for var in block.detected_variables:
                graph.add((node, oc.templateVariables, Literal(var)))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            return node

        elif block.block_type == "ordered_procedure":
            node = make_bnode("proc", f"{block.content_order}")
            graph.add((node, RDF.type, oc.Workflow))
            graph.add((node, oc.workflowId, Literal(f"procedure_{block.content_order}")))
            graph.add((node, oc.workflowName, Literal("Ordered Procedure")))
            graph.add((node, oc.contentOrder, Literal(block.content_order)))
            for step in block.items:
                step_node = make_bnode("step", f"{block.content_order}_{step.position}")
                graph.add((node, oc.hasStep, step_node))
                graph.add((step_node, RDF.type, oc.WorkflowStep))
                graph.add((step_node, oc.stepId, Literal(f"step_{step.position}")))
                graph.add((step_node, DCTERMS.description, Literal(step.text)))
                graph.add((step_node, oc.stepOrder, Literal(step.position)))
                for child in step.children:
                    child_node = _serialize_content_block(graph, child, make_bnode)
                    if child_node:
                        graph.add((step_node, oc.hasChild, child_node))
            return node

        return None

    for section in content_extraction.sections:
        _serialize_section(section, skill_uri, is_subsection=False)


def serialize_skill(
    graph: Graph,
    skill: ExtractedSkill,
    qualified_id: str | None = None,
    extends_parent: str | None = None,
    extends_parent_qualified: str | None = None,
    content_extraction: "ContentExtraction | None" = None,
) -> None:
    """
    Serialize a skill to RDF triples in the graph.

    Args:
        graph: RDF graph to add triples to
        skill: ExtractedSkill to serialize
        qualified_id: Optional qualified ID for URI (prevents collisions across packages)
        extends_parent: Optional parent skill short ID to inject as extends relationship
        extends_parent_qualified: Optional parent qualified ID for extends URI
        content_extraction: Optional ContentExtraction with code blocks, tables, flowcharts, templates
    """
    oc = get_oc_namespace()

    # Create stable skill URI from qualified_id if provided, otherwise from skill.id
    skill_uri = skill_uri_for_skill(skill, qualified_id)

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
    # Use oc:dependsOnSkill for skill-to-skill dependencies (OntoCore refactoring)
    # Skip self-references to prevent circular deps
    for dep in skill.depends_on:
        if dep == skill.id:
            continue
        graph.add((skill_uri, oc.dependsOnSkill, relation_uri_for_value(dep)))

    # Inject deterministic extends if provided (sub-skills)
    parent_uri = None
    if extends_parent:
        # Use qualified ID for parent URI if provided
        parent_uri = skill_uri_for_id(extends_parent, extends_parent_qualified)
        graph.add((skill_uri, oc.extends, parent_uri))

    # Also include any LLM-extracted extends (for non-sub-skill cases)
    for ext in skill.extends:
        ext_uri = relation_uri_for_value(ext)
        # Avoid duplicate if already injected (compare against actual parent_uri)
        if not parent_uri or str(ext_uri) != str(parent_uri):
            graph.add((skill_uri, oc.extends, ext_uri))

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

    # LLM attestation removed — migrated to system/index.json per-skill metadata

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

        # Add the knowledge node type as class (SHACL requires explicit KnowledgeNode type)
        graph.add((kn_uri, RDF.type, oc[kn.node_type]))
        graph.add((kn_uri, RDF.type, oc.KnowledgeNode))
        graph.add((kn_uri, oc.directiveContent, Literal(kn.directive_content)))
        graph.add((kn_uri, oc.appliesToContext, Literal(kn.applies_to_context)))
        graph.add((kn_uri, oc.hasRationale, Literal(kn.has_rationale)))

        if kn.severity_level:
            graph.add((kn_uri, oc.severityLevel, Literal(kn.severity_level.value)))

        # Link skill to knowledge node
        graph.add((skill_uri, oc.impartsKnowledge, kn_uri))

    # === Phase 2 Components ===

    # Pre-index files by relative_path for O(1) lookup (instead of O(N*M))
    files_index: dict[str, FileInfo] = {}
    for f in getattr(skill, 'files', []):
        files_index[f.relative_path] = f

    # Helper to create deterministic blank node IDs
    def make_bnode(component_type: str, identifier: str) -> BNode:
        """Create a deterministic blank node ID from a fixed-length hash.

        Uses SHA-256 of {skill.hash}:{component_type}:{identifier} to ensure:
        - Fixed length (16 hex chars)
        - No collisions from identifier normalization
        - No TTL bloat from long identifiers
        """
        raw = f"{skill.hash}:{component_type}:{identifier}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return BNode(f"ref_{digest}")

    # Reference Files (progressive disclosure)
    for ref in getattr(skill, 'reference_files', []):
        ref_node = make_bnode("ref", ref.relative_path)
        graph.add((skill_uri, oc.hasReferenceFile, ref_node))
        graph.add((ref_node, RDF.type, oc.ReferenceFile))
        graph.add((ref_node, oc.filePath, Literal(ref.relative_path)))
        graph.add((ref_node, oc.purpose, Literal(ref.purpose)))

        # O(1) lookup using pre-indexed files
        if ref.relative_path in files_index:
            f = files_index[ref.relative_path]
            graph.add((ref_node, oc.fileHash, Literal(f.content_hash)))
            graph.add((ref_node, oc.fileSize, Literal(f.file_size)))
            graph.add((ref_node, oc.fileMimeType, Literal(f.mime_type)))

    # Executable Scripts
    for script in getattr(skill, 'executable_scripts', []):
        script_node = make_bnode("script", script.relative_path)
        graph.add((skill_uri, oc.hasExecutableScript, script_node))
        graph.add((script_node, RDF.type, oc.ExecutableScript))
        graph.add((script_node, oc.filePath, Literal(script.relative_path)))
        graph.add((script_node, oc.scriptExecutor, Literal(script.executor)))
        graph.add((script_node, oc.scriptIntent, Literal(script.execution_intent)))

        if script.command_template:
            graph.add((script_node, oc.scriptCommand, Literal(script.command_template)))

        # Requirements as blank nodes
        for req in script.requirements:
            req_node = make_bnode("req", req)
            graph.add((script_node, oc.scriptHasRequirement, req_node))
            graph.add((req_node, RDF.type, oc.Requirement))
            graph.add((req_node, oc.requirementType, Literal("Tool")))
            graph.add((req_node, oc.requirementValue, Literal(req)))
            graph.add((req_node, oc.isOptional, Literal(False)))

        if script.produces_output:
            graph.add((script_node, oc.scriptOutput, Literal(script.produces_output)))

        # O(1) lookup using pre-indexed files
        if script.relative_path in files_index:
            f = files_index[script.relative_path]
            graph.add((script_node, oc.fileHash, Literal(f.content_hash)))
            graph.add((script_node, oc.fileSize, Literal(f.file_size)))
            graph.add((script_node, oc.fileMimeType, Literal(f.mime_type)))

    # Workflows
    for wf in getattr(skill, 'workflows', []):
        wf_node = make_bnode("workflow", wf.workflow_id)
        graph.add((skill_uri, oc.hasWorkflow, wf_node))
        graph.add((wf_node, RDF.type, oc.Workflow))
        graph.add((wf_node, oc.workflowId, Literal(wf.workflow_id)))
        graph.add((wf_node, oc.workflowName, Literal(wf.name)))
        graph.add((wf_node, DCTERMS.description, Literal(wf.description)))

        # Build step node mapping for dependency resolution
        step_nodes = {}
        for step in wf.steps:
            step_node = make_bnode("step", f"{wf.workflow_id}_{step.step_id}")
            step_nodes[step.step_id] = step_node
            graph.add((wf_node, oc.hasStep, step_node))
            graph.add((step_node, RDF.type, oc.WorkflowStep))
            graph.add((step_node, oc.stepId, Literal(step.step_id)))
            graph.add((step_node, DCTERMS.description, Literal(step.description)))
            if step.expected_outcome:
                graph.add((step_node, oc.expectedOutcome, Literal(step.expected_outcome)))

        # Add step dependencies as ObjectProperty (second pass after all nodes created)
        for step in wf.steps:
            step_node = step_nodes[step.step_id]
            for dep_id in step.depends_on:
                dep_node = step_nodes.get(dep_id)
                if dep_node is not None:
                    graph.add((step_node, oc.stepDependsOn, dep_node))
                else:
                    logger.warning(
                        "Unresolved workflow step dependency '%s' referenced from step '%s' "
                        "in workflow '%s'; dependency will not be serialized.",
                        dep_id,
                        step.step_id,
                        wf.workflow_id,
                    )

    # Examples (use index for unique BNode IDs to avoid collisions with same name)
    for idx, ex in enumerate(getattr(skill, 'examples', [])):
        ex_node = make_bnode("example", f"{idx}:{ex.name}")
        graph.add((skill_uri, oc.hasExample, ex_node))
        graph.add((ex_node, RDF.type, oc.Example))
        graph.add((ex_node, oc.exampleName, Literal(ex.name)))
        graph.add((ex_node, oc.inputDescription, Literal(ex.input_description)))
        graph.add((ex_node, oc.outputExample, Literal(ex.output_example)))
        for tag in ex.tags:
            graph.add((ex_node, oc.hasTag, Literal(tag)))

    # === Resolve content_extraction: explicit param or skill attribute ===
    if content_extraction is None:
        content_extraction = getattr(skill, 'content_extraction', None)

    # === Ordered Procedures (from Phase 1 content extraction) ===
    # Convert extracted OrderedProcedure items to Workflow/WorkflowStep triples
    if content_extraction:
        for proc_idx, proc in enumerate(content_extraction.procedures):
            proc_node = make_bnode("proc_workflow", f"{proc_idx}")
            graph.add((skill_uri, oc.hasWorkflow, proc_node))
            graph.add((proc_node, RDF.type, oc.Workflow))
            graph.add((proc_node, oc.workflowId, Literal(f"procedure_{proc_idx}")))
            graph.add((proc_node, oc.workflowName, Literal(f"Ordered Procedure {proc_idx + 1}")))
            graph.add((proc_node, DCTERMS.description, Literal(
                f"Extracted ordered procedure with {len(proc.items)} steps")))
            for step in proc.items:
                step_node = make_bnode("proc_step", f"{proc_idx}_{step.position}")
                graph.add((proc_node, oc.hasStep, step_node))
                graph.add((step_node, RDF.type, oc.WorkflowStep))
                graph.add((step_node, oc.stepId, Literal(f"step_{step.position}")))
                graph.add((step_node, DCTERMS.description, Literal(step.text)))
                graph.add((step_node, oc.stepOrder, Literal(step.position)))

    # === Content Block Serialization ===

    if content_extraction:
        def _find_annotation(annotations: list, index: int):
            for a in annotations:
                if getattr(a, 'index', None) == index:
                    return a
            return None

        # Code Examples
        for idx, code_block in enumerate(content_extraction.code_blocks):
            code_node = make_bnode("code", f"{idx}:{code_block.language}")
            graph.add((skill_uri, oc.hasCodeExample, code_node))
            graph.add((code_node, RDF.type, oc.CodeExample))
            graph.add((code_node, oc.codeLanguage, Literal(code_block.language)))
            graph.add((code_node, oc.codeContent, Literal(code_block.content)))
            graph.add((code_node, oc.sourceLocation,
                       Literal(f"lines {code_block.source_line_start}-{code_block.source_line_end}")))
            ann = _find_annotation(skill.code_annotations, idx)
            if ann:
                graph.add((code_node, oc.codePurpose, Literal(ann.purpose)))
                graph.add((code_node, oc.codeContext, Literal(ann.context)))

        # Tables
        for idx, table in enumerate(content_extraction.tables):
            table_node = make_bnode("table", f"{idx}:{table.caption or 'untitled'}")
            graph.add((skill_uri, oc.hasTable, table_node))
            graph.add((table_node, RDF.type, oc.Table))
            graph.add((table_node, oc.tableMarkdown, Literal(table.markdown_source)))
            if table.caption:
                graph.add((table_node, oc.tableCaption, Literal(table.caption)))
            graph.add((table_node, oc.rowCount, Literal(table.row_count)))
            ann = _find_annotation(skill.table_annotations, idx)
            if ann:
                graph.add((table_node, oc.tablePurpose, Literal(ann.purpose)))

        # Flowcharts
        for idx, flow in enumerate(content_extraction.flowcharts):
            flow_node = make_bnode("flow", f"{idx}:{flow.chart_type}")
            graph.add((skill_uri, oc.hasFlowchart, flow_node))
            graph.add((flow_node, RDF.type, oc.Flowchart))
            graph.add((flow_node, oc.flowchartSource, Literal(flow.source)))
            graph.add((flow_node, oc.flowchartType, Literal(flow.chart_type)))
            ann = _find_annotation(skill.flowchart_annotations, idx)
            if ann:
                graph.add((flow_node, oc.flowchartDescription, Literal(ann.description)))

        # Templates
        for idx, tmpl in enumerate(content_extraction.templates):
            tmpl_node = make_bnode("tmpl", f"{idx}:{','.join(tmpl.detected_variables)}")
            graph.add((skill_uri, oc.hasTemplate, tmpl_node))
            graph.add((tmpl_node, RDF.type, oc.Template))
            graph.add((tmpl_node, oc.templateContent, Literal(tmpl.content)))
            for var in tmpl.detected_variables:
                graph.add((tmpl_node, oc.templateVariables, Literal(var)))
            ann = _find_annotation(skill.template_annotations, idx)
            if ann:
                graph.add((tmpl_node, oc.templateType, Literal(ann.template_type)))

    # === DocGraph Section Tree Serialization ===
    if content_extraction and content_extraction.sections:
        _serialize_section_tree(graph, skill_uri, content_extraction, make_bnode)

    # Frontmatter properties
    if hasattr(skill, 'frontmatter') and skill.frontmatter:
        graph.add((skill_uri, oc.hasName, Literal(skill.frontmatter.name)))
        graph.add((skill_uri, oc.hasDescription, Literal(skill.frontmatter.description)))

    # === New Metadata Properties (OntoCore refactoring) ===

    if hasattr(skill, 'category') and skill.category:
        graph.add((skill_uri, oc.hasCategory, Literal(skill.category)))

    # version, license, author belong in package.json manifest, not ontology TTL

    if hasattr(skill, 'package_name') and skill.package_name:
        graph.add((skill_uri, oc.hasPackageName, Literal(skill.package_name)))

    if hasattr(skill, 'is_user_invocable'):
        # Use typed boolean literal for xsd:boolean range
        graph.add((skill_uri, oc.isUserInvocable, Literal(skill.is_user_invocable, datatype=XSD.boolean)))

    if hasattr(skill, 'argument_hint') and skill.argument_hint:
        graph.add((skill_uri, oc.hasArgumentHint, Literal(skill.argument_hint)))

    # Repeatable properties — one triple per value
    for tool in getattr(skill, 'allowed_tools', []):
        graph.add((skill_uri, oc.hasAllowedTool, Literal(tool)))

    for alias in getattr(skill, 'aliases', []):
        graph.add((skill_uri, oc.hasAlias, Literal(alias)))


def serialize_skill_to_module(
    skill: ExtractedSkill,
    output_path: Path,
    output_base: Optional[Path] = None,
    qualified_id: str | None = None,
    extends_parent: str | None = None,
    extends_parent_qualified: str | None = None,
    content_extraction: "ContentExtraction | None" = None,
) -> None:
    """
    Serialize a skill to a standalone ontoskill.ttl module file.

    Creates a skill module that mirrors the skills directory structure:
    - skills/xlsx/pdf/pptx/SKILL.md -> ontoskills/xlsx/pdf/pptx/ontoskill.ttl

    Args:
        skill: ExtractedSkill to serialize
        output_path: Path where ontoskill.ttl should be written
        output_base: Base output directory for core ontology lookup (default: OUTPUT_DIR)
        qualified_id: Optional qualified ID for URI (prevents collisions across packages)
        extends_parent: Optional parent skill short ID to inject as extends relationship
        extends_parent_qualified: Optional parent qualified ID for extends URI
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

    core_ontology_path = output_base / CORE_ONTOLOGY_FILENAME
    if core_ontology_path.exists():
        g.add((URIRef(BASE_URI.rstrip('#')), OWL.imports, URIRef(CORE_ONTOLOGY_URL)))

    # Serialize the skill with optional extends injection
    serialize_skill(g, skill, qualified_id=qualified_id, extends_parent=extends_parent,
                    extends_parent_qualified=extends_parent_qualified,
                    content_extraction=content_extraction)

    # VALIDATE BEFORE WRITE
    try:
        validate_and_raise(g)
    except OntologyValidationError:
        logger.critical(f"Refusing to write invalid skill to {output_path}")
        raise

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    g.serialize(output_path, format="turtle")
    logger.info(f"Serialized skill module to {output_path}")
