"""
Tests for the serialization module.

Tests for serialize_skill(), serialize_skill_to_module(), and related functions.
"""

import pytest
from pathlib import Path
from rdflib import Graph, RDF, OWL, Literal

from compiler.serialization import (
    serialize_skill,
    serialize_skill_to_module,
    skill_uri_for_id,
)
from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload, StateTransition
from compiler.schemas import (
    ContentExtraction, CodeBlock, MarkdownTable, FlowchartBlock,
    TemplateBlock, CodeAnnotation, TableAnnotation, FlowchartAnnotation,
    TemplateAnnotation,
)
from compiler.core_ontology import get_oc_namespace


def test_serialize_skill_adds_triples_to_graph():
    """Test that serialize_skill adds skill triples to an RDF graph."""
    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="A test skill",
        genus="Test",
        differentia="for testing",
        intents=["test", "verify"],
        requirements=[Requirement(type="Tool", value="pytest")],
        contradicts=["bad-skill"],
        execution_payload=ExecutionPayload(executor="shell", code="echo test"),
        provenance="/skills/test/SKILL.md",
    )

    graph = Graph()
    serialize_skill(graph, skill)

    # Check skill was added
    oc = get_oc_namespace()
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.Skill) in graph


def test_serialize_skill_to_module_creates_file(tmp_path):
    """Test serializing a skill to a standalone module file."""
    skill = ExtractedSkill(
        id="test-module-skill",
        hash="module123",
        nature="A skill for module serialization",
        genus="Test",
        differentia="module serialization",
        intents=["test", "module"],
        requirements=[],
        execution_payload=None,
        provenance="/skills/test/SKILL.md",
        generated_by="claude-opus-4-6"
    )

    output_path = tmp_path / "test-skill" / "ontoskill.ttl"
    serialize_skill_to_module(skill, output_path)

    # Verify file was created
    assert output_path.exists()

    # Load and verify content
    graph = Graph()
    graph.parse(output_path, format="turtle")

    oc = get_oc_namespace()
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.Skill) in graph


def test_serialize_skill_to_module_with_output_base(tmp_path):
    """Test serialize_skill_to_module uses output_base parameter for core ontology lookup."""
    # Create a mock core ontology in a custom output_base directory
    output_base = tmp_path / "custom-ontoskills"
    output_base.mkdir(parents=True, exist_ok=True)

    # Create a minimal core ontology file
    core_ontology_path = output_base / "core.ttl"
    core_graph = Graph()
    oc = get_oc_namespace()
    core_graph.bind("oc", oc)
    core_graph.bind("owl", OWL)
    core_graph.add((oc.Skill, RDF.type, OWL.Class))
    core_graph.serialize(core_ontology_path, format="turtle")

    skill = ExtractedSkill(
        id="output-base-test",
        hash="outputbase123",
        nature="Test output_base parameter",
        genus="Test",
        differentia="output base",
        intents=["test"],
        requirements=[],
        execution_payload=None,
        provenance="/skills/test/SKILL.md",
        generated_by="claude-opus-4-6"
    )

    output_path = tmp_path / "test-output" / "ontoskill.ttl"

    # Call with 3 arguments: skill, output_path, output_base
    serialize_skill_to_module(skill, output_path, output_base=output_base)

    # Verify file was created
    assert output_path.exists()

    # Load and verify the skill
    graph = Graph()
    graph.parse(output_path, format="turtle")

    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.Skill) in graph


def test_serialize_skill_to_module_with_execution_payload(tmp_path):
    """Test that serialize_skill_to_module handles skills with execution payload."""
    skill = ExtractedSkill(
        id="exec-skill",
        hash="abc123def456",
        nature="Executable",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="test")
    )

    output_path = tmp_path / "exec-skill" / "ontoskill.ttl"
    serialize_skill_to_module(skill, output_path)

    # Verify file was created
    assert output_path.exists()

    # Load and verify the skill is ExecutableSkill
    graph = Graph()
    graph.parse(output_path, format="turtle")

    oc = get_oc_namespace()
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.ExecutableSkill) in graph


