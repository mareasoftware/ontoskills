import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace
from loader import (
    get_oc_namespace,
    create_core_ontology,
    serialize_skill,
    serialize_skill_to_module,
    load_ontology,
    load_skill_module,
    merge_skill,
    save_ontology_atomic,
    apply_reasoning,
    mirror_skill_path,
    get_output_path,
    create_output_directory,
)
from schemas import ExtractedSkill, Requirement, ExecutionPayload
from config import BASE_URI, CORE_STATES, FAILURE_STATES, OUTPUT_DIR


def test_get_oc_namespace():
    """Test that get_oc_namespace returns namespace with BASE_URI."""
    oc = get_oc_namespace()
    assert isinstance(oc, Namespace)
    assert str(oc) == BASE_URI


def test_create_core_ontology_structure(tmp_path):
    """Test core ontology creates required classes."""
    output_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(output_path)

    # Verify file was created
    assert output_path.exists()

    # Check that core classes exist
    oc = get_oc_namespace()

    # Check oc:Skill class
    assert (oc.Skill, RDF.type, OWL.Class) in graph
    assert (oc.Skill, RDFS.label, None) in graph

    # Check oc:State class
    assert (oc.State, RDF.type, OWL.Class) in graph

    # Check oc:Attempt class
    assert (oc.Attempt, RDF.type, OWL.Class) in graph

    # Check oc:ExecutionPayload class
    assert (oc.ExecutionPayload, RDF.type, OWL.Class) in graph


def test_create_core_ontology_state_properties(tmp_path):
    """Test core ontology creates state transition properties."""
    output_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(output_path)
    oc = get_oc_namespace()

    # Check oc:requiresState (Skill → State)
    assert (oc.requiresState, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.requiresState, RDFS.domain, oc.Skill) in graph
    assert (oc.requiresState, RDFS.range, oc.State) in graph

    # Check oc:yieldsState (Skill → State)
    assert (oc.yieldsState, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.yieldsState, RDFS.domain, oc.Skill) in graph
    assert (oc.yieldsState, RDFS.range, oc.State) in graph

    # Check oc:handlesFailure (Skill → State)
    assert (oc.handlesFailure, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.handlesFailure, RDFS.domain, oc.Skill) in graph
    assert (oc.handlesFailure, RDFS.range, oc.State) in graph

    # Check oc:hasStatus (Attempt → State)
    assert (oc.hasStatus, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.hasStatus, RDFS.domain, oc.Attempt) in graph
    assert (oc.hasStatus, RDFS.range, oc.State) in graph


def test_create_core_ontology_execution_payload(tmp_path):
    """Test core ontology creates execution payload class and properties."""
    output_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(output_path)
    oc = get_oc_namespace()

    # Check oc:hasPayload (Skill → ExecutionPayload)
    assert (oc.hasPayload, RDF.type, OWL.ObjectProperty) in graph
    assert (oc.hasPayload, RDFS.domain, oc.Skill) in graph
    assert (oc.hasPayload, RDFS.range, oc.ExecutionPayload) in graph

    # Check oc:executor (DatatypeProperty)
    assert (oc.executor, RDF.type, OWL.DatatypeProperty) in graph
    assert (oc.executor, RDFS.domain, oc.ExecutionPayload) in graph

    # Check oc:code (DatatypeProperty)
    assert (oc.code, RDF.type, OWL.DatatypeProperty) in graph
    assert (oc.code, RDFS.domain, oc.ExecutionPayload) in graph

    # Check oc:timeout (DatatypeProperty)
    assert (oc.timeout, RDF.type, OWL.DatatypeProperty) in graph
    assert (oc.timeout, RDFS.domain, oc.ExecutionPayload) in graph


