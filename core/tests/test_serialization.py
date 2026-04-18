"""
Tests for the serialization module.

Tests for serialize_skill(), serialize_skill_to_module(), and related functions.
"""

import pytest
from pathlib import Path
from rdflib import Graph, RDF, OWL

from compiler.serialization import (
    serialize_skill,
    serialize_skill_to_module,
    skill_uri_for_id,
)
from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload, StateTransition
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
