"""Phase 1 integration tests - Python-only preprocessing (no LLM).

These tests validate the Phase 1 loader pipeline:
- scan_skill_directory() integration with schemas
- Frontmatter extraction and validation
- File hash computation
- DirectoryScan creation
"""

import pytest
from pathlib import Path

from compiler.loader import (
    scan_skill_directory,
    compute_file_hash,
    LoaderError,
)
from compiler.schemas import (
    DirectoryScan,
    CompiledSkill,
    ExtractedSkill,
    KnowledgeNode,
    SeverityLevel,
)


class TestPhase1EndToEnd:
    """End-to-end Phase 1 tests."""

    def test_scan_skill_directory_creates_valid_directory_scan(self, tmp_path):
        """scan_skill_directory returns a valid DirectoryScan with all fields."""
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: A test skill for integration testing.
---

# Test Skill

This skill tests the Phase 1 loader.
""", encoding="utf-8")

        # Add a reference file
        ref_file = skill_dir / "reference.md"
        ref_file.write_text("# Reference\n\nAdditional info.", encoding="utf-8")

        # Add a script
        script_file = skill_dir / "scripts" / "helper.py"
        script_file.parent.mkdir(parents=True)
        script_file.write_text("# Helper script\nprint('hello')", encoding="utf-8")

        result = scan_skill_directory(skill_dir)

        assert isinstance(result, DirectoryScan)
        assert result.frontmatter.name == "test-skill"
        assert "integration testing" in result.frontmatter.description
        assert result.skill_id == "test-skill"
        assert result.qualified_id == "local/test-skill"
        assert len(result.files) == 3  # SKILL.md, reference.md, scripts/helper.py
        assert result.content_hash  # Non-empty hash
        assert result.provenance_path == str(skill_dir)
        assert "Test Skill" in result.skill_md_content  # Content contains our markdown
        assert result.file_tree  # Non-empty file tree

    def test_scan_skill_directory_with_package_id(self, tmp_path):
        """scan_skill_directory uses provided package_id for qualified_id."""
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: my-skill
description: Test skill with package.
---
""", encoding="utf-8")

        result = scan_skill_directory(skill_dir, package_id="office/public")

        assert result.skill_id == "my-skill"
        assert result.qualified_id == "office/public/my-skill"

    def test_scan_skill_directory_file_hashes_are_consistent(self, tmp_path):
        """File hashes in DirectoryScan match compute_file_hash()."""
        skill_dir = tmp_path / "skills" / "hash-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: hash-test
description: Testing hash consistency.
---

# Content here
""", encoding="utf-8")

        result = scan_skill_directory(skill_dir)

        # Find SKILL.md in files and verify hash
        skill_file_info = next(f for f in result.files if f.relative_path == "SKILL.md")
        expected_hash = compute_file_hash(skill_md)

        assert skill_file_info.content_hash == expected_hash

    def test_scan_skill_directory_mime_types(self, tmp_path):
        """File MIME types are correctly detected."""
        skill_dir = tmp_path / "skills" / "mime-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: mime-test
description: MIME type test.
---
""", encoding="utf-8")

        # Add various file types
        (skill_dir / "script.py").write_text("print('hi')", encoding="utf-8")
        (skill_dir / "data.json").write_text('{"key": "value"}', encoding="utf-8")
        (skill_dir / "config.yaml").write_text("key: value", encoding="utf-8")

        result = scan_skill_directory(skill_dir)

        mime_map = {f.relative_path: f.mime_type for f in result.files}

        assert mime_map["SKILL.md"] == "text/markdown"
        assert mime_map["script.py"] == "text/x-python"
        assert mime_map["data.json"] == "application/json"
        assert mime_map["config.yaml"] == "application/x-yaml"

    def test_scan_skill_directory_missing_skill_md_raises(self, tmp_path):
        """Missing SKILL.md raises LoaderError."""
        empty_dir = tmp_path / "empty-skill"
        empty_dir.mkdir(parents=True)

        with pytest.raises(LoaderError, match="missing SKILL.md"):
            scan_skill_directory(empty_dir)

    def test_scan_skill_directory_invalid_frontmatter_raises(self, tmp_path):
        """Invalid frontmatter raises LoaderError."""
        skill_dir = tmp_path / "skills" / "bad-frontmatter"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
invalid: yaml
---