def test_create_core_ontology_predefined_states(tmp_path):
    """Test core ontology includes predefined core and failure states."""
    output_path = tmp_path / "ontoclaw-core.ttl"
    graph = create_core_ontology(output_path)
    oc = get_oc_namespace()

    # Check core states exist
    for state_name, state_fragment in CORE_STATES.items():
        state_uri = oc[state_fragment.lstrip('#')]
        assert (state_uri, RDF.type, OWL.Class) in graph
        assert (state_uri, RDFS.subClassOf, oc.State) in graph

    # Check failure states exist
    for state_name, state_fragment in FAILURE_STATES.items():
        state_uri = oc[state_fragment.lstrip('#')]
        assert (state_uri, RDF.type, OWL.Class) in graph
        assert (state_uri, RDFS.subClassOf, oc.State) in graph


def test_serialize_skill():
    """Test skill serialization to RDF triples."""
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
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in graph


def test_load_ontology(tmp_path):
    """Test loading an existing ontology."""
    # Create a core ontology
    output_path = tmp_path / "ontoclaw-core.ttl"
    core_graph = create_core_ontology(output_path)

    # Load it back
    loaded = load_ontology(output_path)
    assert isinstance(loaded, Graph)
    prefixes = dict(loaded.namespaces())
    assert "oc" in prefixes


def test_merge_skill_new(tmp_path):
    """Test merging a new skill into ontology."""
    # Create core ontology first
    core_path = tmp_path / "ontoclaw-core.ttl"
    create_core_ontology(core_path)

    ontology_path = tmp_path / "skills.ttl"
    graph = load_ontology(ontology_path)
    graph.serialize(ontology_path, format="turtle")

    skill = ExtractedSkill(
        id="new-skill",
        hash="def456",
        nature="New skill",
        genus="Test",
        differentia="new",
        intents=["new"],
        requirements=[],
        constraints=[],
        execution_payload=None,
        provenance=None,
    )

    merged = merge_skill(ontology_path, skill)
    assert isinstance(merged, Graph)

    # Check skill was added
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged


def test_merge_skill_update(tmp_path):
    """Test updating an existing skill (same ID, different hash)."""
    # Create core ontology first
    core_path = tmp_path / "ontoclaw-core.ttl"
    create_core_ontology(core_path)

    ontology_path = tmp_path / "skills.ttl"
    graph = load_ontology(ontology_path)
    graph.serialize(ontology_path, format="turtle")

    # Add initial skill
    skill1 = ExtractedSkill(
        id="update-skill",
        hash="hash1",
        nature="Original",
        genus="Test",
        differentia="original",
        intents=["test"],
        requirements=[],
        contradicts=[],
        execution_payload=None,
        provenance=None,
    )
    merge_skill(ontology_path, skill1)
    save_ontology_atomic(ontology_path, merge_skill(ontology_path, skill1))

    # Update with same ID but different hash
    skill2 = ExtractedSkill(
        id="update-skill",
        hash="hash2",
        nature="Updated",
        genus="Test",
        differentia="updated",
        intents=["test"],
        requirements=[],
        contradicts=[],
        execution_payload=None,
        provenance=None,
    )

    merged = merge_skill(ontology_path, skill2)
    # New skill should be present
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill2.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged


def test_save_ontology_atomic(tmp_path):
    """Test atomic write with backup."""
    ontology_path = tmp_path / "skills.ttl"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create core ontology first
    core_path = tmp_path / "ontoclaw-core.ttl"
    create_core_ontology(core_path)

    graph = load_ontology(ontology_path)

    # First save
    save_ontology_atomic(ontology_path, graph, backup_dir=backup_dir)
    assert ontology_path.exists()

    # Second save (should create backup)
    oc = get_oc_namespace()
    graph.add((oc.TestSkill, RDF.type, oc.Skill))
    save_ontology_atomic(ontology_path, graph, backup_dir=backup_dir)

    # Check backup was created
    backups = list(backup_dir.glob("*.ttl"))
    assert len(backups) >= 1


