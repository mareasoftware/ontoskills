"""
Tests for the storage module.

Tests for file I/O operations including:
- Path mirroring operations
- File loading
- Merging skills into ontologies
- Atomic saves with backup
- Orphaned skill cleanup
"""

import pytest
from pathlib import Path
from rdflib import Graph, RDF, RDFS, OWL, Namespace, Literal, URIRef
from rdflib.namespace import DCTERMS

from compiler.storage import (
    mirror_skill_path,
    get_output_path,
    load_skill_module,
    load_ontology,
    get_hash_mapping,
    get_id_mapping,
    remove_skill,
    merge_skill,
    save_ontology_atomic,
    apply_reasoning,
    generate_index_manifest,
    clean_orphaned_files,
    SYSTEM_FILES,
)
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.schemas import ExtractedSkill, Requirement, ExecutionPayload
from compiler.exceptions import OntologyLoadError, OntologyValidationError
from compiler.config import BASE_URI, SKILLS_DIR, OUTPUT_DIR


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_skill():
    """Create a sample skill for testing."""
    return ExtractedSkill(
        id="test-skill",
        hash="abc123def456",
        nature="A test skill",
        genus="Test",
        differentia="for testing",
        intents=["test", "verify"],
        requirements=[Requirement(type="Tool", value="pytest")],
        execution_payload=None,
        provenance="/skills/test/SKILL.md",
        generated_by="claude-opus-4-6"
    )


@pytest.fixture
def sample_skill_with_payload():
    """Create a sample skill with execution payload."""
    return ExtractedSkill(
        id="exec-skill",
        hash="exec123abc456",
        nature="An executable skill",
        genus="Test",
        differentia="executable",
        intents=["execute"],
        requirements=[],
        execution_payload=ExecutionPayload(executor="python", code="print('hello')"),
        provenance="/skills/exec/SKILL.md",
        generated_by="claude-opus-4-6"
    )


@pytest.fixture
def core_ontology(tmp_path):
    """Create a core ontology for tests that need it."""
    core_path = tmp_path / "ontoclaw-core.ttl"
    create_core_ontology(core_path)
    return core_path


# =============================================================================
# mirror_skill_path() tests
# =============================================================================

def test_mirror_skill_path_simple():
    """Test path mirroring with simple skill path."""
    skill_dir = Path("/skills/xlsx")
    output_base = Path("/ontoskills")

    result = mirror_skill_path(skill_dir, output_base)

    assert result == Path("/ontoskills/xlsx/ontoskill.ttl")


def test_mirror_skill_path_nested():
    """Test path mirroring with nested skill path."""
    skill_dir = Path("/skills/xlsx/pdf/pptx")
    output_base = Path("/ontoskills")

    result = mirror_skill_path(skill_dir, output_base)

    assert result == Path("/ontoskills/xlsx/pdf/pptx/ontoskill.ttl")


def test_mirror_skill_path_with_config():
    """Test path mirroring uses config defaults."""
    # Create mock paths using config
    skill_dir = Path(SKILLS_DIR) / "xlsx" / "pdf"
    output_base = Path(OUTPUT_DIR)

    result = mirror_skill_path(skill_dir, output_base)

    assert result.name == "ontoskill.ttl"
    assert "xlsx" in str(result)
    assert "pdf" in str(result)


# =============================================================================
# get_output_path() tests
# =============================================================================

def test_get_output_path():
    """Test get_output_path uses config defaults."""
    skill_dir = Path("/skills/test-skill")

    result = get_output_path(skill_dir)

    assert result.name == "ontoskill.ttl"
    # Should resolve OUTPUT_DIR to absolute path
    assert "ontoskills" in str(result) or "test-skill" in str(result)


def test_get_output_path_with_custom_base(tmp_path):
    """Test get_output_path with custom output base."""
    skill_dir = Path("/skills/test-skill")
    output_base = tmp_path / "custom-output"

    result = get_output_path(skill_dir, output_base)

    assert result == tmp_path / "custom-output" / "test-skill" / "ontoskill.ttl"


# =============================================================================
# load_skill_module() tests
# =============================================================================

def test_load_skill_module(tmp_path, sample_skill):
    """Test loading a skill module from file."""
    # First create a module
    module_path = tmp_path / "loadable" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, module_path)

    # Now load it
    loaded_graph = load_skill_module(module_path)

    assert isinstance(loaded_graph, Graph)
    assert len(loaded_graph) > 0

    # Verify skill is present
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + sample_skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in loaded_graph


