import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


def test_cli_version():
    """Test CLI version command - reads from pyproject.toml."""
    from compiler.cli import cli, __version__
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    # Version should match what's in pyproject.toml
    assert __version__ in result.output


def test_cli_help():
    """Test CLI help command."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert "compile" in result.output
    assert "query" in result.output
    assert "list-skills" in result.output
    assert "init-core" in result.output


def test_init_core_command(tmp_path):
    """Test init-core command creates core ontology."""
    from compiler.cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"
    result = runner.invoke(cli, ['init-core', '-o', str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "core.ttl").exists()
    assert "created core ontology" in result.output.lower()


def test_init_core_idempotent(tmp_path):
    """Test that init-core doesn't overwrite existing core without --force."""
    from compiler.cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"

    # First run
    result1 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    assert result1.exit_code == 0

    core_path = output_dir / "core.ttl"
    import hashlib
    content1 = core_path.read_text()
    hash1 = hashlib.sha256(content1.encode()).hexdigest()

    # Second run (should skip without --force)
    result2 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    content2 = core_path.read_text()
    hash2 = hashlib.sha256(content2.encode()).hexdigest()

    assert hash1 == hash2  # Content unchanged
    assert "already exists" in result2.output


def test_compile_no_skills(tmp_path):
    """Test compile with no skills directory."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'compile',
        '-i', str(tmp_path / 'nonexistent'),
        '-o', str(tmp_path / 'output')
    ])

    assert result.exit_code == 0  # Graceful exit
    assert "no skills" in result.output.lower()


def test_query_missing_ontology(tmp_path):
    """Test query with missing ontology file."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'query',
        'SELECT ?s WHERE { ?s a ?type }',
        '-o', str(tmp_path / 'nonexistent.ttl')
    ])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_list_skills_missing_ontology(tmp_path):
    """Test list-skills with missing ontology."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'list-skills',
        '-o', str(tmp_path / 'nonexistent.ttl')
    ])

    assert "not found" in result.output.lower()


def test_security_audit_no_skills(tmp_path):
    """Test security-audit with no skills directory."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'security-audit',
        '-i', str(tmp_path / 'nonexistent')
    ])

    assert "not found" in result.output.lower()


def test_diff_command_in_help():
    """Test that the diff command is listed in the CLI help output."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'diff' in result.output


def test_diff_no_snapshot(tmp_path):
    """Test that diff fails gracefully when no snapshot exists."""
    from compiler.cli import cli
    runner = CliRunner()
    # Point to a non-existent snapshot dir so get_latest_snapshot returns None
    with runner.isolated_filesystem():
        result = runner.invoke(cli, [
            'diff',
            '--to', str(tmp_path / 'nonexistent.ttl'),
        ])
    assert result.exit_code != 0
    assert 'snapshot' in result.output.lower() or 'no snapshot' in result.output.lower()


def test_diff_clean(tmp_path):
    """Test that diffing identical files reports no drift and exits 0."""
    from compiler.cli import cli
    runner = CliRunner()

    ttl_content = """
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "do_thing" .
"""
    ttl_file = tmp_path / 'skills.ttl'
    ttl_file.write_text(ttl_content)

    result = runner.invoke(cli, [
        'diff',
        '--from', str(ttl_file),
        '--to', str(ttl_file),
    ])

    assert result.exit_code == 0
    assert 'no drift' in result.output.lower() or 'consistent' in result.output.lower()


def test_diff_breaking_exits_9(tmp_path):
    """Test that breaking changes cause exit code 9."""
    from compiler.cli import cli
    runner = CliRunner()

    old_ttl = tmp_path / 'old.ttl'
    new_ttl = tmp_path / 'new.ttl'

    old_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "create_pdf" .
""")
    new_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "generate_pdf" .
""")

    result = runner.invoke(cli, [
        'diff',
        '--from', str(old_ttl),
        '--to', str(new_ttl),
    ])

    assert result.exit_code == 9


def test_diff_breaking_only_flag(tmp_path):
    """Test that --breaking-only suppresses additive changes in output."""
    from compiler.cli import cli
    runner = CliRunner()

    old_ttl = tmp_path / 'old.ttl'
    new_ttl = tmp_path / 'new.ttl'

    old_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "task_a" .
""")
    # Only an additive change: new skill added, nothing removed
    new_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "task_a" .
oc:SkillB a oc:Skill ;
    oc:resolvesIntent "task_b" .
