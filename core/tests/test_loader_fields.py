"""Tests for FIELD_ALIASES normalization and vendor/package derivation."""

import pytest
from compiler.loader import (
    normalize_field_aliases,
    derive_vendor_and_package,
)


class TestFieldAliases:
    """Verify FIELD_ALIASES maps heterogeneous frontmatter keys to canonical names."""

    def test_category_aliases(self):
        raw = {"categories": "automation", "name": "test", "description": "test"}
        result = normalize_field_aliases(raw)
        assert result.get("category") == "automation"

    def test_is_user_invocable_aliases(self):
        raw = {"invocable": "yes", "name": "test", "description": "test"}
        result = normalize_field_aliases(raw)
        assert "is_user_invocable" in result

    def test_allowed_tools_aliases(self):
        raw = {"tools": ["Bash", "Read"], "name": "test", "description": "test"}
        result = normalize_field_aliases(raw)
        assert "allowed_tools" in result

    def test_aliases_field(self):
        raw = {"also_known_as": ["jira", "jira-auto"], "name": "test", "description": "test"}
        result = normalize_field_aliases(raw)
        assert result.get("aliases") == ["jira", "jira-auto"]

    def test_depends_on_aliases(self):
        raw = {"dependencies": ["office"], "name": "test", "description": "test"}
        result = normalize_field_aliases(raw)
        assert result.get("depends_on") == ["office"]

    def test_no_aliases_field_untouched(self):
        raw = {"name": "test", "description": "test", "version": "1.0"}
        result = normalize_field_aliases(raw)
        assert result["name"] == "test"
        assert result["version"] == "1.0"


class TestVendorPackageDerivation:
    """Verify vendor and package_name are derived from directory path."""

    def test_derive_from_skills_path(self):
        result = derive_vendor_and_package("/home/user/.agents/skills/anthropics/claude-code/brainstorming")
        assert result == ("anthropics", "claude-code")

    def test_derive_from_nested_path(self):
        result = derive_vendor_and_package("/home/user/.agents/skills/claude-office-skills/skills/jira-automation")
        assert result == ("claude-office-skills", "skills")

    def test_derive_returns_none_for_short_path(self):
        result = derive_vendor_and_package("/home/user/skill")
        assert result == (None, None)
