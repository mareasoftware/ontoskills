"""Tests for the ontology registry helpers."""

import json
from pathlib import Path

from compiler.core_ontology import create_core_ontology
from compiler.registry import (
    add_registry_source,
    enabled_index_path,
    install_package_from_directory,
    install_source_package_from_directory,
    install_package_from_sources,
    load_registry_lock,
    load_registry_sources,
    rebuild_registry_indexes,
    disable_skills,
    enable_skills,
)


def write_package(package_dir: Path) -> None:
    (package_dir / "skills").mkdir(parents=True, exist_ok=True)
    (package_dir / "skills" / "office.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office base" .
""",
        encoding="utf-8",
    )
    (package_dir / "skills" / "xlsx.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Spreadsheet" ;
    oc:extends oc:skill_office .
""",
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "marea.office",
                "version": "1.0.0",
                "trust_tier": "verified",
                "source": "https://example.invalid/marea/office",
                "modules": ["skills/office.ttl", "skills/xlsx.ttl"],
                "skills": [
                    {"id": "office", "path": "skills/office.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "skills/xlsx.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_install_enable_disable_package_rebuilds_indexes(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "package"
    write_package(package_dir)

    install_package_from_directory(package_dir, root=root)
    lock = load_registry_lock(root)
    assert "marea.office" in lock.packages
    assert enabled_index_path(root).exists()

    enable_skills("marea.office", ["xlsx"], root=root)
    lock = load_registry_lock(root)
    office_pkg = lock.packages["marea.office"]
    enabled = {skill.skill_id for skill in office_pkg.skills if skill.enabled}
    assert enabled == {"office", "xlsx"}

    disable_skills("marea.office", ["office"], root=root)
    lock = load_registry_lock(root)
    office_pkg = lock.packages["marea.office"]
    enabled = {skill.skill_id for skill in office_pkg.skills if skill.enabled}
    assert enabled == set()

    installed_index, enabled_index = rebuild_registry_indexes(root)
    assert installed_index.exists()
    assert enabled_index.exists()


def test_registry_source_install_from_file_index(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "package"
    write_package(package_dir)

    index_path = tmp_path / "registry.json"
    manifest_url = (package_dir / "package.json").resolve().as_uri()
    index_path.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "marea.office",
                        "manifest_url": manifest_url,
                        "trust_tier": "verified",
                        "source_kind": "ontology",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    add_registry_source("official", index_path.resolve().as_uri(), root=root, trust_tier="verified")
    sources = load_registry_sources(root)
    assert len(sources.sources) == 1

    install_package_from_sources("marea.office", root=root)
    lock = load_registry_lock(root)
    assert "marea.office" in lock.packages
    assert lock.packages["marea.office"].trust_tier == "verified"


def test_import_source_package_compiles_and_stays_disabled(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "source-package"
    (package_dir / "src" / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
    (package_dir / "src" / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    (package_dir / "src" / "office" / "xlsx" / "SKILL.md").write_text("# Xlsx", encoding="utf-8")
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "community.office",
                "version": "0.1.0",
                "trust_tier": "community",
                "source_root": "src",
                "skills": [
                    {"id": "office", "path": "office/ontoskill.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "office/xlsx/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_compile(source_root, compiled_root):
        (compiled_root / "office").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office" .
""",
            encoding="utf-8",
        )
        (compiled_root / "office" / "xlsx" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Xlsx" ;
    oc:extends oc:skill_office .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = install_source_package_from_directory(package_dir, root=root, trust_tier="community")

    assert package.source_kind == "source"
    assert all(not skill.enabled for skill in package.skills)
    lock = load_registry_lock(root)
    assert "community.office" in lock.packages


def test_registry_source_import_from_file_index_for_remote_source_package(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    package_dir = tmp_path / "remote-source-package"
    (package_dir / "src" / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
    (package_dir / "src" / "office" / "SKILL.md").write_text("# Office", encoding="utf-8")
    (package_dir / "src" / "office" / "xlsx" / "SKILL.md").write_text("# Xlsx", encoding="utf-8")
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "skillssh.office",
                "version": "0.2.0",
                "trust_tier": "community",
                "source_root": "src",
                "source_files": [
                    "src/office/SKILL.md",
                    "src/office/xlsx/SKILL.md",
                ],
                "skills": [
                    {"id": "office", "path": "office/ontoskill.ttl", "default_enabled": False},
                    {"id": "xlsx", "path": "office/xlsx/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    registry_index = tmp_path / "registry-source.json"
    registry_index.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "skillssh.office",
                        "manifest_url": (package_dir / "package.json").resolve().as_uri(),
                        "trust_tier": "community",
                        "source_kind": "source",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_compile(source_root, compiled_root):
        assert (source_root / "office" / "SKILL.md").exists()
        assert (source_root / "office" / "xlsx" / "SKILL.md").exists()
        (compiled_root / "office").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "xlsx").mkdir(parents=True, exist_ok=True)
        (compiled_root / "office" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Office" .
""",
            encoding="utf-8",
        )
        (compiled_root / "office" / "xlsx" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_xlsx a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "xlsx" ;
    oc:nature "Xlsx" ;
    oc:extends oc:skill_office .
""",
            encoding="utf-8",
        )

    add_registry_source("skillssh", registry_index.resolve().as_uri(), root=root, trust_tier="community", source_kind="source")
    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = install_package_from_sources("skillssh.office", root=root)

    assert package.source_kind == "source"
    assert package.package_id == "skillssh.office"
    assert all(not skill.enabled for skill in package.skills)
