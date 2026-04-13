"""Tests for new metadata property TTL serialization."""

import pytest
from rdflib import Graph, Namespace, RDF, Literal, XSD

from compiler.schemas import ExtractedSkill
from compiler.serialization import serialize_skill, skill_uri_for_skill

OC = Namespace("https://ontoskills.sh/ontology#")


def _make_skill(**overrides) -> ExtractedSkill:
    defaults = dict(
        id="test-skill",
        hash="abc123",
        nature="Test",
        genus="Test",
        differentia="testing",
        intents=["test"],
        generated_by="test-model",
    )
    defaults.update(overrides)
    return ExtractedSkill(**defaults)


class TestNewPropertySerialization:
    """Verify new metadata fields are correctly serialized to TTL triples."""

    def test_category_serialized(self):
        skill = _make_skill(category="automation")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasCategory))
        assert vals == [Literal("automation")]

    def test_version_not_serialized_to_ttl(self):
        """version belongs in package.json manifest, not ontology TTL."""
        skill = _make_skill(version="1.0.0")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasVersion))
        assert vals == []

    def test_license_not_serialized_to_ttl(self):
        """license belongs in package.json manifest, not ontology TTL."""
        skill = _make_skill(license="MIT")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasLicense))
        assert vals == []

    def test_vendor_not_serialized_to_ttl(self):
        """vendor belongs in package.json manifest, not ontology TTL."""
        skill = _make_skill(vendor="anthropics")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasVendor))
        assert vals == []

    def test_package_name_serialized(self):
        skill = _make_skill(package_name="claude-plugins-official")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasPackageName))
        assert vals == [Literal("claude-plugins-official")]

    def test_is_user_invocable_serialized_as_boolean(self):
        skill = _make_skill(is_user_invocable=False)
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.isUserInvocable))
        assert len(vals) == 1
        assert vals[0].toPython() is False
        # Verify it's a typed boolean literal, not a string
        assert vals[0].datatype == XSD.boolean

    def test_argument_hint_serialized(self):
        skill = _make_skill(argument_hint="query")
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = list(g.objects(uri, OC.hasArgumentHint))
        assert vals == [Literal("query")]

    def test_allowed_tools_repeatable(self):
        skill = _make_skill(allowed_tools=["Bash", "Read", "Write"])
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = sorted(str(v) for v in g.objects(uri, OC.hasAllowedTool))
        assert vals == ["Bash", "Read", "Write"]

    def test_aliases_repeatable(self):
        skill = _make_skill(aliases=["review", "code-review"])
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        vals = sorted(str(v) for v in g.objects(uri, OC.hasAlias))
        assert vals == ["code-review", "review"]

    def test_none_fields_not_serialized(self):
        skill = _make_skill()  # All new fields are None/empty
        g = Graph()
        serialize_skill(g, skill)
        uri = skill_uri_for_skill(skill)
        assert len(list(g.objects(uri, OC.hasCategory))) == 0
        assert len(list(g.objects(uri, OC.hasVendor))) == 0
        assert len(list(g.objects(uri, OC.hasAlias))) == 0