def test_serialize_skill_to_module_with_declarative_type(tmp_path):
    """Test that serialize_skill_to_module handles skills without payload as DeclarativeSkill."""
    skill = ExtractedSkill(
        id="decl-skill",
        hash="xyz789abc123",
        nature="Declarative",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6"
    )

    output_path = tmp_path / "decl-skill" / "ontoskill.ttl"
    serialize_skill_to_module(skill, output_path)

    # Verify file was created
    assert output_path.exists()

    # Load and verify the skill is DeclarativeSkill
    graph = Graph()
    graph.parse(output_path, format="turtle")

    oc = get_oc_namespace()
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.DeclarativeSkill) in graph


def test_serialize_skill_adds_executable_type():
    """Test that serialize_skill adds oc:ExecutableSkill type for skills with payload."""
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="exec-skill",
        hash="abc123def456",
        nature="Executable",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="test")
    )
    serialize_skill(g, skill)
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.ExecutableSkill) in g


def test_serialize_skill_adds_declarative_type():
    """Test that serialize_skill adds oc:DeclarativeSkill type for skills without payload."""
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="decl-skill",
        hash="xyz789abc123",
        nature="Declarative",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6"
    )
    serialize_skill(g, skill)
    skill_uri = skill_uri_for_id(skill.id)
    assert (skill_uri, RDF.type, oc.DeclarativeSkill) in g


def test_serialize_skill_to_module_validates_and_blocks_invalid():
    """Test that serialize_skill_to_module validates and blocks invalid skills."""
    from compiler.exceptions import OntologyValidationError

    # Create an invalid skill - missing required intent (SHACL requires minCount 1)
    skill = ExtractedSkill(
        id="invalid-skill",
        hash="invalid123abc456",
        nature="Invalid",
        genus="Test",
        differentia="test",
        intents=[],  # Missing required intent - should fail validation
        requirements=[],
        generated_by="claude-opus-4-6"
    )

    with pytest.raises(OntologyValidationError):
        serialize_skill_to_module(skill, Path("/tmp/invalid/ontoskill.ttl"))


def test_serialize_skill_to_module_does_not_write_on_validation_failure(tmp_path):
    """Test that serialize_skill_to_module does not write file when validation fails."""
    from compiler.exceptions import OntologyValidationError

    # Create an invalid skill
    skill = ExtractedSkill(
        id="invalid-skill-2",
        hash="invalid789def",
        nature="Invalid",
        genus="Test",
        differentia="test",
        intents=[],  # Missing required intent
        requirements=[],
        generated_by="claude-opus-4-6"
    )

    output_path = tmp_path / "invalid" / "ontoskill.ttl"

    with pytest.raises(OntologyValidationError):
        serialize_skill_to_module(skill, output_path)

    # File should NOT have been written
    assert not output_path.exists()


def test_serialize_skill_with_state_transitions():
    """Test that serialize_skill correctly serializes state transitions."""
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="state-skill",
        hash="statetrans123",
        nature="State transition skill",
        genus="Test",
        differentia="state transitions",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        state_transitions=StateTransition(
            requires_state=["oc:SystemAuthenticated"],
            yields_state=["oc:DocumentCreated"],
            handles_failure=["oc:PermissionDenied"]
        )
    )

    serialize_skill(g, skill)
    skill_uri = skill_uri_for_id(skill.id)

    # Verify state transitions were serialized
    assert (skill_uri, oc.requiresState, oc.SystemAuthenticated) in g
    assert (skill_uri, oc.yieldsState, oc.DocumentCreated) in g
    assert (skill_uri, oc.handlesFailure, oc.PermissionDenied) in g


def test_serialize_skill_relations_use_skill_uris():
    """Skill relations should be serialized as object properties, not literals."""
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="office",
        hash="officehash123",
        nature="Meta office skill",
        genus="Test",
        differentia="routes to document skills",
        intents=["route office tasks"],
        requirements=[],
        depends_on=["docx", "xlsx"],
        extends=["toolkit"],
        contradicts=["legacy-office"],
        generated_by="claude-opus-4-6",
    )

    serialize_skill(g, skill)
    skill_uri = skill_uri_for_id(skill.id)

    assert (skill_uri, oc.dependsOnSkill, skill_uri_for_id("docx")) in g
    assert (skill_uri, oc.dependsOnSkill, skill_uri_for_id("xlsx")) in g
    assert (skill_uri, oc.extends, skill_uri_for_id("toolkit")) in g
    assert (skill_uri, oc.contradicts, skill_uri_for_id("legacy-office")) in g