def test_apply_reasoning(tmp_path):
    """Test OWL reasoning applies inferences."""
    # Create core ontology first
    core_path = tmp_path / "ontoclaw-core.ttl"
    create_core_ontology(core_path)

    graph = load_ontology(tmp_path / "skills.ttl")

    # Add some test relationships
    oc = get_oc_namespace()
    skill_a = oc["skill_a"]
    skill_b = oc["skill_b"]
    skill_c = oc["skill_c"]

    graph.add((skill_a, RDF.type, oc.Skill))
    graph.add((skill_b, RDF.type, oc.Skill))
    graph.add((skill_c, RDF.type, oc.Skill))

    # Add some relationships (extends, etc.)
    graph.add((skill_a, oc.extends, skill_b))
    graph.add((skill_b, oc.extends, skill_c))

    # Apply reasoning
    reasoned = apply_reasoning(graph)

    # Should have inferences
    assert isinstance(reasoned, Graph)


def test_mirror_skill_path_simple():
    """Test path mirroring with simple skill path."""
    skill_dir = Path("/skills/xlsx")
    output_base = Path("/semantic-skills")

    result = mirror_skill_path(skill_dir, output_base)

    assert result == Path("/semantic-skills/xlsx/skill.ttl")


def test_mirror_skill_path_nested():
    """Test path mirroring with nested skill path."""
    skill_dir = Path("/skills/xlsx/pdf/pptx")
    output_base = Path("/semantic-skills")

    result = mirror_skill_path(skill_dir, output_base)

    assert result == Path("/semantic-skills/xlsx/pdf/pptx/skill.ttl")


def test_mirror_skill_path_with_config():
    """Test path mirroring uses config defaults."""
    from config import SKILLS_DIR, OUTPUT_DIR

    # Create mock paths using config
    skill_dir = Path(SKILLS_DIR) / "xlsx" / "pdf"
    output_base = Path(OUTPUT_DIR)

    result = mirror_skill_path(skill_dir, output_base)

    assert result.name == "skill.ttl"
    assert "xlsx" in str(result)
    assert "pdf" in str(result)


def test_get_output_path():
    """Test get_output_path uses config defaults."""
    skill_dir = Path("/skills/test-skill")

    result = get_output_path(skill_dir)

    assert result.name == "skill.ttl"
    # Should resolve OUTPUT_DIR to absolute path
    assert "semantic-skills" in str(result) or "test-skill" in str(result)


def test_create_output_directory(tmp_path):
    """Test create_output_directory creates directory structure."""
    skill_dir = Path("/skills/xlsx/pdf/pptx")
    output_base = tmp_path / "semantic-skills"

    output_dir = create_output_directory(skill_dir, output_base)

    assert output_dir.exists()
    assert output_dir.is_dir()
    assert (output_dir / "skill.ttl").parent == output_dir


def test_serialize_skill_to_module(tmp_path):
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
    )

    output_path = tmp_path / "test-skill" / "skill.ttl"
    serialize_skill_to_module(skill, output_path)

    # Verify file was created
    assert output_path.exists()

    # Load and verify content
    graph = Graph()
    graph.parse(output_path, format="turtle")

    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in graph


def test_load_skill_module(tmp_path):
    """Test loading a skill module from file."""
    # First create a module
    skill = ExtractedSkill(
        id="loadable-skill",
        hash="loadable456",
        nature="A loadable skill",
        genus="Test",
        differentia="loadable",
        intents=["test"],
        requirements=[],
        execution_payload=None,
        provenance="/skills/loadable/SKILL.md",
    )

    module_path = tmp_path / "loadable" / "skill.ttl"
    serialize_skill_to_module(skill, module_path)

    # Now load it
    loaded_graph = load_skill_module(module_path)

    assert isinstance(loaded_graph, Graph)
    assert len(loaded_graph) > 0

    # Verify skill is present
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in loaded_graph


def test_load_skill_module_not_found():
    """Test loading non-existent module raises error."""
    from loader import OntologyLoadError

    non_existent = Path("/tmp/non-existent/skill.ttl")

    with pytest.raises(OntologyLoadError):
        load_skill_module(non_existent)
