import pytest
from click.testing import CliRunner


def test_cli_version():
    """Test CLI version command."""
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "0.4.0" in result.output


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
    assert (output_dir / "ontoclaw-core.ttl").exists()
    assert "created core ontology" in result.output.lower()


def test_init_core_idempotent(tmp_path):
    """Test that init-core doesn't overwrite existing core without --force."""
    from cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"

    # First run
    result1 = runner.invoke(cli, ['init-core', '-o', str(output_dir)])
    assert result1.exit_code == 0

    core_path = output_dir / "ontoclaw-core.ttl"
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
    core_path = output_dir / "ontoclaw-core.ttl"
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
