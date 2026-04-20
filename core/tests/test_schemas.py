import pytest
from pydantic import ValidationError
from compiler.schemas import Requirement, ExecutionPayload, ExtractedSkill, StateTransition
from compiler.schemas import (
    CodeBlock, MarkdownTable, FlowchartBlock, ProcedureStep,
    OrderedProcedure, TemplateBlock, ContentExtraction
)
from compiler.schemas import (
    CodeAnnotation, TableAnnotation, FlowchartAnnotation,
    TemplateAnnotation, CompiledSkill, Workflow, WorkflowStep,
)


def test_skill_type_computed_as_executable():
    """Test that skill_type is 'executable' when execution_payload exists."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hi')")
    )
    assert skill.skill_type == "executable"


def test_skill_type_computed_as_declarative():
    """Test that skill_type is 'declarative' when no execution_payload."""
    skill = ExtractedSkill(
        id="test",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6"
    )
    assert skill.skill_type == "declarative"


def test_state_transition_model():
    """Test StateTransition model with valid URIs."""
    st = StateTransition(
        requires_state=["oc:SystemAuthenticated", "oc:UserLoggedIn"],
        yields_state=["oc:DocumentCreated"],
        handles_failure=["oc:PermissionDenied", "oc:ResourceNotFound"]
    )
    assert st.requires_state == ["oc:SystemAuthenticated", "oc:UserLoggedIn"]
    assert st.yields_state == ["oc:DocumentCreated"]
    assert st.handles_failure == ["oc:PermissionDenied", "oc:ResourceNotFound"]


def test_state_transition_defaults():
    """Test StateTransition model with empty lists (defaults)."""
    st = StateTransition()
    assert st.requires_state == []
    assert st.yields_state == []
    assert st.handles_failure == []


def test_state_transition_uri_validation():
    """Test that invalid URIs raise ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        StateTransition(requires_state=["invalid-uri"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        StateTransition(yields_state=["oc:invalid", "oc:AnotherInvalid"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    with pytest.raises(ValidationError) as exc_info:
        StateTransition(handles_failure=["oc:123InvalidStart"])
    assert "state URIs" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()


def test_schemas_validation():
    req = Requirement(type="EnvVar", value="API_KEY")
    assert req.optional is False

    payload = ExecutionPayload(executor="shell", code="echo 'hello'")
    assert payload.timeout is None

    state_transition = StateTransition(
        requires_state=["oc:SystemAuthenticated"],
        yields_state=["oc:DocumentCreated"],
        handles_failure=["oc:PermissionDenied"]
    )

    skill = ExtractedSkill(
        id="test-skill",
        hash="abcdef",
        nature="A test skill",
        genus="Test",
        differentia="that tests",
        intents=["testing"],
        requirements=[req],
        state_transitions=state_transition,
        generated_by="gpt-4",
        execution_payload=payload,
        provenance="/path",
    )
    assert skill.id == "test-skill"
    assert skill.generated_by == "gpt-4"
    assert skill.state_transitions.requires_state == ["oc:SystemAuthenticated"]


# ============================================================================
# KnowledgeNode Tests (10-Dimensional Epistemic TBox)
# ============================================================================


def test_knowledge_node_model():
    """Test KnowledgeNode model with valid data."""
    from compiler.schemas import KnowledgeNode, SeverityLevel

    kn = KnowledgeNode(
        node_type="AntiPattern",
        directive_content="Never modify the spreadsheet without preserving formulas",
        applies_to_context="When editing any Excel file",
        has_rationale="Formula corruption breaks the spreadsheet's computational integrity",
        severity_level=SeverityLevel.CRITICAL
    )
    assert kn.node_type == "AntiPattern"
    assert kn.severity_level == SeverityLevel.CRITICAL


def test_knowledge_node_without_severity():
    """Test KnowledgeNode model without optional severity_level."""
    from compiler.schemas import KnowledgeNode

    kn = KnowledgeNode(
        node_type="Heuristic",
        directive_content="Use absolute paths for file operations",
        applies_to_context="Always",
        has_rationale="Relative paths can break when cwd changes"
    )
    assert kn.severity_level is None


def test_knowledge_node_invalid_type():
    """Test that invalid node_type raises ValidationError."""
    from compiler.schemas import KnowledgeNode

    with pytest.raises(ValidationError):
        KnowledgeNode(
            node_type="InvalidType",
            directive_content="test",
            applies_to_context="test",
            has_rationale="test"
        )


def test_severity_level_enum():
    """Test SeverityLevel enum values."""
    from compiler.schemas import SeverityLevel

    assert SeverityLevel.CRITICAL.value == "CRITICAL"
    assert SeverityLevel.HIGH.value == "HIGH"
    assert SeverityLevel.MEDIUM.value == "MEDIUM"
    assert SeverityLevel.LOW.value == "LOW"


def test_extracted_skill_with_knowledge_nodes():
    """Test ExtractedSkill with knowledge_nodes field."""
    from compiler.schemas import ExtractedSkill, KnowledgeNode

    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="claude-opus-4-6",
        knowledge_nodes=[
            KnowledgeNode(
                node_type="Standard",
                directive_content="Always validate input",
                applies_to_context="Before processing",
                has_rationale="Prevents injection attacks"
            )
        ]
    )
    assert len(skill.knowledge_nodes) == 1
    assert skill.knowledge_nodes[0].node_type == "Standard"


# ============================================================================
# KnowledgeNode Filtering Tests (parse_and_clean_nested_data)
# ============================================================================


def test_knowledge_node_filtering_preserves_valid_dicts():
    """Test that valid dict knowledge_nodes are preserved."""
    from compiler.schemas import ExtractedSkill

    skill = ExtractedSkill(
        id="test",
        hash="abc",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="test",
        knowledge_nodes=[
            {
                "node_type": "Standard",
                "directive_content": "Always validate",
                "applies_to_context": "Always",
                "has_rationale": "Security"
            }
        ]
    )
    assert len(skill.knowledge_nodes) == 1
    assert skill.knowledge_nodes[0].node_type == "Standard"


def test_knowledge_node_filtering_removes_incomplete_dicts():
    """Test that incomplete dict knowledge_nodes are filtered out with warning."""
    from compiler.schemas import ExtractedSkill
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            requirements=[],
            generated_by="test",
            knowledge_nodes=[
                {
                    "node_type": "Standard",
                    "directive_content": "Always validate"
                    # Missing: applies_to_context, has_rationale
                }
            ]
        )

        # Should have been filtered out
        assert len(skill.knowledge_nodes) == 0
        # Should have raised a warning
        assert len(w) == 1
        assert "incomplete" in str(w[0].message).lower()


def test_knowledge_node_filtering_parses_json_strings():
    """Test that string JSON knowledge_nodes are parsed and validated."""
    from compiler.schemas import ExtractedSkill
    import json

    valid_node = json.dumps({
        "node_type": "AntiPattern",
        "directive_content": "Never do X",
        "applies_to_context": "Always",
        "has_rationale": "Because Y"
    })

    skill = ExtractedSkill(
        id="test",
        hash="abc",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="test",
        knowledge_nodes=[valid_node]
    )

    # Should have been parsed and kept
    assert len(skill.knowledge_nodes) == 1
    assert skill.knowledge_nodes[0].node_type == "AntiPattern"


def test_knowledge_node_filtering_discards_invalid_json_strings():
    """Test that invalid JSON strings are discarded with warning."""
    from compiler.schemas import ExtractedSkill
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            requirements=[],
            generated_by="test",
            knowledge_nodes=["not valid json", '{"node_type": "Standard"}']  # Invalid JSON and incomplete JSON
        )

        # Both should have been filtered out
        assert len(skill.knowledge_nodes) == 0
        # Should have raised warnings
        assert len(w) >= 1


def test_knowledge_node_filtering_preserves_knowledge_node_objects():
    """Test that KnowledgeNode objects are preserved."""
    from compiler.schemas import ExtractedSkill, KnowledgeNode

    kn = KnowledgeNode(
        node_type="Heuristic",
        directive_content="Test",
        applies_to_context="Always",
        has_rationale="Because"
    )

    skill = ExtractedSkill(
        id="test",
        hash="abc",
        nature="Test",
        genus="Test",
        differentia="test",
        intents=["test"],
        requirements=[],
        generated_by="test",
        knowledge_nodes=[kn]
    )

    assert len(skill.knowledge_nodes) == 1
    assert skill.knowledge_nodes[0].node_type == "Heuristic"


def test_knowledge_node_filtering_mixed_types():
    """Test filtering with mixed valid and invalid nodes."""
    from compiler.schemas import ExtractedSkill, KnowledgeNode
    import json
    import warnings

    valid_dict = {
        "node_type": "Standard",
        "directive_content": "Valid",
        "applies_to_context": "Always",
        "has_rationale": "Reason"
    }
    invalid_dict = {"node_type": "Standard"}  # Incomplete
    valid_json_string = json.dumps({
        "node_type": "AntiPattern",
        "directive_content": "Valid JSON",
        "applies_to_context": "Always",
        "has_rationale": "Reason"
    })
    invalid_json_string = "not json"

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")

        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            requirements=[],
            generated_by="test",
            knowledge_nodes=[valid_dict, invalid_dict, valid_json_string, invalid_json_string]
        )

        # Only valid_dict and valid_json_string should remain
        assert len(skill.knowledge_nodes) == 2
        node_types = {kn.node_type for kn in skill.knowledge_nodes}
        assert "Standard" in node_types
        assert "AntiPattern" in node_types