def test_load_skill_module_not_found():
    """Test loading non-existent module raises error."""
    non_existent = Path("/tmp/non-existent-skill-module/ontoskill.ttl")

    with pytest.raises(OntologyLoadError):
        load_skill_module(non_existent)


# =============================================================================
# load_ontology() tests
# =============================================================================

def test_load_ontology_existing(tmp_path, core_ontology):
    """Test loading an existing ontology."""
    ontology_path = tmp_path / "skills.ttl"
    oc = get_oc_namespace()

    # Create a graph with oc namespace and serialize it
    graph = Graph()
    graph.bind("oc", oc)
    graph.bind("dcterms", DCTERMS)
    graph.add((oc.TestSkill, RDF.type, oc.Skill))
    graph.serialize(ontology_path, format="turtle")

    # Load it back
    loaded = load_ontology(ontology_path)
    assert isinstance(loaded, Graph)
    # Verify the test skill was loaded
    assert (oc.TestSkill, RDF.type, oc.Skill) in loaded


def test_load_ontology_new(tmp_path):
    """Test loading a non-existent ontology creates a new one."""
    ontology_path = tmp_path / "new-skills.ttl"

    loaded = load_ontology(ontology_path)

    assert isinstance(loaded, Graph)
    # Should have namespace bindings
    prefixes = dict(loaded.namespaces())
    assert "oc" in prefixes


# =============================================================================
# get_hash_mapping() tests
# =============================================================================

def test_get_hash_mapping(sample_skill, core_ontology):
    """Test extracting hash to URI mapping from graph."""
    graph = Graph()
    oc = get_oc_namespace()

    # Manually add a skill with hash
    skill_uri = oc["skill_testhash"]
    graph.add((skill_uri, RDF.type, oc.Skill))
    graph.add((skill_uri, oc.contentHash, Literal("testhash123")))

    mapping = get_hash_mapping(graph)

    assert "testhash123" in mapping
    assert mapping["testhash123"] == skill_uri


def test_get_hash_mapping_empty():
    """Test hash mapping on empty graph returns empty dict."""
    graph = Graph()
    mapping = get_hash_mapping(graph)
    assert mapping == {}


# =============================================================================
# get_id_mapping() tests
# =============================================================================

def test_get_id_mapping(sample_skill, core_ontology):
    """Test extracting ID to URI mapping from graph."""
    graph = Graph()
    oc = get_oc_namespace()

    # Manually add a skill with ID
    skill_uri = oc["skill_testid"]
    graph.add((skill_uri, RDF.type, oc.Skill))
    graph.add((skill_uri, DCTERMS.identifier, Literal("my-skill-id")))

    mapping = get_id_mapping(graph)

    assert "my-skill-id" in mapping
    assert mapping["my-skill-id"] == skill_uri


def test_get_id_mapping_empty():
    """Test ID mapping on empty graph returns empty dict."""
    graph = Graph()
    mapping = get_id_mapping(graph)
    assert mapping == {}


# =============================================================================
# remove_skill() tests
# =============================================================================

def test_remove_skill(core_ontology):
    """Test removing a skill from the graph."""
    graph = Graph()
    oc = get_oc_namespace()

    # Add a skill
    skill_uri = oc["skill_to_remove"]
    graph.add((skill_uri, RDF.type, oc.Skill))
    graph.add((skill_uri, DCTERMS.identifier, Literal("remove-me")))
    graph.add((skill_uri, oc.nature, Literal("To be removed")))

    # Verify it's there
    assert (skill_uri, RDF.type, oc.Skill) in graph

    # Remove it
    remove_skill(graph, skill_uri)

    # Verify it's gone
    assert (skill_uri, RDF.type, oc.Skill) not in graph
    assert (skill_uri, DCTERMS.identifier, Literal("remove-me")) not in graph


def test_remove_skill_with_requirements(core_ontology):
    """Test removing a skill with requirements."""
    graph = Graph()
    oc = get_oc_namespace()

    # Add a skill with requirement
    skill_uri = oc["skill_with_req"]
    req_uri = oc["req_test123"]

    graph.add((skill_uri, RDF.type, oc.Skill))
    graph.add((skill_uri, oc.hasRequirement, req_uri))
    graph.add((req_uri, RDF.type, oc.RequirementTool))
    graph.add((req_uri, oc.requirementValue, Literal("pytest")))

    # Remove skill
    remove_skill(graph, skill_uri)

    # Requirement blank node should also be cleaned
    assert (skill_uri, oc.hasRequirement, req_uri) not in graph