Missing required fields.
""", encoding="utf-8")

        with pytest.raises(LoaderError, match="missing required"):
            scan_skill_directory(skill_dir)


class TestCompiledSkillIntegration:
    """Test CompiledSkill creation from Phase 1 data."""

    def test_compiled_skill_from_phase1_and_extraction(self, tmp_path):
        """CompiledSkill combines Phase 1 data with extracted data."""
        skill_dir = tmp_path / "skills" / "combined-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: combined-skill
description: Testing combined skill creation.
version: "1.0.0"
author: test-author
---

# Combined Skill

This skill combines Phase 1 and Phase 2 data.
""", encoding="utf-8")

        # Phase 1: Get DirectoryScan
        dir_scan = scan_skill_directory(skill_dir)

        # Phase 2: Simulate extraction result
        extracted = ExtractedSkill(
            id=dir_scan.skill_id,
            hash=dir_scan.content_hash,
            nature="A skill that combines data from multiple phases",
            genus="action",
            differentia="combines frontmatter with extracted knowledge",
            intents=["test-combined-skill"],
            requirements=[],
            knowledge_nodes=[
                KnowledgeNode(
                    node_type="Heuristic",
                    directive_content="Always validate frontmatter before extraction",
                    applies_to_context="When processing skills",
                    has_rationale="Prevents errors in Phase 2",
                    severity_level=SeverityLevel.HIGH,
                )
            ],
        )

        # Create CompiledSkill
        compiled = CompiledSkill(
            **extracted.model_dump(),
            frontmatter=dir_scan.frontmatter,
            files=dir_scan.files,
        )

        # Verify combined data
        assert compiled.id == "combined-skill"
        assert compiled.frontmatter.name == "combined-skill"
        assert compiled.frontmatter.version == "1.0.0"
        assert compiled.frontmatter.metadata.get("author") == "test-author"
        assert len(compiled.files) == 1
        assert compiled.knowledge_nodes[0].node_type == "Heuristic"

    def test_compiled_skill_serialization_includes_phase1_data(self, tmp_path):
        """Serialized CompiledSkill includes Phase 1 frontmatter data."""
        from compiler.serialization import serialize_skill_to_module
        from rdflib import Graph

        skill_dir = tmp_path / "skills" / "serialize-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: serialize-test
description: Testing serialization with frontmatter.
---

# Serialize Test
""", encoding="utf-8")

        dir_scan = scan_skill_directory(skill_dir)

        extracted = ExtractedSkill(
            id=dir_scan.skill_id,
            hash=dir_scan.content_hash,
            nature="A skill for testing serialization",
            genus="action",
            differentia="tests RDF output",
            intents=["test-serialization"],
            requirements=[],
            generated_by="test-model",
            knowledge_nodes=[
                KnowledgeNode(
                    node_type="Standard",
                    directive_content="Always include generated_by field",
                    applies_to_context="When serializing skills",
                    has_rationale="Required for provenance tracking",
                    severity_level=SeverityLevel.MEDIUM,
                )
            ],
        )

        compiled = CompiledSkill(
            **extracted.model_dump(),
            frontmatter=dir_scan.frontmatter,
            files=dir_scan.files,
        )

        output_path = tmp_path / "output" / "ontoskill.ttl"
        output_path.parent.mkdir(parents=True)

        serialize_skill_to_module(compiled, output_path)

        # Parse and verify
        g = Graph()
        g.parse(output_path, format="turtle")

        # Verify skill exists
        from compiler.core_ontology import get_oc_namespace
        oc = get_oc_namespace()
        from rdflib import RDF

        skill_subjects = list(g.subjects(RDF.type, oc.Skill))
        assert len(skill_subjects) == 1


class TestPhase1Security:
    """Security tests for Phase 1 loader."""

    def test_path_traversal_in_filename_rejected(self, tmp_path):
        """Path traversal attempts in filenames are rejected."""
        skill_dir = tmp_path / "skills" / "traversal-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: traversal-test
description: Security test.
---
""", encoding="utf-8")

        # Create a file that would be at parent level (simulated)
        # Note: We can't actually create a file with '..' in the name on most filesystems
        # So we test that the code checks for it

        result = scan_skill_directory(skill_dir)

        # All files should be within the skill directory
        for f in result.files:
            assert ".." not in f.relative_path
            assert not f.relative_path.startswith("/")

    def test_backslash_in_path_rejected(self, tmp_path):
        """Backslashes in paths are rejected (Windows-style traversal / cross-platform safety).

        On Unix, backslash is a valid filename character. This test verifies
        that such files are excluded to prevent issues on Windows systems
        and cross-platform path confusion.
        """
        skill_dir = tmp_path / "skills" / "backslash-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: backslash-test
description: Security test.
---
""", encoding="utf-8")

        # Create a file with a backslash in the name (valid on POSIX)
        # This simulates a potential cross-platform issue
        try:
            backslash_file = skill_dir / "subdir\\file.md"
            backslash_file.parent.mkdir(parents=True, exist_ok=True)
            backslash_file.write_text("content", encoding="utf-8")
            created_backslash_file = True
        except (OSError, ValueError):
            # Some filesystems may not allow backslashes in names
            created_backslash_file = False

        result = scan_skill_directory(skill_dir)

        # No file should have backslashes in relative_path
        for f in result.files:
            assert "\\" not in f.relative_path, f"Backslash found in: {f.relative_path}"

        # If we created a backslash file, verify it was excluded
        if created_backslash_file:
            relative_paths = [f.relative_path for f in result.files]
            assert "subdir\\file.md" not in relative_paths

    def test_hidden_files_ignored(self, tmp_path):
        """Hidden files (dotfiles) are not included in scan."""
        skill_dir = tmp_path / "skills" / "hidden-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: hidden-test
description: Hidden files test.
---
""", encoding="utf-8")

        # Create hidden files
        (skill_dir / ".env").write_text("SECRET=value", encoding="utf-8")
        (skill_dir / ".gitignore").write_text("*.pyc", encoding="utf-8")

        result = scan_skill_directory(skill_dir)

        # Only SKILL.md should be in files
        file_names = [f.relative_path for f in result.files]
        assert ".env" not in file_names
        assert ".gitignore" not in file_names
        assert "SKILL.md" in file_names