""")

    result = runner.invoke(cli, [
        'diff',
        '--from', str(old_ttl),
        '--to', str(new_ttl),
        '--breaking-only',
    ])

    # No breaking changes, so exit 0 and summary shows 0 breaking
    assert result.exit_code == 0
    assert '0 breaking' in result.output.lower()


def test_diff_json_output(tmp_path):
    """Test that --format json writes a valid JSON drift report."""
    import json as json_mod
    from compiler.cli import cli
    runner = CliRunner()

    ttl_file = tmp_path / 'skills.ttl'
    ttl_file.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "do_thing" .
""")
    output_file = tmp_path / 'report.json'

    runner.invoke(cli, [
        'diff',
        '--from', str(ttl_file),
        '--to', str(ttl_file),
        '--format', 'json',
        '--output', str(output_file),
    ])

    assert output_file.exists()
    data = json_mod.loads(output_file.read_text())
    assert 'has_breaking' in data
    assert 'breaking' in data
    assert 'additive' in data


def test_diff_suggest_shows_migration_guidance(tmp_path):
    """--suggest should print migration guidance when breaking changes exist."""
    from compiler.cli import cli
    runner = CliRunner()

    old_ttl = tmp_path / 'old.ttl'
    new_ttl = tmp_path / 'new.ttl'
    old_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:SkillA a oc:Skill ; oc:resolvesIntent "old_intent" .
""")
    new_ttl.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:SkillA a oc:Skill ; oc:resolvesIntent "new_intent" .
""")

    result = runner.invoke(cli, [
        'diff',
        '--from', str(old_ttl),
        '--to', str(new_ttl),
        '--suggest',
    ])

    assert result.exit_code == 9
    assert 'migration' in result.output.lower() or 'action' in result.output.lower()


