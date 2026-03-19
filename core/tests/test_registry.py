"""Tests for the simplified ontology registry helpers."""

import json
from pathlib import Path

from compiler.core_ontology import create_core_ontology
from compiler.registry import (
    add_registry_source,
    disable_skills,
    enable_skills,
    enabled_index_path,
    import_source_repository,
    install_package_from_directory,
    install_package_from_sources,
    load_registry_lock,
    load_registry_sources,
    ontology_vendor_dir,
    rebuild_registry_indexes,
    skills_vendor_dir,
)


def write_compiled_package(package_dir: Path) -> None:
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
    write_compiled_package(package_dir)

    package = install_package_from_directory(package_dir, root=root)
    lock = load_registry_lock(root)
    assert "marea.office" in lock.packages
    assert Path(package.install_root) == ontology_vendor_dir(root) / "marea.office"
    assert enabled_index_path(root).exists()

    enable_skills("marea.office", ["xlsx"], root=root)
    lock = load_registry_lock(root)
    enabled = {skill.skill_id for skill in lock.packages["marea.office"].skills if skill.enabled}
    assert enabled == {"office", "xlsx"}

    disable_skills("marea.office", ["office"], root=root)
    lock = load_registry_lock(root)
    enabled = {skill.skill_id for skill in lock.packages["marea.office"].skills if skill.enabled}
    assert enabled == set()

    installed_index, enabled_index = rebuild_registry_indexes(root)
    assert installed_index.exists()
    assert enabled_index.exists()


