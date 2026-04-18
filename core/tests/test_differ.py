"""Tests for OntoSkills Skill Drift Detector — differ module and migration suggestions."""

import pytest

from compiler.differ import compute_diff

OLD_TTL = """
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:Idle .
"""

NEW_TTL_INTENT_REMOVED = """
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "generate_pdf" .
"""

NEW_TTL_SKILL_ADDED = (
    OLD_TTL
    + """
oc:NewSkill a oc:Skill ;
    oc:resolvesIntent "new_thing" .
"""
)


def test_removed_intent_is_breaking(tmp_path):
    """Renaming an intent is a breaking change — agents querying the old name get nothing."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text(NEW_TTL_INTENT_REMOVED)

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert any(c.category == 'intent' for c in report.breaking)


def test_clean_diff_is_clean(tmp_path):
    """Diffing identical files should produce a clean report."""
    f = tmp_path / 'skill.ttl'
    f.write_text(OLD_TTL)

    report = compute_diff(str(f), str(f))

    assert report.is_clean


def test_added_skill_not_breaking(tmp_path):
    """Adding a new skill is additive, not breaking."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text(NEW_TTL_SKILL_ADDED)

    report = compute_diff(str(old_f), str(new_f))

    assert not report.has_breaking
    assert report.added_skills or report.additive


def test_removed_skill_is_breaking(tmp_path):
    """Removing a skill entirely is a breaking change."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
""")

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert report.removed_skills


def test_added_requirement_is_breaking(tmp_path):
    """Adding a new requirement is breaking — existing agents may not satisfy it."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:Idle ;
    oc:hasRequirement oc:req_apikey .
oc:req_apikey a oc:Requirement ;
    oc:requirementValue "api-key" .
""")

    report = compute_diff(str(old_f), str(new_f))

    assert report.has_breaking
    assert any(c.category == 'requirement' for c in report.breaking)


# ─── Migration suggestion tests ───────────────────────────────────────────────


def test_suggest_intent_renamed(tmp_path):
    """A renamed intent should produce an intent-renamed migration suggestion."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text(NEW_TTL_INTENT_REMOVED)

    report = compute_diff(str(old_f), str(new_f))
    suggestions = report.suggestions()

    assert any(s.category == 'intent-renamed' for s in suggestions)
    intent_sug = next(s for s in suggestions if s.category == 'intent-renamed')
    assert 'create_pdf' in intent_sug.summary
    assert 'create_pdf' in intent_sug.sparql_query
    assert intent_sug.action


def test_suggest_skill_removed(tmp_path):
    """A removed skill should produce a skill-removed migration suggestion."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("@prefix oc: <https://ontoskills.sh/ontology#> .\n")

    report = compute_diff(str(old_f), str(new_f))
    suggestions = report.suggestions()

    assert any(s.category == 'skill-removed' for s in suggestions)
    skill_sug = next(s for s in suggestions if s.category == 'skill-removed')
    assert 'CreatePDF' in skill_sug.summary
    assert 'dependsOn' in skill_sug.sparql_query


def test_suggest_requirement_added(tmp_path):
    """A new requirement should produce a requirement-added migration suggestion."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("""
@prefix oc: <https://ontoskills.sh/ontology#> .
oc:CreatePDF a oc:Skill ;
    oc:resolvesIntent "create_pdf" ;
    oc:requiresState oc:Idle ;
    oc:hasRequirement oc:req_apikey .
oc:req_apikey a oc:Requirement ;
    oc:requirementValue "api-key" .
""")

    report = compute_diff(str(old_f), str(new_f))
    suggestions = report.suggestions()

    assert any(s.category == 'requirement-added' for s in suggestions)
    req_sug = next(s for s in suggestions if s.category == 'requirement-added')
    assert 'req_apikey' in req_sug.summary
    assert 'req_apikey' in req_sug.sparql_query


def test_clean_diff_has_no_suggestions(tmp_path):
    """A clean diff (no changes) should produce no migration suggestions."""
    f = tmp_path / 'skill.ttl'
    f.write_text(OLD_TTL)

    report = compute_diff(str(f), str(f))
    assert report.suggestions() == []


def test_migration_suggestion_sparql_uses_union(tmp_path):
    """Migration suggestions should query both dependsOnSkill and dependsOn."""
    old_f = tmp_path / 'old.ttl'
    new_f = tmp_path / 'new.ttl'
    old_f.write_text(OLD_TTL)
    new_f.write_text("@prefix oc: <https://ontoskills.sh/ontology#> .\n")

    report = compute_diff(str(old_f), str(new_f))
    suggestions = report.suggestions()

    skill_sug = next(s for s in suggestions if s.category == 'skill-removed')
    # SPARQL should contain UNION covering both old and new property names
    assert 'UNION' in skill_sug.sparql_query
    assert 'dependsOnSkill' in skill_sug.sparql_query
    assert 'dependsOn' in skill_sug.sparql_query