def test_knowledge_node_filtering_unsupported_types():
    """Test that unsupported types (not dict, str, or KnowledgeNode) are discarded with warning."""
    from compiler.schemas import ExtractedSkill
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            requirements=[],
            generated_by="test",
            knowledge_nodes=[123, None, ["list"]]  # int, None, list - all unsupported
        )

        # All should have been filtered out
        assert len(skill.knowledge_nodes) == 0
        # Should have raised warnings for each unsupported type
        assert len(w) == 3
        warning_messages = [str(warning.message) for warning in w]
        assert any("unsupported type" in msg.lower() for msg in warning_messages)


class TestContentExtractionModels:
    def test_code_block_construction(self):
        cb = CodeBlock(
            language="python",
            content="print('hello')",
            source_line_start=10,
            source_line_end=12,
        )
        assert cb.language == "python"
        assert cb.content == "print('hello')"
        assert cb.source_line_start == 10

    def test_markdown_table_construction(self):
        t = MarkdownTable(
            markdown_source="| a | b |\n|---|---|\n| 1 | 2 |",
            caption="Test table",
            row_count=1,
        )
        assert t.row_count == 1
        assert t.caption == "Test table"

    def test_markdown_table_without_caption(self):
        t = MarkdownTable(
            markdown_source="| a |\n|---|\n| 1 |",
            caption=None,
            row_count=1,
        )
        assert t.caption is None

    def test_flowchart_block_construction(self):
        f = FlowchartBlock(
            source="digraph { A -> B }",
            chart_type="graphviz",
        )
        assert f.chart_type == "graphviz"

    def test_flowchart_block_mermaid(self):
        f = FlowchartBlock(
            source="graph TD\n  A-->B",
            chart_type="mermaid",
        )
        assert f.chart_type == "mermaid"

    def test_ordered_procedure(self):
        p = OrderedProcedure(items=[
            ProcedureStep(text="Step one", position=1),
            ProcedureStep(text="Step two", position=2),
        ])
        assert len(p.items) == 2
        assert p.items[0].position == 1

    def test_template_block(self):
        t = TemplateBlock(
            content="Hello {name}, welcome to {place}",
            detected_variables=["name", "place"],
        )
        assert t.detected_variables == ["name", "place"]

    def test_content_extraction_empty(self):
        ce = ContentExtraction(
            code_blocks=[], tables=[], flowcharts=[],
            procedures=[], templates=[],
        )
        assert ce.code_blocks == []

    def test_content_extraction_with_blocks(self):
        ce = ContentExtraction(
            code_blocks=[CodeBlock(language="python", content="x=1", source_line_start=1, source_line_end=1)],
            tables=[],
            flowcharts=[FlowchartBlock(source="digraph{}", chart_type="graphviz")],
            procedures=[OrderedProcedure(items=[ProcedureStep(text="Do it", position=1)])],
            templates=[],
        )
        assert len(ce.code_blocks) == 1
        assert len(ce.flowcharts) == 1
        assert len(ce.procedures) == 1


