"""
Tests for the serialization module.

Tests for serialize_skill(), serialize_skill_to_module(), and related functions.
"""

import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace

from compiler.serialization import (
    serialize_skill,
    serialize_skill_to_module,
    skill_uri_for_id,
)
from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload, StateTransition
from compiler.config import BASE_URI
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
    core_ontology_path = output_base / "ontoskills-core.ttl"
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

    assert (skill_uri, oc.dependsOn, skill_uri_for_id("docx")) in g
    assert (skill_uri, oc.dependsOn, skill_uri_for_id("xlsx")) in g
    assert (skill_uri, oc.extends, skill_uri_for_id("toolkit")) in g
    assert (skill_uri, oc.contradicts, skill_uri_for_id("legacy-office")) in g


def test_skill_uri_for_qualified_id():
    """Test URI generation handles Qualified IDs with slashes."""
    from compiler.serialization import skill_uri_for_id

    # Qualified ID with slashes should be preserved in URI
    uri = skill_uri_for_id("obra/superpowers/brainstorming/planning")
    uri_str = str(uri)

    # URI should contain the full qualified path with slashes preserved
    assert "obra/superpowers/brainstorming/planning" in uri_str
