"""Tests for SHACL validation module."""

import pytest
from rdflib import Graph, Namespace, Literal, RDF


def test_validate_skill_graph_empty_graph():
    """Test validation of empty graph (should pass - no skill instances to validate)."""
    from compiler.validator import validate_skill_graph

    g = Graph()
    result = validate_skill_graph(g)
    assert result.conforms is True  # Empty graph has no skill instances to validate


def test_validate_and_raise_raises_for_invalid():
    """Test that validate_and_raise raises OntologyValidationError for invalid graph."""
    from compiler.validator import validate_and_raise
    from compiler.exceptions import OntologyValidationError

    oc = Namespace("https://ontoskills.sh/ontology#")
    g = Graph()

    # Add a skill without required properties (invalid)
    skill_uri = oc["skill_test"]
    g.add((skill_uri, RDF.type, oc.Skill))
    # Missing resolvesIntent and generatedBy - should fail

    with pytest.raises(OntologyValidationError):
        validate_and_raise(g)


def test_validation_result_namedtuple():
    """Test that ValidationResult is a NamedTuple with correct fields."""
    from compiler.validator import ValidationResult

    # Create a result
    result = ValidationResult(
        conforms=True,
        results_text="All good",
        results_graph=None
    )
    assert result.conforms is True
    assert result.results_text == "All good"
    assert result.results_graph is None


def test_load_shacl_shapes():
    """Test that SHACL shapes file loads correctly."""
    from compiler.validator import load_shacl_shapes

    shapes = load_shacl_shapes()
    assert shapes is not None
    # Should contain our shapes (more than 0 triples)
    assert len(shapes) > 0


def test_load_core_ontology_returns_none_if_missing():
    """Test that load_core_ontology returns None if core ontology doesn't exist."""
    from compiler.validator import load_core_ontology

    # This test assumes core ontology might not exist in test environment
    result = load_core_ontology()
    # Result could be None or a Graph depending on whether ontoskills-core.ttl exists
    if result is None:
        assert True  # Expected if file doesn't exist
    else:
        assert isinstance(result, Graph)


# ============================================================================
# COMPREHENSIVE VALIDATION TEST CASES
# ============================================================================


def test_valid_executable_skill_passes():
    """A skill with all required fields and valid payload should pass."""
    from compiler.schemas import ExtractedSkill, ExecutionPayload, Requirement
    from compiler.serialization import serialize_skill
    from compiler.validator import validate_skill_graph

    skill = ExtractedSkill(
        id="test-skill",
        hash="abc123",
        nature="Test skill",
        genus="Test",
        differentia="for testing",
        intents=["test"],
        requirements=[Requirement(type="Tool", value="pytest")],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hello')")
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is True


def test_skill_missing_intent_fails():
    """A skill without resolvesIntent should fail validation."""
    from compiler.schemas import ExtractedSkill, Requirement
    from compiler.serialization import serialize_skill
    from compiler.validator import validate_skill_graph

    skill = ExtractedSkill(
        id="bad-skill",
        hash="def456",
        nature="Bad skill",
        genus="Test",
        differentia="incomplete",
        intents=[],  # Missing required intent
        requirements=[Requirement(type="Tool", value="pytest")],
        generated_by="claude-opus-4-6"
    )
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "resolvesIntent" in result.results_text


def test_skill_without_payload_is_declarative():
    """A skill without execution_payload becomes DeclarativeSkill and passes."""
    from compiler.schemas import ExtractedSkill, Requirement
    from compiler.serialization import serialize_skill
    from compiler.validator import validate_skill_graph

    skill = ExtractedSkill(
        id="knowledge-skill",
        hash="ghi789",
        nature="Knowledge skill",
        genus="Test",
        differentia="declarative knowledge",
        intents=["test"],
        requirements=[Requirement(type="Tool", value="pytest")],
        generated_by="claude-opus-4-6"
        # No execution_payload - automatically becomes DeclarativeSkill
    )
    graph = Graph()
    serialize_skill(graph, skill)  # Will add oc:DeclarativeSkill type
    result = validate_skill_graph(graph)
    # This should pass since it's a valid DeclarativeSkill (no payload required)
    assert result.conforms is True


def test_literal_as_state_fails():
    """A skill with a literal string (not URI) as state should fail."""
    from compiler.schemas import ExtractedSkill, Requirement, StateTransition, ExecutionPayload
    from compiler.serialization import serialize_skill
    from compiler.core_ontology import get_oc_namespace
    from compiler.validator import validate_skill_graph

    oc = get_oc_namespace()

    skill = ExtractedSkill(
        id="bad-state",
        hash="mno345",
        nature="Bad state skill",
        genus="Test",
        differentia="invalid state",
        intents=["test"],
        requirements=[Requirement(type="Tool", value="pytest")],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="test")
    )
    graph = Graph()
    serialize_skill(graph, skill)

    # Manually add a literal (string) as state - this should fail
    from compiler.serialization import skill_uri_for_id

    skill_uri = skill_uri_for_id(skill.id)
    graph.add((skill_uri, oc.yieldsState, Literal("SomeState")))  # WRONG: Literal not URI

    result = validate_skill_graph(graph)
    assert result.conforms is False
    assert "yieldsState" in result.results_text or "IRI" in result.results_text