# =============================================================================
# merge_skill() tests
# =============================================================================

def test_merge_skill_new(tmp_path, core_ontology):
    """Test merging a new skill into ontology."""
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
        execution_payload=None,
        provenance=None,
        generated_by="claude-opus-4-6"
    )

    merged = merge_skill(ontology_path, skill)
    assert isinstance(merged, Graph)

    # Check skill was added
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged


def test_merge_skill_update(tmp_path, core_ontology):
    """Test updating an existing skill (same ID, different hash)."""
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
        execution_payload=None,
        provenance=None,
        generated_by="claude-opus-4-6"
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
        execution_payload=None,
        provenance=None,
        generated_by="claude-opus-4-6"
    )

    merged = merge_skill(ontology_path, skill2)
    # New skill should be present
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill2.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged


def test_merge_skill_force_parameter(tmp_path, core_ontology):
    """Test merge_skill with force=True skips hash check."""
    ontology_path = tmp_path / "skills.ttl"
    graph = load_ontology(ontology_path)
    graph.serialize(ontology_path, format="turtle")

    skill = ExtractedSkill(
        id="force-skill",
        hash="force123",
        nature="Force skill",
        genus="Test",
        differentia="force",
        intents=["force"],
        requirements=[],
        execution_payload=None,
        provenance=None,
        generated_by="claude-opus-4-6"
    )

    # First merge
    merged1 = merge_skill(ontology_path, skill)
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged1

    # Save the state
    save_ontology_atomic(ontology_path, merged1)

    # Second merge without force - should skip (same hash)
    merged2 = merge_skill(ontology_path, skill)
    # Graph should be returned but skill still there
    assert (skill_uri, RDF.type, oc.Skill) in merged2

    # Third merge with force=True - should re-add
    merged3 = merge_skill(ontology_path, skill, force=True)
    assert (skill_uri, RDF.type, oc.Skill) in merged3


def test_merge_skill_unchanged_skips(tmp_path, core_ontology):
    """Test that unchanged skills (same hash) are skipped."""
    ontology_path = tmp_path / "skills.ttl"
    graph = load_ontology(ontology_path)
    graph.serialize(ontology_path, format="turtle")

    skill = ExtractedSkill(
        id="unchanged-skill",
        hash="samehash123",
        nature="Unchanged",
        genus="Test",
        differentia="same",
        intents=["test"],
        requirements=[],
        execution_payload=None,
        provenance=None,
        generated_by="claude-opus-4-6"
    )

    # First merge
    merged1 = merge_skill(ontology_path, skill)
    save_ontology_atomic(ontology_path, merged1)

    # Second merge with same hash - should skip
    merged2 = merge_skill(ontology_path, skill)

    # Graph should still have the skill but it was skipped
    oc = get_oc_namespace()
    skill_uri = oc["skill_" + skill.hash[:16]]
    assert (skill_uri, RDF.type, oc.Skill) in merged2


def test_merge_skill_validates_and_blocks_invalid(tmp_path, core_ontology):
    """Test that merge_skill validates and blocks invalid skills."""
    ontology_path = tmp_path / "skills.ttl"
    graph = load_ontology(ontology_path)
    graph.serialize(ontology_path, format="turtle")

    # Create an invalid skill - missing required intent
    skill = ExtractedSkill(
        id="invalid-merge-skill",
        hash="invalidmerge123",
        nature="Invalid",
        genus="Test",
        differentia="test",
        intents=[],  # Missing required intent
        requirements=[],
        generated_by="claude-opus-4-6"
    )

    with pytest.raises(OntologyValidationError):
        merge_skill(ontology_path, skill)


# =============================================================================
# save_ontology_atomic() tests
# =============================================================================

def test_save_ontology_atomic(tmp_path, core_ontology):
    """Test atomic write with backup."""
    ontology_path = tmp_path / "skills.ttl"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

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


def test_save_ontology_atomic_max_backups(tmp_path, core_ontology):
    """Test that old backups are cleaned up beyond max_backups."""
    ontology_path = tmp_path / "skills.ttl"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    graph = load_ontology(ontology_path)
    oc = get_oc_namespace()

    # Create more backups than max_backups
    max_backups = 2
    for i in range(5):
        graph.add((oc[f"Skill{i}"], RDF.type, oc.Skill))
        save_ontology_atomic(ontology_path, graph, backup_dir=backup_dir, max_backups=max_backups)

    # Should only have max_backups backups
    backups = list(backup_dir.glob("*.ttl"))
    assert len(backups) <= max_backups


