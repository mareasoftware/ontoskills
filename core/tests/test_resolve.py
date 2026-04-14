"""Tests for install reference resolution and standalone checks."""

import json
from pathlib import Path

import pytest

from compiler.registry.models import (
    RegistryIndex,
    RegistryPackageEntry,
)
from compiler.registry.resolve import (
    resolve_install_ref,
    is_standalone_skill,
    AmbiguousRefError,
    NotFoundError,
)


# --- Fixtures ---

def _make_index(*package_ids: str) -> RegistryIndex:
    return RegistryIndex(
        packages=[
            RegistryPackageEntry(
                package_id=pid,
                manifest_path=f"packages/{pid}/package.json",
                trust_tier="verified",
                source_kind="ontology",
            )
            for pid in package_ids
        ]
    )


def _make_package_json(
    tmp_path: Path,
    package_id: str,
    skills: list[dict],
) -> Path:
    """Write a package.json and return the directory containing it."""
    pkg_dir = tmp_path / "packages" / package_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "package_id": package_id,
        "version": "1.0.0",
        "trust_tier": "verified",
        "source_kind": "ontology",
        "modules": [s["path"] for s in skills],
        "skills": skills,
    }
    (pkg_dir / "package.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return pkg_dir


# --- Resolution Tests ---

def test_exact_match_resolves_to_package():
    index = _make_index("anthropics/financial-services-plugin")
    result = resolve_install_ref("anthropics/financial-services-plugin", index)
    assert result.package.package_id == "anthropics/financial-services-plugin"


def test_prefix_match_resolves_to_author():
    index = _make_index(
        "anthropics/financial-services-plugin",
        "anthropics/claude-code",
        "obra/superpowers",
    )
    result = resolve_install_ref("anthropics", index)
    assert result.author == "anthropics"
    assert len(result.packages) == 2


def test_short_name_resolves_when_unique():
    index = _make_index(
        "pbakaus/impeccable",
        "obra/superpowers",
    )
    result = resolve_install_ref("impeccable", index)
    assert result.package.package_id == "pbakaus/impeccable"


def test_short_name_raises_when_ambiguous():
    index = _make_index(
        "author-a/impeccable",
        "author-b/impeccable",
    )
    with pytest.raises(AmbiguousRefError, match="Ambiguous"):
        resolve_install_ref("impeccable", index)


def test_not_found_raises():
    index = _make_index("obra/superpowers")
    with pytest.raises(NotFoundError, match="not found"):
        resolve_install_ref("nonexistent", index)


def test_empty_author_raises():
    index = _make_index("obra/superpowers")
    with pytest.raises(NotFoundError, match="not found"):
        resolve_install_ref("xyz", index)


# --- Skill-Level Resolution Tests ---

def test_skill_ref_with_exact_package(tmp_path):
    index = _make_index("pbakaus/impeccable")
    _make_package_json(tmp_path, "pbakaus/impeccable", [
        {"id": "harden", "path": "impeccable/harden/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ])
    result = resolve_install_ref(
        "pbakaus/impeccable/harden", index,
        manifest_base=tmp_path,
    )
    assert result.skill_id == "harden"
    assert result.standalone is True


def test_skill_ref_with_short_name_package(tmp_path):
    index = _make_index("pbakaus/impeccable")
    _make_package_json(tmp_path, "pbakaus/impeccable", [
        {"id": "harden", "path": "impeccable/harden/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": ["audit"]},
        {"id": "audit", "path": "impeccable/audit/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ])
    result = resolve_install_ref(
        "impeccable/harden", index,
        manifest_base=tmp_path,
    )
    assert result.skill_id == "harden"
    assert result.standalone is False
    assert "audit" in result.sibling_deps


def test_skill_ref_not_standalone_returns_target(tmp_path):
    """Non-standalone skills resolve successfully — the CLI checks and rejects."""
    index = _make_index("obra/superpowers")
    _make_package_json(tmp_path, "obra/superpowers", [
        {"id": "brainstorming", "path": "superpowers/brainstorming/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": ["writing-plans"]},
        {"id": "writing-plans", "path": "superpowers/writing-plans/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ])
    result = resolve_install_ref(
        "obra/superpowers/brainstorming", index,
        manifest_base=tmp_path,
    )
    assert result.skill_id == "brainstorming"
    assert result.standalone is False
    assert "writing-plans" in result.sibling_deps


def test_skill_not_found_in_package(tmp_path):
    index = _make_index("pbakaus/impeccable")
    _make_package_json(tmp_path, "pbakaus/impeccable", [
        {"id": "harden", "path": "impeccable/harden/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ])
    with pytest.raises(NotFoundError, match="Skill.*not found"):
        resolve_install_ref(
            "pbakaus/impeccable/xyz", index,
            manifest_base=tmp_path,
        )


# --- Standalone Check Tests ---

def test_standalone_skill_no_deps():
    skills = [
        {"id": "optimize", "path": "impeccable/optimize/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ]
    assert is_standalone_skill("optimize", skills) is True


def test_not_standalone_with_sibling_dep():
    skills = [
        {"id": "brainstorming", "path": "sp/brainstorming/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": ["writing-plans"]},
        {"id": "writing-plans", "path": "sp/writing-plans/ontoskill.ttl",
         "default_enabled": True, "aliases": [], "depends_on_skills": []},
    ]
    assert is_standalone_skill("brainstorming", skills) is False
