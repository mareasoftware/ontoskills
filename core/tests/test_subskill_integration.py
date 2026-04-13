"""
Integration tests for sub-skill compilation.

These tests verify the complete flow from .md files to .ttl output
with proper extends relationships.
"""

import pytest
from click.testing import CliRunner


@pytest.fixture
def skill_with_subskills(tmp_path):
    """Create a skill directory with SKILL.md and sub-skills."""
    skill_dir = tmp_path / "skills" / "integration-test"
    skill_dir.mkdir(parents=True)

    # Parent skill
    (skill_dir / "SKILL.md").write_text("""---
name: integration-test
description: A parent skill for testing sub-skill compilation.
---

# Integration Test Skill

A parent skill for testing sub-skill compilation.

## Anti-Patterns

- Don't skip validation
""")

    # Sub-skill 1
    (skill_dir / "planning.md").write_text("""
# Planning Phase

This sub-skill handles the planning phase.

It should extend the parent and may depend on setup.
""")

    # Sub-skill 2
    (skill_dir / "review.md").write_text("""
# Review Phase

This sub-skill handles the review phase.

It should extend the parent and depend on planning.
""")

    # Asset file
    (skill_dir / "diagram.png").write_bytes(b"fake png content")

    # Package manifest
    package_json = tmp_path / "skills" / "package.json"
    package_json.write_text('{"name": "test/package", "version": "1.0.0"}')

    return tmp_path


def test_subskill_qualified_ids(skill_with_subskills, tmp_path):
    """Test that sub-skills get Qualified IDs."""
    from compiler.extractor import (
        resolve_package_id,
        generate_qualified_skill_id,
        generate_sub_skill_id
    )

    skill_dir = skill_with_subskills / "skills" / "integration-test"

    # Test package resolution
    package_id = resolve_package_id(skill_dir)
    assert package_id == "test/package"

    # Test ID generation
    parent_id = generate_qualified_skill_id(package_id, "integration-test")
    assert parent_id == "test/package/integration-test"

    sub_id = generate_sub_skill_id(package_id, "integration-test", "planning.md")
    assert sub_id == "test/package/integration-test/planning"


def test_subskill_hash_independence(skill_with_subskills):
    """Test that sub-skill hashes are independent of parent."""
    from compiler.extractor import compute_sub_skill_hash

    skill_dir = skill_with_subskills / "skills" / "integration-test"

    planning_hash = compute_sub_skill_hash(skill_dir / "planning.md")
    review_hash = compute_sub_skill_hash(skill_dir / "review.md")

    # Different content = different hashes
    assert planning_hash != review_hash

    # Same content = same hash
    (skill_dir / "copy.md").write_text((skill_dir / "planning.md").read_text())
    copy_hash = compute_sub_skill_hash(skill_dir / "copy.md")
    assert copy_hash == planning_hash


# Mark as integration test (requires LLM API)
@pytest.mark.integration
def test_full_compilation_with_subskills(skill_with_subskills, tmp_path):
    """Full integration test of sub-skill compilation."""
    from compiler.cli import cli

    runner = CliRunner()
    output_dir = tmp_path / "ontoskills"

    result = runner.invoke(cli, [
        'compile',
        '-i', str(skill_with_subskills / 'skills'),
        '-o', str(output_dir),
        '--skip-security'
    ])

    # Should succeed
    assert result.exit_code == 0

    # Check output structure
    skill_output = output_dir / "integration-test"
    assert skill_output.exists()

    # Check parent skill
    assert (skill_output / "ontoskill.ttl").exists()
    parent_content = (skill_output / "ontoskill.ttl").read_text()
    assert "integration-test" in parent_content

    # Check sub-skills
    assert (skill_output / "planning.ttl").exists()
    assert (skill_output / "review.ttl").exists()

    planning_content = (skill_output / "planning.ttl").read_text()
    assert "oc:extends" in planning_content
    # Parent URI is slugified: skills/integration-test → skill_skills_integration_test
    assert "oc:skill_skills_integration_test" in planning_content

    # Check asset copy
    assert (skill_output / "diagram.png").exists()