def test_serialize_skill_no_self_loop_depends():
    """Self-referencing depends_on should be silently skipped."""
    oc = get_oc_namespace()
    g = Graph()

    skill = ExtractedSkill(
        id="selfdep",
        hash="selfdephash",
        nature="Test",
        genus="Test",
        differentia="depends on itself",
        intents=["test self-dep"],
        requirements=[],
        depends_on=["selfdep", "other"],
        extends=[],
        contradicts=[],
        generated_by="test",
    )

    serialize_skill(g, skill)
    skill_uri = skill_uri_for_id(skill.id)

    # Should depend on 'other' but NOT on itself
    assert (skill_uri, oc.dependsOnSkill, skill_uri_for_id("other")) in g
    assert (skill_uri, oc.dependsOnSkill, skill_uri) not in g


def test_skill_uri_for_qualified_id():
    """Test URI generation handles Qualified IDs by slugifying slashes."""
    from compiler.serialization import skill_uri_for_id

    # Qualified ID with slashes should be slugified to QName-friendly form
    uri = skill_uri_for_id("obra/superpowers/brainstorming/planning")
    uri_str = str(uri)

    # URI should end with slugged fragment (slashes replaced with underscores)
    assert uri_str.endswith("#skill_obra_superpowers_brainstorming_planning")
    # Fragment should not contain slashes (the base URI https:// does, but fragment doesn't)
    fragment = uri_str.split("#")[-1]
    assert "/" not in fragment


def test_skill_uri_for_id_defensive_slugification():
    """Test that skill_uri_for_id defensively slugifies special characters."""
    from compiler.serialization import skill_uri_for_id

    # Dots should be replaced
    uri = skill_uri_for_id("my.skill")
    assert "#" in str(uri)
    fragment = str(uri).split("#")[-1]
    assert "." not in fragment
    assert "my_skill" in fragment

    # Spaces should be replaced
    uri = skill_uri_for_id("my skill")
    fragment = str(uri).split("#")[-1]
    assert " " not in fragment

    # Uppercase should be lowercased
    uri = skill_uri_for_id("MySkill")
    fragment = str(uri).split("#")[-1]
    assert fragment == "skill_myskill"

    # Mixed special chars
    uri = skill_uri_for_id("My.Package/With Spaces")
    fragment = str(uri).split("#")[-1]
    for char in [" ", ".", "/", "@"]:
        assert char not in fragment


def test_serialize_skill_with_extends_injection():
    """Test that extends is injected for sub-skills."""
    from compiler.serialization import serialize_skill, skill_uri_for_id
    from compiler.schemas import ExtractedSkill
    from rdflib import Graph

    # Create a minimal sub-skill
    sub_skill = ExtractedSkill(
        id="obra/superpowers/brainstorming/planning",
        hash="abc123",
        nature="A planning sub-skill",
        genus="Methodology",
        differentia="for brainstorming",
        intents=["plan_ideas"],
        requirements=[],
        depends_on=[],
        extends=[],  # Empty - will be injected
        contradicts=[],
        knowledge_nodes=[]
    )

    graph = Graph()
    serialize_skill(graph, sub_skill, extends_parent="obra/superpowers/brainstorming")

    # Verify extends triple was added using slugged URIs
    skill_uri = skill_uri_for_id(sub_skill.id)
    parent_skill_uri = skill_uri_for_id("obra/superpowers/brainstorming")

    from compiler.core_ontology import get_oc_namespace
    oc = get_oc_namespace()

    # Check that extends relationship exists
    extends_values = list(graph.objects(skill_uri, oc.extends))
    assert len(extends_values) == 1
    assert extends_values[0] == parent_skill_uri