def test_skill_with_payload_is_executable():
    """A skill with execution_payload becomes ExecutableSkill and passes."""
    from compiler.schemas import ExtractedSkill, ExecutionPayload, Requirement
    from compiler.serialization import serialize_skill
    from compiler.validator import validate_skill_graph

    skill = ExtractedSkill(
        id="code-skill",
        hash="jkl012",
        nature="Executable skill",
        genus="Test",
        differentia="has code to execute",
        intents=["test"],
        requirements=[Requirement(type="Tool", value="pytest")],
        generated_by="claude-opus-4-6",
        execution_payload=ExecutionPayload(executor="python", code="print('hello')")
    )
    # skill.skill_type will be "executable" because payload exists
    # So this will be validated as ExecutableSkill
    graph = Graph()
    serialize_skill(graph, skill)
    result = validate_skill_graph(graph)
    assert result.conforms is True  # It's a valid ExecutableSkill


# ============================================================================
# KnowledgeNode SHACL VALIDATION TESTS
# ============================================================================


def test_knowledge_node_validation_missing_required():
    """Test that KnowledgeNode without required properties fails SHACL."""
    from compiler.validator import validate_skill_graph
    from rdflib import Graph, RDF, Literal, Namespace
    from compiler.config import BASE_URI

    g = Graph()
    oc = Namespace(BASE_URI)

    # Create a KnowledgeNode without required properties
    kn_uri = oc["kn_test123"]
    g.add((kn_uri, RDF.type, oc.KnowledgeNode))

    # Should fail validation
    result = validate_skill_graph(g)
    assert not result.conforms
    assert "directiveContent" in result.results_text or "appliesToContext" in result.results_text


    assert "hasRationale" in result.results_text


def test_knowledge_node_validation_with_all_required():
    """Test that KnowledgeNode with all required properties passes."""
    from compiler.validator import validate_skill_graph
    from rdflib import Graph, RDF, Literal, Namespace
    from compiler.config import BASE_URI

    g = Graph()
    oc = Namespace(BASE_URI)

    # Create a valid KnowledgeNode (typed as both for completeness)
    kn_uri = oc["kn_test456"]
    g.add((kn_uri, RDF.type, oc.KnowledgeNode))
    g.add((kn_uri, RDF.type, oc.AntiPattern))
    g.add((kn_uri, oc.directiveContent, Literal("Never do X")))
    g.add((kn_uri, oc.appliesToContext, Literal("Always")))
    g.add((kn_uri, oc.hasRationale, Literal("Because Y")))

    # Should pass validation
    result = validate_skill_graph(g)
    assert result.conforms


def test_knowledge_node_shape_target_objects_of():
    """Test that sh:targetObjectsOf validates nodes linked via impartsKnowledge.

    This tests that a node typed ONLY as AntiPattern (not explicitly KnowledgeNode)
    is still validated when linked from a Skill via impartsKnowledge.
    """
    from compiler.validator import validate_skill_graph
    from rdflib import Graph, RDF, Literal, Namespace
    from compiler.config import BASE_URI

    g = Graph()
    oc = Namespace(BASE_URI)

    # Create a Skill
    skill_uri = oc["test_skill"]
    g.add((skill_uri, RDF.type, oc.Skill))
    g.add((skill_uri, oc.resolvesIntent, Literal("test intent")))
    g.add((skill_uri, oc.generatedBy, Literal("test")))

    # Create a KnowledgeNode typed ONLY as AntiPattern (not KnowledgeNode)
    kn_uri = oc["kn_subclass"]
    g.add((kn_uri, RDF.type, oc.AntiPattern))
    # Missing required properties: directiveContent, appliesToContext, hasRationale

    # Link skill to knowledge node via impartsKnowledge
    g.add((skill_uri, oc.impartsKnowledge, kn_uri))

    # Should FAIL because KnowledgeNodeShape applies via targetObjectsOf
    # and the node is missing required properties
    result = validate_skill_graph(g)
    assert not result.conforms
    assert "directiveContent" in result.results_text or "appliesToContext" in result.results_text