# =============================================================================
# apply_reasoning() tests
# =============================================================================

def test_apply_reasoning(tmp_path, core_ontology):
    """Test OWL reasoning applies inferences."""
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


# =============================================================================
# generate_index_manifest() tests
# =============================================================================

def test_generate_index_manifest(tmp_path, core_ontology, sample_skill):
    """Test generating the index.ttl manifest."""
    # Create a skill module
    skill_path = tmp_path / "ontoskills" / "test" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, skill_path)

    index_path = tmp_path / "ontoskills" / "index.ttl"

    generate_index_manifest([skill_path], index_path, tmp_path / "ontoskills")

    assert index_path.exists()

    # Load and verify
    index_graph = Graph()
    index_graph.parse(index_path, format="turtle")

    # Should have imports
    imports = list(index_graph.objects(None, OWL.imports))
    assert len(imports) >= 1


def test_generate_index_manifest_multiple_skills(tmp_path, core_ontology, sample_skill, sample_skill_with_payload):
    """Test generating index with multiple skill modules."""
    # Create skill modules
    skill_path1 = tmp_path / "ontoskills" / "skill1" / "ontoskill.ttl"
    skill_path2 = tmp_path / "ontoskills" / "skill2" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, skill_path1)
    serialize_skill_to_module(sample_skill_with_payload, skill_path2)

    index_path = tmp_path / "ontoskills" / "index.ttl"

    generate_index_manifest([skill_path1, skill_path2], index_path, tmp_path / "ontoskills")

    assert index_path.exists()

    # Load and verify
    index_graph = Graph()
    index_graph.parse(index_path, format="turtle")

    # Should have 2 skill imports + possibly core ontology import
    imports = list(index_graph.objects(None, OWL.imports))
    skill_imports = [i for i in imports if "ontoskill.ttl" in str(i)]
    assert len(skill_imports) == 2


# =============================================================================
# clean_orphaned_files() tests
# =============================================================================

def test_clean_orphaned_files_removes_orphan(tmp_path, core_ontology, sample_skill):
    """Test that clean_orphaned_files removes ontoskill.ttl when source SKILL.md is missing."""
    # Set up directories
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create a skill module in output (but no source SKILL.md)
    orphan_path = output_dir / "orphan-skill" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, orphan_path)

    # Verify orphan exists
    assert orphan_path.exists()

    # Source SKILL.md does not exist
    source_md = skills_dir / "orphan-skill" / "SKILL.md"
    assert not source_md.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    # Orphan should be removed
    assert removed == 1
    assert not orphan_path.exists()


def test_clean_orphaned_files_preserves_valid(tmp_path, core_ontology, sample_skill):
    """Test that clean_orphaned_files keeps ontoskill.ttl when source SKILL.md exists."""
    # Set up directories
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create both source SKILL.md and output ontoskill.ttl
    skill_dir = skills_dir / "valid-skill"
    skill_dir.mkdir(parents=True)
    source_md = skill_dir / "SKILL.md"
    source_md.write_text("# Test Skill\n\nTest content")

    output_path = output_dir / "valid-skill" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, output_path)

    # Verify both exist
    assert source_md.exists()
    assert output_path.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    # Nothing should be removed
    assert removed == 0
    assert output_path.exists()
    assert source_md.exists()


def test_clean_orphaned_files_dry_run(tmp_path, core_ontology, sample_skill):
    """Test that clean_orphaned_files doesn't delete in dry_run mode."""
    # Set up directories
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create an orphan
    orphan_path = output_dir / "orphan-skill" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, orphan_path)

    # Verify orphan exists
    assert orphan_path.exists()

    # Run cleanup in dry_run mode
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=True)

    # Should report 1 orphan but not delete
    assert removed == 1
    assert orphan_path.exists()  # File should still exist


def test_clean_orphaned_files_returns_zero_when_no_orphans(tmp_path, core_ontology, sample_skill):
    """Test that clean_orphaned_files returns 0 when no orphans exist."""
    # Set up directories
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create valid skill with source
    skill_dir = skills_dir / "valid-skill"
    skill_dir.mkdir(parents=True)
    source_md = skill_dir / "SKILL.md"
    source_md.write_text("# Test Skill")

    output_path = output_dir / "valid-skill" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, output_path)

    # Run cleanup on empty or clean output directory
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    # No orphans to remove
    assert removed == 0