def test_serialize_skill_to_module_with_extends(tmp_path):
    """Test module serialization with extends injection."""
    from compiler.serialization import serialize_skill_to_module
    from compiler.schemas import ExtractedSkill

    sub_skill = ExtractedSkill(
        id="obra/superpowers/brainstorming/planning",
        hash="abc123",
        nature="Planning sub-skill",
        genus="Methodology",
        differentia="for brainstorming phases",
        intents=["plan_ideas"],
        requirements=[],
        depends_on=[],
        extends=[],
        contradicts=[],
        knowledge_nodes=[],
        generated_by="claude-opus-4-6"
    )

    output_path = tmp_path / "output" / "brainstorming" / "planning.ttl"
    serialize_skill_to_module(
        sub_skill,
        output_path,
        extends_parent="obra/superpowers/brainstorming"
    )

    # Verify file exists and contains extends
    content = output_path.read_text()
    assert "oc:extends" in content
    assert "brainstorming" in content


class TestExtractedBlockSerialization:
    def _make_skill_with_content(self, **overrides):
        defaults = dict(
            id="content-skill",
            hash="abc123",
            nature="A skill with content blocks",
            genus="Test",
            differentia="content blocks",
            intents=["test content"],
            generated_by="test",
        )
        defaults.update(overrides)
        return ExtractedSkill(**defaults)

    def test_code_example_serialization(self):
        skill = self._make_skill_with_content(
            code_annotations=[CodeAnnotation(index=0, purpose="Demo code", context="always")],
        )
        content_extraction = ContentExtraction(
            code_blocks=[CodeBlock(language="python", content="print('hi')", source_line_start=3, source_line_end=4)],
            tables=[], flowcharts=[], procedures=[], templates=[],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        code_nodes = list(graph.subjects(RDF.type, oc.CodeExample))
        assert len(code_nodes) == 1
        assert (code_nodes[0], oc.codeLanguage, Literal("python")) in graph
        assert (code_nodes[0], oc.codeContent, Literal("print('hi')")) in graph
        assert (code_nodes[0], oc.codePurpose, Literal("Demo code")) in graph

    def test_table_serialization(self):
        skill = self._make_skill_with_content(
            table_annotations=[TableAnnotation(index=0, purpose="Parameter reference")],
        )
        content_extraction = ContentExtraction(
            code_blocks=[],
            tables=[MarkdownTable(markdown_source="| a | b |\n|---|---|\n| 1 | 2 |", caption="Test", row_count=1)],
            flowcharts=[], procedures=[], templates=[],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        table_nodes = list(graph.subjects(RDF.type, oc.Table))
        assert len(table_nodes) == 1
        assert (table_nodes[0], oc.tableMarkdown, Literal("| a | b |\n|---|---|\n| 1 | 2 |")) in graph
        assert (table_nodes[0], oc.tablePurpose, Literal("Parameter reference")) in graph

    def test_flowchart_serialization(self):
        skill = self._make_skill_with_content(
            flowchart_annotations=[FlowchartAnnotation(index=0, description="Decision flow")],
        )
        content_extraction = ContentExtraction(
            code_blocks=[], tables=[],
            flowcharts=[FlowchartBlock(source="digraph { A -> B }", chart_type="graphviz")],
            procedures=[], templates=[],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        flow_nodes = list(graph.subjects(RDF.type, oc.Flowchart))
        assert len(flow_nodes) == 1
        assert (flow_nodes[0], oc.flowchartType, Literal("graphviz")) in graph
        assert (flow_nodes[0], oc.flowchartDescription, Literal("Decision flow")) in graph

    def test_template_serialization(self):
        skill = self._make_skill_with_content(
            template_annotations=[TemplateAnnotation(index=0, template_type="prompt")],
        )
        content_extraction = ContentExtraction(
            code_blocks=[], tables=[], flowcharts=[],
            procedures=[],
            templates=[TemplateBlock(content="Hello {name}", detected_variables=["name"])],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        tmpl_nodes = list(graph.subjects(RDF.type, oc.Template))
        assert len(tmpl_nodes) == 1
        assert (tmpl_nodes[0], oc.templateType, Literal("prompt")) in graph
        assert (tmpl_nodes[0], oc.templateVariables, Literal("name")) in graph

    def test_procedure_serialized_as_workflow_with_step_order(self):
        from compiler.schemas import OrderedProcedure, ProcedureStep
        skill = self._make_skill_with_content()
        content_extraction = ContentExtraction(
            code_blocks=[], tables=[], flowcharts=[], templates=[],
            procedures=[OrderedProcedure(items=[
                ProcedureStep(text="First step", position=1),
                ProcedureStep(text="Second step", position=2),
            ])],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        wf_nodes = list(graph.subjects(RDF.type, oc.Workflow))
        assert len(wf_nodes) == 1
        step_nodes = list(graph.subjects(RDF.type, oc.WorkflowStep))
        assert len(step_nodes) == 2
        # Verify stepOrder is present
        step_orders = [int(str(o)) for s in step_nodes for o in graph.objects(s, oc.stepOrder)]
        assert sorted(step_orders) == [1, 2]

    def test_content_extraction_fallback_from_skill_attribute(self):
        from compiler.schemas import CompiledSkill, CodeBlock
        skill = CompiledSkill(
            id="fallback-skill",
            hash="fb123",
            nature="Fallback test",
            genus="Test",
            differentia="fallback",
            intents=["test fallback"],
            generated_by="test",
            content_extraction=ContentExtraction(
                code_blocks=[CodeBlock(language="python", content="x=1", source_line_start=1, source_line_end=1)],
                tables=[], flowcharts=[], procedures=[], templates=[],
            ),
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill)  # No content_extraction param!

        # Content blocks should still be serialized via fallback
        code_nodes = list(graph.subjects(RDF.type, oc.CodeExample))
        assert len(code_nodes) == 1


class TestContentTreeSerialization:
    def _make_skill_with_sections(self, **overrides):
        from compiler.schemas import ExtractedSkill
        defaults = dict(
            id="content-skill",
            hash="dg123",
            nature="A skill with section tree",
            genus="Test",
            differentia="content",
            intents=["test content"],
            generated_by="test",
        )
        defaults.update(overrides)
        return ExtractedSkill(**defaults)

    def test_section_serialization(self):
        from compiler.schemas import Section, Paragraph
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Overview", level=2, order=1, content=[
                    Paragraph(text_content="Intro text.", content_order=1),
                ]),
            ],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        section_nodes = list(graph.subjects(RDF.type, oc.Section))
        assert len(section_nodes) == 1
        assert (section_nodes[0], oc.sectionTitle, Literal("Overview")) in graph
        assert (section_nodes[0], oc.sectionLevel, Literal(2)) in graph
        assert (section_nodes[0], oc.sectionOrder, Literal(1)) in graph
        assert (skill_uri_for_id("content-skill"), oc.hasSection, section_nodes[0]) in graph

    def test_paragraph_in_section_serialization(self):
        from compiler.schemas import Section, Paragraph
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Intro", level=2, order=1, content=[
                    Paragraph(text_content="Hello **world**", content_order=1),
                ]),
            ],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        para_nodes = list(graph.subjects(RDF.type, oc.Paragraph))
        assert len(para_nodes) == 1
        assert (para_nodes[0], oc.textContent, Literal("Hello **world**")) in graph
        assert (para_nodes[0], oc.contentOrder, Literal(1)) in graph

        section_nodes = list(graph.subjects(RDF.type, oc.Section))
        assert (section_nodes[0], oc.hasContent, para_nodes[0]) in graph

    def test_bullet_list_serialization(self):
        from compiler.schemas import Section, BulletListBlock, BulletItem
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Mistakes", level=2, order=1, content=[
                    BulletListBlock(items=[
                        BulletItem(text="Don't skip tests", order=1),
                        BulletItem(text="Don't ignore errors", order=2),
                    ], content_order=1),
                ]),
            ],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        bl_nodes = list(graph.subjects(RDF.type, oc.BulletList))
        assert len(bl_nodes) == 1

        bi_nodes = list(graph.subjects(RDF.type, oc.BulletItem))
        assert len(bi_nodes) == 2
        assert (bi_nodes[0], oc.itemText, Literal("Don't skip tests")) in graph
        assert (bi_nodes[0], oc.itemOrder, Literal(1)) in graph

    def test_blockquote_serialization(self):
        from compiler.schemas import Section, BlockQuoteBlock
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Quote", level=2, order=1, content=[
                    BlockQuoteBlock(content="Clean code matters.", attribution="R.C. Martin", content_order=1),
                ]),
            ],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        bq_nodes = list(graph.subjects(RDF.type, oc.BlockQuote))
        assert len(bq_nodes) == 1
        assert (bq_nodes[0], oc.quoteContent, Literal("Clean code matters.")) in graph
        assert (bq_nodes[0], oc.quoteAttribution, Literal("R.C. Martin")) in graph

    def test_nested_section_serialization(self):
        from compiler.schemas import Section, Paragraph
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Parent", level=2, order=1, content=[
                    Paragraph(text_content="Parent intro.", content_order=1),
                ], subsections=[
                    Section(title="Child", level=3, order=1, content=[
                        Paragraph(text_content="Child text.", content_order=1),
                    ]),
                ]),
            ],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        section_nodes = list(graph.subjects(RDF.type, oc.Section))
        assert len(section_nodes) == 2

        parent = [s for s in section_nodes if (s, oc.sectionTitle, Literal("Parent")) in graph][0]
        child = [s for s in section_nodes if (s, oc.sectionTitle, Literal("Child")) in graph][0]
        assert (parent, oc.hasSubsection, child) in graph

    def test_code_block_in_section_gets_content_order(self):
        from compiler.schemas import Section, Paragraph, CodeBlock
        skill = self._make_skill_with_sections()
        content_extraction = ContentExtraction(
            sections=[
                Section(title="Example", level=2, order=1, content=[
                    Paragraph(text_content="Intro.", content_order=1),
                    CodeBlock(language="python", content="x=1", source_line_start=3, source_line_end=3, content_order=2),
                ]),
            ],
            code_blocks=[CodeBlock(language="python", content="x=1", source_line_start=3, source_line_end=3, content_order=2)],
        )
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=content_extraction)

        code_nodes = list(graph.subjects(RDF.type, oc.CodeExample))
        assert len(code_nodes) >= 1
        # Check that at least one code node has contentOrder = 2
        has_order_2 = any((node, oc.contentOrder, Literal(2)) in graph for node in code_nodes)
        assert has_order_2