def test_local_compiled_skills_are_tracked_and_can_be_disabled(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")
    (root / "office").mkdir(parents=True, exist_ok=True)
    (root / "office" / "ontoskill.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_office a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "office" ;
    oc:nature "Local office" .
""",
        encoding="utf-8",
    )

    rebuild_registry_indexes(root)
    lock = load_registry_lock(root)
    assert "local" in lock.packages
    assert lock.packages["local"].skills[0].enabled is True

    disable_skills("local", ["office"], root=root)
    lock = load_registry_lock(root)
    local_skill = next(skill for skill in lock.packages["local"].skills if skill.skill_id == "office")
    assert local_skill.enabled is False


def test_registry_install_from_file_index_uses_relative_manifest_and_vendor_layout(tmp_path):
    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    registry_dir = tmp_path / "registry"
    package_dir = registry_dir / "packages" / "marea.greeting"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "hello").mkdir(parents=True, exist_ok=True)
    (package_dir / "hello" / "ontoskill.ttl").write_text(
        """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_hello a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "hello" ;
    oc:nature "Greeting" .
""",
        encoding="utf-8",
    )
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "package_id": "marea.greeting",
                "version": "0.1.0",
                "trust_tier": "verified",
                "modules": ["hello/ontoskill.ttl"],
                "skills": [
                    {"id": "hello", "path": "hello/ontoskill.ttl", "default_enabled": False},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (registry_dir / "index.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "package_id": "marea.greeting",
                        "manifest_url": "./packages/marea.greeting/package.json",
                        "trust_tier": "verified",
                        "source_kind": "ontology",
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    add_registry_source("official", (registry_dir / "index.json").resolve().as_uri(), root=root, trust_tier="verified")
    sources = load_registry_sources(root)
    assert len(sources.sources) == 1

    package = install_package_from_sources("marea.greeting", root=root)
    assert package.package_id == "marea.greeting"
    assert Path(package.install_root) == ontology_vendor_dir(root) / "marea.greeting"


def test_import_source_repository_clones_to_skills_vendor_and_compiles_to_ontology_vendor(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "ui-ux-pro-max-skill"
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").write_text("# UI UX Pro Max", encoding="utf-8")
    (repo_dir / "src" / "landing-page").mkdir(parents=True, exist_ok=True)
    (repo_dir / "src" / "landing-page" / "SKILL.md").write_text("# Landing Page", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        assert source_root == skills_vendor_dir(root) / "ui-ux-pro-max-skill"
        assert compiled_root == ontology_vendor_dir(root) / "ui-ux-pro-max-skill"
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "landing-page").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_ui_ux_pro_max a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "ui-ux-pro-max" ;
    oc:nature "Design system skill" .
""",
            encoding="utf-8",
        )
        (compiled_root / "src" / "landing-page" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_landing_page a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "landing-page" ;
    oc:nature "Landing page skill" .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(str(repo_dir), root=root, trust_tier="community")

    assert package.package_id == "ui-ux-pro-max-skill"
    assert Path(package.install_root) == ontology_vendor_dir(root) / "ui-ux-pro-max-skill"
    assert (skills_vendor_dir(root) / "ui-ux-pro-max-skill" / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").exists()
    assert sorted(skill.skill_id for skill in package.skills) == ["landing-page", "ui-ux-pro-max"]
    assert all(not skill.enabled for skill in package.skills)


def test_import_source_repository_rewrites_compiled_payload_script_paths(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "ui-ux-pro-max-skill"
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "ui-ux-pro-max" / "SKILL.md").write_text("# UI UX Pro Max", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "ui-ux-pro-max" / "scripts").mkdir(parents=True, exist_ok=True)
        (compiled_root / "src" / "ui-ux-pro-max" / "scripts" / "search.py").write_text("print('search')", encoding="utf-8")
        (compiled_root / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_ui_ux_pro_max a oc:Skill, oc:DeclarativeSkill ;
    dcterms:identifier "ui-ux-pro-max" ;
    oc:nature "Design system skill" ;
    oc:hasPayload [
        a oc:PythonCode ;
        oc:code "python3 skills/ui-ux-pro-max/scripts/search.py \\"hero section\\""
    ] .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(str(repo_dir), root=root, trust_tier="community")

    ttl_path = Path(package.install_root) / ".claude" / "skills" / "ui-ux-pro-max" / "ontoskill.ttl"
    payload = ttl_path.read_text(encoding="utf-8")
    expected_script = (Path(package.install_root) / "src" / "ui-ux-pro-max" / "scripts" / "search.py").resolve().as_posix()
    assert expected_script in payload
    assert "skills/ui-ux-pro-max/scripts/search.py" not in payload


def test_import_source_repository_rewrites_relative_and_broken_absolute_script_paths(tmp_path):
    from unittest.mock import patch

    root = tmp_path / "ontoskills"
    create_core_ontology(root / "ontoclaw-core.ttl")

    repo_dir = tmp_path / "design-repo"
    (repo_dir / ".claude" / "skills" / "design-system").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "design-system" / "SKILL.md").write_text("# Design System", encoding="utf-8")
    (repo_dir / ".claude" / "skills" / "design").mkdir(parents=True, exist_ok=True)
    (repo_dir / ".claude" / "skills" / "design" / "SKILL.md").write_text("# Design", encoding="utf-8")

    def fake_compile(source_root, compiled_root):
        (compiled_root / ".claude" / "skills" / "design-system" / "scripts").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "design" / "scripts" / "logo").mkdir(parents=True, exist_ok=True)
        (compiled_root / ".claude" / "skills" / "design-system" / "scripts" / "search-slides.py").write_text("print('slides')", encoding="utf-8")
        (compiled_root / ".claude" / "skills" / "design" / "scripts" / "logo" / "search.py").write_text("print('logo')", encoding="utf-8")
        (compiled_root / ".claude" / "skills" / "design-system" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_design_system a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "design-system" ;
    oc:hasPayload [
        a oc:ExecutionPayload ;
        oc:code "python scripts/search-slides.py \\"investor pitch\\""
    ] .
""",
            encoding="utf-8",
        )
        (compiled_root / ".claude" / "skills" / "design" / "ontoskill.ttl").write_text(
            """
@prefix oc: <http://ontoclaw.marea.software/ontology#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

oc:skill_design a oc:Skill, oc:ExecutableSkill ;
    dcterms:identifier "design" ;
    oc:hasPayload [
        a oc:ExecutionPayload ;
        oc:code "python ~/.claude//Users/test/skill/scripts/logo/search.py"
    ] .
""",
            encoding="utf-8",
        )

    with patch("compiler.registry.compile_source_tree", side_effect=fake_compile):
        package = import_source_repository(str(repo_dir), root=root, trust_tier="community")

    design_system_ttl = Path(package.install_root) / ".claude" / "skills" / "design-system" / "ontoskill.ttl"
    design_payload = design_system_ttl.read_text(encoding="utf-8")
    expected_relative_script = (
        Path(package.install_root) / ".claude" / "skills" / "design-system" / "scripts" / "search-slides.py"
    ).resolve().as_posix()
    assert expected_relative_script in design_payload
    assert "python scripts/search-slides.py" not in design_payload

    design_ttl = Path(package.install_root) / ".claude" / "skills" / "design" / "ontoskill.ttl"
    broken_payload = design_ttl.read_text(encoding="utf-8")
    assert "~/.claude//Users/" not in broken_payload
    assert "python /Users/test/skill/scripts/logo/search.py" in broken_payload