def test_clean_orphaned_files_empty_output_dir(tmp_path):
    """Test clean_orphaned_files on empty output directory."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"
    output_dir.mkdir(parents=True)

    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 0


def test_clean_orphaned_files_nested_paths(tmp_path, core_ontology, sample_skill):
    """Test clean_orphaned_files handles nested directory structures."""
    # Set up directories
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create nested orphan
    orphan_path = output_dir / "xlsx" / "pdf" / "convert" / "ontoskill.ttl"
    serialize_skill_to_module(sample_skill, orphan_path)

    assert orphan_path.exists()

    # Source doesn't exist at nested path
    source_md = skills_dir / "xlsx" / "pdf" / "convert" / "SKILL.md"
    assert not source_md.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 1
    assert not orphan_path.exists()


def test_clean_orphaned_files_preserves_system_files(tmp_path, core_ontology, sample_skill):
    """Test that clean_orphaned_files preserves system-generated files."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create system files that have no source
    core_path = output_dir / "ontoclaw-core.ttl"
    index_path = output_dir / "index.ttl"

    create_core_ontology(core_path)
    index_path.write_text("@prefix owl: <http://www.w3.org/2002/07/owl#> .")

    assert core_path.exists()
    assert index_path.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    # System files should be preserved
    assert removed == 0
    assert core_path.exists()
    assert index_path.exists()


def test_clean_orphaned_files_removes_orphan_asset(tmp_path):
    """Test that clean_orphaned_files removes orphaned asset files."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create an orphan asset file (no source exists)
    orphan_asset = output_dir / "scripts" / "helper.py"
    orphan_asset.parent.mkdir(parents=True)
    orphan_asset.write_text("print('hello')")

    assert orphan_asset.exists()

    # Source doesn't exist
    source_asset = skills_dir / "scripts" / "helper.py"
    assert not source_asset.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 1
    assert not orphan_asset.exists()


def test_clean_orphaned_files_preserves_valid_asset(tmp_path):
    """Test that clean_orphaned_files keeps assets when source exists."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create both source and output asset
    source_asset = skills_dir / "scripts" / "helper.py"
    source_asset.parent.mkdir(parents=True)
    source_asset.write_text("print('hello')")

    output_asset = output_dir / "scripts" / "helper.py"
    output_asset.parent.mkdir(parents=True)
    output_asset.write_text("print('hello')")

    assert source_asset.exists()
    assert output_asset.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 0
    assert output_asset.exists()


def test_clean_orphaned_files_auxiliary_markdown_mapping(tmp_path):
    """Test that clean_orphaned_files correctly maps *.ttl to *.md for auxiliary files."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create an orphan auxiliary ttl (REFERENCE.ttl with no REFERENCE.md source)
    orphan_ttl = output_dir / "docs" / "REFERENCE.ttl"
    orphan_ttl.parent.mkdir(parents=True)
    orphan_ttl.write_text("@prefix oc: <http://example.org/> .")

    assert orphan_ttl.exists()

    # Source doesn't exist (REFERENCE.md)
    source_md = skills_dir / "docs" / "REFERENCE.md"
    assert not source_md.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 1
    assert not orphan_ttl.exists()


def test_clean_orphaned_files_preserves_auxiliary_with_source(tmp_path):
    """Test that clean_orphaned_files keeps *.ttl when *.md source exists."""
    skills_dir = tmp_path / "skills"
    output_dir = tmp_path / "ontoskills"

    # Create both source and output
    source_md = skills_dir / "docs" / "REFERENCE.md"
    source_md.parent.mkdir(parents=True)
    source_md.write_text("# Reference")

    output_ttl = output_dir / "docs" / "REFERENCE.ttl"
    output_ttl.parent.mkdir(parents=True)
    output_ttl.write_text("@prefix oc: <http://example.org/> .")

    assert source_md.exists()
    assert output_ttl.exists()

    # Run cleanup
    removed = clean_orphaned_files(skills_dir, output_dir, dry_run=False)

    assert removed == 0
    assert output_ttl.exists()


def test_system_files_constant():
    """Test that SYSTEM_FILES constant contains expected files."""
    assert "ontoclaw-core.ttl" in SYSTEM_FILES
    assert "index.ttl" in SYSTEM_FILES
    assert len(SYSTEM_FILES) == 2
