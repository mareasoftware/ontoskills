import pytest
from click.testing import CliRunner


def test_cli_version():
    """Test CLI version command."""
    from cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "0.2.0" in result.output


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
    output_dir = tmp_path / "semantic-skills"
    result = runner.invoke(cli, ['init-core', '-o', str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "ontoclaw-core.ttl").exists()
    assert "created core ontology" in result.output.lower()


def test_init_core_idempotent(tmp_path):
    """Test that init-core doesn't overwrite existing core without --force."""
    from cli import cli
    runner = CliRunner()
    output_dir = tmp_path / "semantic-skills"

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
