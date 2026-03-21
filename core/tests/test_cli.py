import pytest
from click.testing import CliRunner


def test_cli_version():
    """Test CLI version command - reads from pyproject.toml."""
    from cli import cli, __version__
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    # Version should match what's in pyproject.toml
    assert __version__ in result.output


def test_cli_help():
    """Test CLI help command."""
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert "compile" in result.output
    assert "query" in result.output
    assert "list-skills" in result.output
    assert "init-core" in result.output


def test_init_core_command(tmp_path):
    """Test init-core command creates core ontology."""
    from cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"
    result = runner.invoke(cli, ['init-core', '-o', str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "ontoskills-core.ttl").exists()
    assert "created core ontology" in result.output.lower()


def test_init_core_idempotent(tmp_path):
    """Test that init-core doesn't overwrite existing core without --force."""
    from cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"

    # First run
    result1 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    assert result1.exit_code == 0

    core_path = output_dir / "ontoskills-core.ttl"
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
    from cli import cli
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
    from cli import cli
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
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'list-skills',
        '-o', str(tmp_path / 'nonexistent.ttl')
    ])

    assert "not found" in result.output.lower()


def test_security_audit_no_skills(tmp_path):
    """Test security-audit with no skills directory."""
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, [
        'security-audit',
        '-i', str(tmp_path / 'nonexistent')
    ])

    assert "not found" in result.output.lower()


def test_diff_command_in_help():
    """Test that the diff command is listed in the CLI help output."""
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'diff' in result.output


def test_diff_no_snapshot(tmp_path):
    """Test that diff fails gracefully when no snapshot exists."""
    from cli import cli
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
    from cli import cli
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
    from cli import cli
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
    from cli import cli
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
    from cli import cli
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
    from cli import cli
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
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['compile', '--help'])

    assert result.exit_code == 0
    assert '--force' in result.output or '-f' in result.output
    # Check for the help text describing the force flag
    assert 'force' in result.output.lower()


def test_force_flag_bypasses_hash(tmp_path):
    """Test that --force flag bypasses hash check and triggers recompilation."""
    from unittest.mock import patch, MagicMock
    from cli import cli
    from compiler.extractor import compute_skill_hash
    from compiler.config import BASE_URI

    # Create a skill directory with SKILL.md
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("# Test Skill\n\nThis is a test skill.", encoding="utf-8")

    # Create output directory with an existing ontoskill.ttl that has matching hash
    output_dir = tmp_path / "output"
    output_skill_dir = output_dir / "test-skill"
    output_skill_dir.mkdir(parents=True)
    output_skill_path = output_skill_dir / "ontoskill.ttl"

    # Create a fake existing skill with the same hash
    # Use the correct namespace from config
    skill_hash = compute_skill_hash(skill_dir)
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
    core_path = output_dir / "ontoskills-core.ttl"
    core_path.parent.mkdir(parents=True, exist_ok=True)
    core_path.write_text(f"@prefix oc: <{BASE_URI}> .", encoding="utf-8")

    runner = CliRunner()

    # Create mock for extracted skill
    mock_extracted = MagicMock()
    mock_extracted.id = "test-skill"
    mock_extracted.nature = "Extracted skill"
    mock_extracted.genus = "action"
    mock_extracted.intents = ["test"]
    mock_extracted.state_transitions.requires_state = []
    mock_extracted.state_transitions.yields_state = []

    with patch('cli.tool_use_loop') as mock_tool_use_loop, \
         patch('cli.serialize_skill_to_module'):
        mock_tool_use_loop.return_value = mock_extracted

        # Without --force, the hash matches and tool_use_loop should NOT be called
        result_no_force = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '-y'  # Skip confirmation
        ])

        assert result_no_force.exit_code == 0
        # tool_use_loop should NOT have been called since hash matches
        assert mock_tool_use_loop.call_count == 0

        # Reset the mock
        mock_tool_use_loop.reset_mock()

        # With --force, tool_use_loop SHOULD be called even though hash matches
        result_with_force = runner.invoke(cli, [
            'compile',
            '-i', str(tmp_path / "skills"),
            '-o', str(output_dir),
            '--force',
            '-y'  # Skip confirmation
        ])

        assert result_with_force.exit_code == 0
        # tool_use_loop SHOULD have been called with --force
        assert mock_tool_use_loop.call_count == 1


def test_infer_parent_skill_id_from_nested_skill_path(tmp_path):
    """Nested skills should inherit from the nearest ancestor skill directory."""
    from cli import infer_parent_skill_id

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
    from cli import enrich_extracted_skill
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
    from cli import enrich_extracted_skill
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
    def test_export_embeddings_command(self, tmp_path):
        """export-embeddings command creates output files."""
        from rdflib import Graph, Namespace, Literal, RDF
        from cli import cli

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