class TestAnnotationModels:
    def test_code_annotation(self):
        a = CodeAnnotation(index=0, purpose="Creates a presentation", context="when creating slides")
        assert a.index == 0
        assert a.purpose == "Creates a presentation"

    def test_table_annotation(self):
        a = TableAnnotation(index=0, purpose="Parameter reference")
        assert a.index == 0

    def test_flowchart_annotation(self):
        a = FlowchartAnnotation(index=0, description="Decision flow for TDD cycle")
        assert a.description == "Decision flow for TDD cycle"

    def test_template_annotation(self):
        a = TemplateAnnotation(index=0, template_type="prompt")
        assert a.template_type == "prompt"

    def test_extracted_skill_has_annotation_fields(self):
        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            code_annotations=[CodeAnnotation(index=0, purpose="demo", context="always")],
            table_annotations=[],
            flowchart_annotations=[],
            template_annotations=[],
        )
        assert len(skill.code_annotations) == 1
        assert skill.code_annotations[0].purpose == "demo"

    def test_extracted_skill_has_workflows(self):
        """Verify workflows moved from CompiledSkill to ExtractedSkill (bug fix)."""
        skill = ExtractedSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            workflows=[Workflow(
                workflow_id="main",
                name="Main flow",
                description="The main flow",
                steps=[WorkflowStep(step_id="s1", description="Step 1")],
            )],
        )
        assert len(skill.workflows) == 1
        assert skill.workflows[0].workflow_id == "main"

    def test_compiled_skill_inherits_workflows(self):
        """CompiledSkill should still have workflows via inheritance."""
        compiled = CompiledSkill(
            id="test",
            hash="abc",
            nature="Test",
            genus="Test",
            differentia="test",
            intents=["test"],
            workflows=[Workflow(
                workflow_id="inherited",
                name="Inherited",
                description="Test",
                steps=[],
            )],
        )
        assert len(compiled.workflows) == 1