def test_force_flag_accepted():
    """Test that --force flag appears in compile --help output."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['compile', '--help'])

    assert result.exit_code == 0
    assert '--force' in result.output or '-f' in result.output
    # Check for the help text describing the force flag
    assert 'force' in result.output.lower()


def test_force_flag_bypasses_hash(tmp_path):
    """Test that --force flag bypasses hash check and triggers recompilation."""
    from unittest.mock import patch, MagicMock
    from compiler.cli import cli  # Use correct import path
    from compiler.loader import scan_skill_directory
    from compiler.config import BASE_URI
    import compiler.cli.compile  # Import module for patching

    # Create a skill directory with SKILL.md (with valid YAML frontmatter)
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_content = '''---
name: test-skill
description: A test skill for testing force flag.
---

# Test Skill

This is a test skill.
'''
    skill_file.write_text(skill_content, encoding="utf-8")

    # Create output directory with an existing ontoskill.ttl that has matching hash
    output_dir = tmp_path / "output"
    output_skill_dir = output_dir / "test-skill"
    output_skill_dir.mkdir(parents=True)
    output_skill_path = output_skill_dir / "ontoskill.ttl"

    # Get hash from Phase 1 loader
    dir_scan = scan_skill_directory(skill_dir)
    skill_hash = dir_scan.content_hash

    # Create a fake existing skill with the same hash
    existing_ttl = f'''
@prefix oc: <{BASE_URI}> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix skill: <{BASE_URI}skills/test-skill#> .

skill:test-skill a oc:Skill ;
    dcterms:identifier "test-skill" ;
    oc:contentHash "{skill_hash}" ;
    oc:nature "Existing skill" .
'''
    output_skill_path.write_text(existing_ttl, encoding="utf-8")

    # Create core ontology
    core_path = output_dir / "core.ttl"
    core_path.parent.mkdir(parents=True, exist_ok=True)
    core_path.write_text(f"@prefix oc: <{BASE_URI}> .", encoding="utf-8")

    runner = CliRunner()

    # Create mock for extracted skill with real list attributes
    # (MagicMock defaults would break enrich_extracted_skill which calls .append())
    mock_extracted = MagicMock()
    mock_extracted.id = "test-skill"
    mock_extracted.nature = "Extracted skill"
    mock_extracted.genus = "action"
    mock_extracted.intents = ["test"]
    mock_extracted.extends = []  # Real list for .append() in enrich_extracted_skill
    mock_extracted.depends_on = []  # Real list for filtering
    mock_extracted.state_transitions = MagicMock()
    mock_extracted.state_transitions.requires_state = []
    mock_extracted.state_transitions.yields_state = []
    mock_extracted.model_dump = MagicMock(return_value={
        "id": "test-skill",
        "hash": skill_hash,
        "nature": "Extracted skill",
        "genus": "action",
        "differentia": "test",
        "intents": ["test"],
        "requirements": [],
        "depends_on": [],
        "extends": [],
        "contradicts": [],
        "state_transitions": None,
        "generated_by": "test",
        "execution_payload": None,
        "provenance": None,
        "knowledge_nodes": [],
    })

    with patch.object(compiler.cli.compile, 'tool_use_loop') as mock_tool_use_loop, \
         patch.object(compiler.cli.compile, 'serialize_skill_to_module'), \
         patch.dict('sys.modules', {'sentence_transformers': MagicMock(SentenceTransformer=MagicMock())}), \
         patch('compiler.embeddings.exporter.export_skill_embeddings') as mock_export:
        mock_export.return_value = Path("fake/intents.json")
        mock_tool_use_loop.return_value = mock_extracted

        # First: verify baseline behavior (without --force, matching hash causes skip)
        mock_tool_use_loop.reset_mock()
        mock_extracted.model_dump.reset_mock()
        mock_extracted.reset_mock()
        mock_extracted.id = "test-skill"
        mock_extracted.nature = "Extracted skill"
        mock_extracted.genus = "action"
        mock_extracted.intents = ["test"]
        mock_extracted.extends = []  # Real list for .append() in enrich_extracted_skill
        mock_extracted.depends_on = []  # Real list for filtering
        mock_extracted.state_transitions = MagicMock()
        mock_extracted.state_transitions.requires_state = []
        mock_extracted.state_transitions.yields_state = []
        mock_extracted.model_dump = MagicMock(return_value={
            "id": "test-skill",
            "hash": skill_hash,
            "nature": "Extracted skill",
            "genus": "action",
            "differentia": "test",
            "intents": ["test"],
            "requirements": [],
            "depends_on": [],
            "extends": [],
            "contradicts": [],
            "state_transitions": None,
            "generated_by": "test",
            "execution_payload": None,
            "provenance": None,
            "knowledge_nodes": [],
        })

        # Without --force, tool_use_loop should NOT be called (hash matches)
        # Use --skip-security to avoid LLM security check in test
        result_without_force = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '--skip-security',
            '-y'  # Skip confirmation
        ])

        assert result_without_force.exit_code == 0
        # tool_use_loop should NOT have been called (hash match causes skip)
        assert mock_tool_use_loop.call_count == 0, \
            "Expected cache hit to skip extraction, but tool_use_loop was called"

        # Second: verify --force bypasses hash check
        mock_tool_use_loop.reset_mock()
        mock_extracted.model_dump.reset_mock()
        mock_extracted.reset_mock()
        mock_extracted.id = "test-skill"
        mock_extracted.nature = "Extracted skill"
        mock_extracted.genus = "action"
        mock_extracted.intents = ["test"]
        mock_extracted.extends = []  # Real list for .append() in enrich_extracted_skill
        mock_extracted.depends_on = []  # Real list for filtering
        mock_extracted.state_transitions = MagicMock()
        mock_extracted.state_transitions.requires_state = []
        mock_extracted.state_transitions.yields_state = []
        mock_extracted.model_dump = MagicMock(return_value={
            "id": "test-skill",
            "hash": skill_hash,
            "nature": "Extracted skill",
            "genus": "action",
            "differentia": "test",
            "intents": ["test"],
            "requirements": [],
            "depends_on": [],
            "extends": [],
            "contradicts": [],
            "state_transitions": None,
            "generated_by": "test",
            "execution_payload": None,
            "provenance": None,
            "knowledge_nodes": [],
        })

        # With --force, tool_use_loop SHOULD be called even though hash matches
        result_with_force = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '--force',
            '--skip-security',
            '-y'  # Skip confirmation
        ])

        assert result_with_force.exit_code == 0
        # tool_use_loop SHOULD have been called with --force
        assert mock_tool_use_loop.call_count == 1, \
            "Expected --force to bypass cache and trigger extraction"


def test_lint_command_clean(tmp_path):
    """Lint command exits 0 on a clean ontology."""
    from compiler.cli import cli
    runner = CliRunner()

    ttl_file = tmp_path / 'clean.ttl'
    ttl_file.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "do_thing" .
""")
    result = runner.invoke(cli, ['lint', str(ttl_file)])
    assert result.exit_code == 0
    assert 'no issues' in result.output.lower()


def test_lint_command_with_errors(tmp_path):
    """Lint command exits 1 when errors are found."""
    from compiler.cli import cli
    runner = CliRunner()

    ttl_file = tmp_path / 'circular.ttl'
    ttl_file.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:SkillA a oc:Skill ;
    oc:resolvesIntent "intent_a" ;
    oc:dependsOnSkill oc:SkillB .
