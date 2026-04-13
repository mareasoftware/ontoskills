"""Tests for Phase 1 loader module."""

import pytest
from pathlib import Path

from compiler.loader import (
    parse_frontmatter,
    scan_skill_directory,
    LoaderError,
    DirectoryScan,
    compute_file_hash,
    mime_type_from_path,
)


class TestParseFrontmatter:
    """Tests for frontmatter parsing and validation."""

    def test_parse_frontmatter_extracts_name_and_description(self):
        content = """---
name: my-skill
description: A test skill
---
# Content"""
        result = parse_frontmatter(content)
        assert result.name == "my-skill"
        assert result.description == "A test skill"

    def test_parse_frontmatter_extracts_version(self):
        content = """---
name: my-skill
description: Test
version: "1.0.0"
---
# Content"""
        result = parse_frontmatter(content)
        assert result.version == "1.0.0"

    def test_parse_frontmatter_extracts_metadata(self):
        content = """---
name: my-skill
description: Test
author: Claude
tags:
  - pdf
  - docs
---
# Content"""
        result = parse_frontmatter(content)
        assert result.metadata["author"] == "Claude"
        assert result.metadata["tags"] == ["pdf", "docs"]

    def test_parse_frontmatter_rejects_missing_name(self):
        content = """---
description: No name
---
# Content"""
        with pytest.raises(LoaderError, match="missing required 'name'"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_missing_description(self):
        content = """---
name: test-skill
---
# Content"""
        with pytest.raises(LoaderError, match="missing required 'description'"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_missing_delimiters(self):
        content = """# Just markdown
No frontmatter here"""
        with pytest.raises(LoaderError, match="missing YAML frontmatter"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_invalid_yaml(self):
        content = """---
name: [broken
description: Test
---
# Content"""
        with pytest.raises(LoaderError, match="Invalid YAML"):
            parse_frontmatter(content)

    def test_parse_frontmatter_auto_normalizes_uppercase_name(self):
        """Uppercase names are auto-normalized to lowercase."""
        content = """---
name: InvalidName
description: Test
---
# Content"""
        result = parse_frontmatter(content)
        assert result.name == "invalidname"

    def test_parse_frontmatter_auto_normalizes_spaces_to_hyphens(self):
        """Spaces in names are auto-normalized to hyphens."""
        content = """---
name: invalid name
description: Test
---
# Content"""
        result = parse_frontmatter(content)
        assert result.name == "invalid-name"

    def test_parse_frontmatter_rejects_long_name(self):
        long_name = "a" * 65
        content = f"""---
name: {long_name}
description: Test
---
# Content"""
        with pytest.raises(LoaderError, match="exceeds 64"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_reserved_word_ontoskills(self):
        content = """---
name: ontoskills
description: Test
---
# Content"""
        with pytest.raises(LoaderError, match="reserved"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_reserved_word_index(self):
        """'index' is also a reserved word (blocks filesystem conflicts)."""
        content = """---
name: index
description: Test
---
# Content"""
        with pytest.raises(LoaderError, match="reserved"):
            parse_frontmatter(content)

    def test_parse_frontmatter_allows_compound_with_reserved_prefix(self):
        """Compound names containing reserved words are allowed (e.g. 'ontoskills-plugin')."""
        content = """---
name: ontoskills-plugin
description: Test
---
# Content"""
        result = parse_frontmatter(content)
        assert result.name == "ontoskills-plugin"

    def test_parse_frontmatter_allows_marea_helper(self):
        """'marea-helper' is not a reserved word — only full 'ontoskills' and 'index' are."""
        content = """---
name: marea-helper
description: Test
---
# Content"""
        result = parse_frontmatter(content)
        assert result.name == "marea-helper"

    def test_parse_frontmatter_rejects_long_description(self):
        long_desc = "x" * 1025
        content = f"""---
name: test-skill
description: {long_desc}
---
# Content"""
        with pytest.raises(LoaderError, match="exceeds 1024"):
            parse_frontmatter(content)

    def test_parse_frontmatter_rejects_xml_tags_in_description(self):
        content = """---
name: test-skill
description: A <b>bold</b> description
---
# Content"""
        with pytest.raises(LoaderError, match="XML/HTML tags"):
            parse_frontmatter(content)

    def test_parse_frontmatter_accepts_max_length_name(self):
        name = "a" * 64
        content = f"""---
name: {name}
description: Test
---
# Content"""
        result = parse_frontmatter(content)
        assert len(result.name) == 64

    def test_parse_frontmatter_accepts_max_length_description(self):
        desc = "x" * 1024
        content = f"""---
name: test-skill
description: {desc}
---
# Content"""
        result = parse_frontmatter(content)
        assert len(result.description) == 1024


class TestScanSkillDirectory:
    """Tests for directory scanning."""

    def test_scan_skill_directory_returns_directory_scan(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Test skill
---
# Content""")
        (skill_dir / "reference.md").write_text("# Reference")

        result = scan_skill_directory(skill_dir)
        assert isinstance(result, DirectoryScan)
        assert result.frontmatter.name == "my-skill"
        assert result.frontmatter.description == "Test skill"
        assert result.skill_id == "my-skill"
        assert len(result.files) == 2  # SKILL.md + reference.md

    def test_scan_skill_directory_computes_hashes(self, tmp_path):
        skill_dir = tmp_path / "hash-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: hash-skill
description: Test
---
# Content""")

        result = scan_skill_directory(skill_dir)
        assert result.content_hash != ""
        assert len(result.content_hash) == 64  # SHA-256 hex

    def test_scan_skill_directory_includes_file_info(self, tmp_path):
        skill_dir = tmp_path / "info-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: info-skill
description: Test
---
# Content""")
        (skill_dir / "script.py").write_text("print('hello')")

        result = scan_skill_directory(skill_dir)
        py_file = next(f for f in result.files if f.relative_path == "script.py")
        assert py_file.content_hash != ""
        assert py_file.file_size > 0
        assert py_file.mime_type == "text/x-python"

    def test_scan_skill_directory_rejects_missing_skill_md(self, tmp_path):
        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()

        with pytest.raises(LoaderError, match="missing SKILL.md"):
            scan_skill_directory(skill_dir)

    def test_scan_skill_directory_ignores_hidden_files(self, tmp_path):
        skill_dir = tmp_path / "hidden-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: hidden-skill
description: Test
---
# Content""")
        (skill_dir / ".hidden").write_text("secret")

        result = scan_skill_directory(skill_dir)
        hidden_files = [f for f in result.files if f.relative_path.startswith('.')]
        assert len(hidden_files) == 0

    def test_scan_skill_directory_rejects_path_traversal(self, tmp_path):
        skill_dir = tmp_path / "traversal-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: traversal-skill
description: Test
---
# Content""")
        # Create a file with .. in the name (edge case)
        dangerous_dir = skill_dir / "normal" / ".." / "safe"
        dangerous_dir.mkdir(parents=True, exist_ok=True)
        (dangerous_dir / "file.txt").write_text("content")

        result = scan_skill_directory(skill_dir)
        # Files with '..' in path should be excluded
        for f in result.files:
            assert '..' not in f.relative_path.split('/')

    def test_scan_skill_directory_uses_package_id(self, tmp_path):
        skill_dir = tmp_path / "pkg-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: pkg-skill
description: Test
---
# Content""")

        result = scan_skill_directory(skill_dir, package_id="myorg/mypackage")
        assert "myorg/mypackage" in result.qualified_id
        assert result.skill_id == "pkg-skill"

    def test_scan_skill_directory_builds_file_tree(self, tmp_path):
        skill_dir = tmp_path / "tree-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: tree-skill
description: Test
---
# Content""")
        (skill_dir / "ref.md").write_text("Reference")

        result = scan_skill_directory(skill_dir)
        assert "SKILL.md" in result.file_tree
        assert "ref.md" in result.file_tree


class TestComputeFileHash:
    """Tests for file hash computation."""

    def test_compute_file_hash_returns_sha256(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = compute_file_hash(test_file)
        assert len(result) == 64  # SHA-256 hex length
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_compute_file_hash_deterministic(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("same content")

        hash1 = compute_file_hash(test_file)
        hash2 = compute_file_hash(test_file)
        assert hash1 == hash2

    def test_compute_file_hash_different_for_different_content(self, tmp_path):
        file1 = tmp_path / "file1.txt"
        file1.write_text("content A")
        file2 = tmp_path / "file2.txt"
        file2.write_text("content B")

        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)
        assert hash1 != hash2


class TestMimeTypeFromPath:
    """Tests for MIME type inference."""

    def test_mime_type_markdown(self):
        assert mime_type_from_path(Path("test.md")) == "text/markdown"

    def test_mime_type_python(self):
        assert mime_type_from_path(Path("script.py")) == "text/x-python"

    def test_mime_type_json(self):
        assert mime_type_from_path(Path("data.json")) == "application/json"

    def test_mime_type_unknown(self):
        assert mime_type_from_path(Path("file.xyz")) == "application/octet-stream"

    def test_mime_type_case_insensitive(self):
        assert mime_type_from_path(Path("FILE.MD")) == "text/markdown"


class TestCRLFHandling:
    """Tests for cross-platform line ending support."""

    def test_parse_frontmatter_handles_crlf(self):
        """Frontmatter with CRLF (Windows) line endings should parse."""
        content = "---\r\nname: crlf-skill\r\ndescription: Test skill\r\n---\r\n# Content"
        result = parse_frontmatter(content)
        assert result.name == "crlf-skill"
        assert result.description == "Test skill"

    def test_parse_frontmatter_handles_lf(self):
        """Frontmatter with LF (Unix) line endings should parse."""
        content = "---\nname: lf-skill\ndescription: Test skill\n---\n# Content"
        result = parse_frontmatter(content)
        assert result.name == "lf-skill"
        assert result.description == "Test skill"

    def test_parse_frontmatter_handles_mixed_line_endings(self):
        """Frontmatter with mixed line endings should parse."""
        content = "---\nname: mixed-skill\r\ndescription: Test skill\n---\r\n# Content"
        result = parse_frontmatter(content)
        assert result.name == "mixed-skill"

    def test_parse_frontmatter_handles_no_trailing_newline(self):
        """Frontmatter at EOF without trailing newline should parse."""
        content = "---\nname: no-trailing\ndescription: Test\n---"
        result = parse_frontmatter(content)
        assert result.name == "no-trailing"


class TestSymlinkProtection:
    """Tests for symlink escape protection."""

    def test_scan_skill_directory_skips_symlinks(self, tmp_path):
        """Symlinks should be skipped to prevent directory escape."""
        skill_dir = tmp_path / "skills" / "symlink-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: symlink-test
description: Test symlink protection.
---
""", encoding="utf-8")

        # Create external directory with file
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        (external_dir / "secret.txt").write_text("SECRET DATA", encoding="utf-8")

        # Create symlink pointing outside skill directory
        symlink_path = skill_dir / "escape"
        try:
            symlink_path.symlink_to(external_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this platform")

        result = scan_skill_directory(skill_dir)

        # The symlink and its contents should NOT be included
        relative_paths = [f.relative_path for f in result.files]
        assert "escape/secret.txt" not in relative_paths
        assert "escape" not in relative_paths

        # Only SKILL.md should be present
        assert len(result.files) == 1
        assert result.files[0].relative_path == "SKILL.md"

    def test_scan_skill_directory_skips_symlink_files(self, tmp_path):
        """Symlink files should be skipped."""
        skill_dir = tmp_path / "skills" / "symlink-file-test"
        skill_dir.mkdir(parents=True)

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
name: symlink-file-test
description: Test symlink file protection.
---
""", encoding="utf-8")

        # Create external file
        external_file = tmp_path / "external-secret.txt"
        external_file.write_text("SECRET", encoding="utf-8")

        # Create symlink file
        symlink_file = skill_dir / "linked-secret.txt"
        try:
            symlink_file.symlink_to(external_file)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this platform")

        result = scan_skill_directory(skill_dir)

        # The symlink file should NOT be included
        relative_paths = [f.relative_path for f in result.files]
        assert "linked-secret.txt" not in relative_paths
        assert len(result.files) == 1
        assert result.files[0].relative_path == "SKILL.md"