class TestDocGraphModels:
    def test_paragraph_model(self):
        from compiler.schemas import Paragraph
        p = Paragraph(text_content="Hello **world**", content_order=1)
        assert p.block_type == "paragraph"
        assert p.content_order == 1

    def test_bullet_list_model(self):
        from compiler.schemas import BulletListBlock, BulletItem
        bl = BulletListBlock(
            items=[BulletItem(text="First", order=1), BulletItem(text="Second", order=2)],
            content_order=2,
        )
        assert bl.block_type == "bullet_list"
        assert len(bl.items) == 2

    def test_blockquote_model(self):
        from compiler.schemas import BlockQuoteBlock
        bq = BlockQuoteBlock(content="Clean code always looks like it was written by someone who cares.", attribution="Robert C. Martin", content_order=3)
        assert bq.block_type == "blockquote"
        assert bq.attribution is not None

    def test_section_model_with_heterogeneous_content(self):
        from compiler.schemas import Section, Paragraph, CodeBlock, BulletListBlock, BulletItem
        section = Section(
            title="Overview",
            level=2,
            order=1,
            content=[
                Paragraph(text_content="Some intro text.", content_order=1),
                CodeBlock(language="python", content="print('hi')", source_line_start=5, source_line_end=7),
                BulletListBlock(items=[BulletItem(text="Point A", order=1)], content_order=3),
            ],
        )
        assert len(section.content) == 3
        assert section.content[0].block_type == "paragraph"
        assert section.content[1].block_type == "code_block"
        assert section.content[2].block_type == "bullet_list"

    def test_section_nested_subsections(self):
        from compiler.schemas import Section, Paragraph
        parent = Section(
            title="Tools",
            level=2,
            order=1,
            content=[Paragraph(text_content="Intro.", content_order=1)],
            subsections=[
                Section(title="search_skills", level=3, order=1, content=[]),
                Section(title="get_skill_context", level=3, order=2, content=[]),
            ],
        )
        assert len(parent.subsections) == 2
        assert parent.subsections[0].level == 3

    def test_content_extraction_with_sections_and_flat_lists(self):
        from compiler.schemas import ContentExtraction, Section, Paragraph, CodeBlock
        ce = ContentExtraction(
            sections=[
                Section(title="Intro", level=2, order=1, content=[
                    Paragraph(text_content="Hello.", content_order=1),
                    CodeBlock(language="python", content="x=1", source_line_start=3, source_line_end=3),
                ]),
            ],
            code_blocks=[CodeBlock(language="python", content="x=1", source_line_start=3, source_line_end=3)],
        )
        assert len(ce.sections) == 1
        assert len(ce.code_blocks) == 1