class TestContentBlockSerialization:
    def _make_skill(self, **kw):
        defaults = dict(id="v2-skill", hash="v2hash", nature="test", genus="Test", differentia="v2", intents=["test"], generated_by="test")
        defaults.update(kw)
        return ExtractedSkill(**defaults)

    def test_html_block_serialization(self):
        from compiler.schemas import Section, HTMLBlock
        skill = self._make_skill()
        ce = ContentExtraction(sections=[Section(title="S", level=2, order=1, content=[HTMLBlock(content="<HARD-GATE>", content_order=1)])])
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=ce)
        html_nodes = list(graph.subjects(RDF.type, oc.HTMLBlock))
        assert len(html_nodes) == 1
        assert (html_nodes[0], oc.htmlContent, Literal("<HARD-GATE>")) in graph

    def test_frontmatter_block_serialization(self):
        from compiler.schemas import Section, FrontmatterBlock
        skill = self._make_skill()
        ce = ContentExtraction(sections=[Section(title="", level=0, order=0, content=[FrontmatterBlock(raw_yaml="name: test", properties={"name": "test"}, content_order=0)])])
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=ce)
        fm_nodes = list(graph.subjects(RDF.type, oc.FrontmatterBlock))
        assert len(fm_nodes) == 1
        assert (fm_nodes[0], oc.rawYaml, Literal("name: test")) in graph

    def test_bullet_item_children_serialization(self):
        from compiler.schemas import Section, BulletListBlock, BulletItem, CodeBlock
        skill = self._make_skill()
        ce = ContentExtraction(sections=[Section(title="S", level=2, order=1, content=[BulletListBlock(items=[
            BulletItem(text="Run tests", order=1, children=[CodeBlock(language="bash", content="pytest", source_line_start=3, source_line_end=3, content_order=0)]),
        ], content_order=1)])])
        graph = Graph()
        oc = get_oc_namespace()
        serialize_skill(graph, skill, content_extraction=ce)
        child_nodes = list(graph.subjects(RDF.type, oc.CodeExample))
        assert len(child_nodes) >= 1
        has_child = any(
            (item, oc.hasChild, child) in graph
            for item in list(graph.subjects(RDF.type, oc.BulletItem))
            for child in child_nodes
        )
        assert has_child