oc:SkillB a oc:Skill ;
    oc:resolvesIntent "intent_b" ;
    oc:dependsOnSkill oc:SkillA .
""")
    result = runner.invoke(cli, ['lint', str(ttl_file)])
    assert result.exit_code == 1
    assert 'circular' in result.output.lower()


def test_lint_command_errors_only(tmp_path):
    """Lint --errors-only suppresses warnings."""
    from compiler.cli import cli
    runner = CliRunner()

    ttl_file = tmp_path / 'dead_state.ttl'
    ttl_file.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "do_thing" ;
    oc:requiresState oc:NeverYielded .
""")
    result = runner.invoke(cli, ['lint', str(ttl_file), '--errors-only'])
    # dead-state is a warning, so errors-only should find nothing
    assert result.exit_code == 0
    assert 'no issues' in result.output.lower()


def test_lint_command_json_output(tmp_path):
    """Lint --json produces valid JSON output."""
    import json as json_mod
    from compiler.cli import cli
    runner = CliRunner()

    ttl_file = tmp_path / 'skills.ttl'
    ttl_file.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:TestSkill a oc:Skill ;
    oc:resolvesIntent "do_thing" .
""")
    result = runner.invoke(cli, ['lint', str(ttl_file), '--json'])
    assert result.exit_code == 0
    data = json_mod.loads(result.output)
    assert isinstance(data, list)


def test_lint_in_help():
    """Lint command should appear in CLI help."""
    from compiler.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'lint' in result.output


def test_infer_parent_skill_id_from_nested_skill_path(tmp_path):
    """Nested skills should inherit from the nearest ancestor skill directory."""
    from compiler.cli.compile import infer_parent_skill_id

    input_dir = tmp_path / "skills"
    (input_dir / "office" / "SKILL.md").parent.mkdir(parents=True)
    (input_dir / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    (input_dir / "office" / "public" / "xlsx").mkdir(parents=True)

    parent_skill_id = infer_parent_skill_id(
        input_dir / "office" / "public" / "xlsx",
        input_dir,
    )

    assert parent_skill_id == "office"


def test_enrich_extracted_skill_adds_parent_to_extends(tmp_path):
    """Compiler should deterministically add parent inheritance for nested skills."""
    from compiler.cli.compile import enrich_extracted_skill
    from compiler.schemas import ExtractedSkill, Requirement

    input_dir = tmp_path / "skills"
    (input_dir / "office" / "SKILL.md").parent.mkdir(parents=True)
    (input_dir / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    skill_dir = input_dir / "office" / "public" / "xlsx"
    skill_dir.mkdir(parents=True)

    extracted = ExtractedSkill(
        id="xlsx",
        hash="hash",
        nature="Tool",
        genus="Spreadsheet processor",
        differentia="that edits spreadsheets",
        intents=["edit spreadsheet"],
        requirements=[Requirement(type="Tool", value="python")],
        extends=[],
    )

    enrich_extracted_skill(extracted, skill_dir, input_dir)

    assert extracted.extends == ["office"]


def test_enrich_extracted_skill_removes_parent_from_depends_on(tmp_path):
    """A parent inheritance relation should not also remain as a dependency."""
    from compiler.cli.compile import enrich_extracted_skill
    from compiler.schemas import ExtractedSkill, Requirement

    input_dir = tmp_path / "skills"
    (input_dir / "office" / "SKILL.md").parent.mkdir(parents=True)
    (input_dir / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    skill_dir = input_dir / "office" / "public" / "pptx"
    skill_dir.mkdir(parents=True)

    extracted = ExtractedSkill(
        id="pptx",
        hash="hash",
        nature="Tool",
        genus="Presentation tool",
        differentia="that edits presentations",
        intents=["edit presentation"],
        requirements=[Requirement(type="Tool", value="python")],
        depends_on=["office", "pandoc"],
        extends=[],
    )

    enrich_extracted_skill(extracted, skill_dir, input_dir)

    assert extracted.extends == ["office"]
    assert extracted.depends_on == ["pandoc"]


class TestExportEmbeddingsCLI:
    """Tests for export-embeddings CLI command."""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("sentence_transformers"),
        reason="sentence_transformers not installed"
    )
    def test_export_embeddings_command(self, tmp_path):
        """export-embeddings command creates output files."""
        from rdflib import Graph, Namespace, Literal, RDF
        from compiler.cli import cli

        OC = Namespace("https://ontoskills.sh/ontology#")
        DCTERMS = Namespace("http://purl.org/dc/terms/")

        # Create test ontology using production format with dcterms:identifier
        g = Graph()
        g.bind("oc", OC)
        g.bind("dcterms", DCTERMS)
        skill = OC["skill_test"]
        g.add((skill, RDF.type, OC.Skill))
        g.add((skill, DCTERMS.identifier, Literal("test")))  # Production format
        g.add((skill, OC.resolvesIntent, Literal("test_intent")))

        ontology_root = tmp_path / "ontoskills"
        ontology_root.mkdir()
        (ontology_root / "index.ttl").write_text(g.serialize(format="turtle"))

        output_dir = tmp_path / "output"

        runner = CliRunner()
        result = runner.invoke(cli, [
            'export-embeddings',
            '--ontology-root', str(ontology_root),
            '--output-dir', str(output_dir),
        ])

        assert result.exit_code == 0
        assert (output_dir / "intents.json").exists()


def test_compile_warns_on_orphan_sub_skills(tmp_path):
    """Compile should succeed but warn if .md files exist without SKILL.md.

    Auxiliary content directories (rules, examples, references, etc.)
    within a valid skill tree are support content, not orphans.
    """
    from compiler.cli import cli
    runner = CliRunner()

    # Create skill directory with auxiliary .md but no SKILL.md
    skill_dir = tmp_path / "skills" / "orphan-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "planning.md").write_text("# Planning")
    (skill_dir / "review.md").write_text("# Review")

    output_dir = tmp_path / "ontoskills"

    result = runner.invoke(cli, [
        'compile', 'orphan-skill',
        '-i', str(tmp_path / 'skills'),
        '-o', str(output_dir)
    ])

    # Compilation succeeds (no fatal error) — auxiliary dirs are just skipped
    assert result.exit_code == 0


def test_dry_run_does_not_write_sub_skill_modules(tmp_path):
    """Compile --dry-run should not write sub-skill .ttl files or copy assets."""
    from unittest.mock import patch, MagicMock
    from compiler.cli import cli

    # Create skill directory with SKILL.md, auxiliary .md, and an asset
    skill_dir = tmp_path / "skills" / "parent-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Parent Skill\n\nA parent skill.", encoding="utf-8")
    (skill_dir / "sub-module.md").write_text("# Sub Module\n\nA sub-skill.", encoding="utf-8")
    (skill_dir / "asset.txt").write_text("Asset content", encoding="utf-8")

    output_dir = tmp_path / "ontoskills"
    output_skill_dir = output_dir / "parent-skill"
    output_skill_dir.mkdir(parents=True)

    # Create core ontology
    core_path = output_dir / "core.ttl"
    core_path.write_text("@prefix oc: <https://ontoskills.sh/ontology#> .", encoding="utf-8")

    runner = CliRunner()

    # Mock the LLM extraction
    mock_extracted = MagicMock()
    mock_extracted.id = "parent-skill"
    mock_extracted.nature = "Test skill"
    mock_extracted.genus = "action"
    mock_extracted.intents = ["test"]
    mock_extracted.state_transitions.requires_state = []
    mock_extracted.state_transitions.yields_state = []

    mock_sub_extracted = MagicMock()
    mock_sub_extracted.id = "sub-module"
    mock_sub_extracted.nature = "Sub skill"
    mock_sub_extracted.genus = "action"
    mock_sub_extracted.intents = ["sub_test"]
    mock_sub_extracted.state_transitions.requires_state = []
    mock_sub_extracted.state_transitions.yields_state = []

    with patch('compiler.cli.compile.tool_use_loop') as mock_tool_use_loop, \
         patch.dict('sys.modules', {'sentence_transformers': MagicMock(SentenceTransformer=MagicMock())}):
        # First call for parent skill, second for sub-skill
        mock_tool_use_loop.side_effect = [mock_extracted, mock_sub_extracted]

        result = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '--dry-run'
        ])

        assert result.exit_code == 0
        assert "dry run" in result.output.lower()

        # Verify no .ttl files were created for sub-skills
        sub_skill_ttl = output_skill_dir / "sub-module.ttl"
        assert not sub_skill_ttl.exists(), "Sub-skill .ttl should not be created in dry-run"

        # Verify asset was not copied
        output_asset = output_skill_dir / "asset.txt"
        assert not output_asset.exists(), "Asset should not be copied in dry-run"

        # Verify main skill .ttl was not created either
        main_skill_ttl = output_skill_dir / "ontoskill.ttl"
        assert not main_skill_ttl.exists(), "Main skill .ttl should not be created in dry-run"
