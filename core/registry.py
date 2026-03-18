"""Global ontology registry helpers.

This module manages installed package state, enabled skill state, and aggregated
index manifests for the global ontology root.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from pydantic import BaseModel, Field
from rdflib import Graph, RDF, URIRef
from rdflib.namespace import DCTERMS

from compiler.config import (
    ONTOLOGY_COMMUNITY_DIR,
    ONTOLOGY_OFFICIAL_DIR,
    ONTOLOGY_ROOT,
    ONTOLOGY_SYSTEM_DIR,
)
from compiler.core_ontology import get_oc_namespace
from compiler.storage import generate_index_manifest

logger = logging.getLogger(__name__)

TrustTier = Literal["verified", "trusted", "community", "local"]
SourceKind = Literal["ontology", "source"]


class PackageSkillManifest(BaseModel):
    id: str
    path: str
    default_enabled: bool = False
    aliases: list[str] = Field(default_factory=list)


class PackageManifest(BaseModel):
    package_id: str
    version: str
    core_version: str | None = None
    trust_tier: TrustTier
    source: str | None = None
    checksum: str | None = None
    modules: list[str] = Field(default_factory=list)
    skills: list[PackageSkillManifest]
    source_root: str | None = None


class InstalledSkillState(BaseModel):
    skill_id: str
    module_path: str
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = False
    default_enabled: bool = False


class InstalledPackageState(BaseModel):
    package_id: str
    version: str
    trust_tier: TrustTier
    source: str | None = None
    source_kind: SourceKind = "ontology"
    installed_at: str
    install_root: str
    manifest_path: str
    skills: list[InstalledSkillState]


class RegistryLock(BaseModel):
    packages: dict[str, InstalledPackageState] = Field(default_factory=dict)


class RegistrySource(BaseModel):
    name: str
    index_url: str
    trust_tier: TrustTier = "community"
    source_kind: SourceKind = "ontology"


class RegistrySources(BaseModel):
    sources: list[RegistrySource] = Field(default_factory=list)


class RegistryPackageEntry(BaseModel):
    package_id: str
    manifest_url: str
    trust_tier: TrustTier | None = None
    source_kind: SourceKind = "ontology"


class RegistryIndex(BaseModel):
    packages: list[RegistryPackageEntry] = Field(default_factory=list)


def ontology_root() -> Path:
    return Path(ONTOLOGY_ROOT).resolve()


def system_dir(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_SYSTEM_DIR).name


def official_dir(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_OFFICIAL_DIR).name


def community_dir(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_COMMUNITY_DIR).name


def enabled_index_path(root: Path | None = None) -> Path:
    return system_dir(root) / "index.enabled.ttl"


def installed_index_path(root: Path | None = None) -> Path:
    return system_dir(root) / "index.installed.ttl"


def registry_lock_path(root: Path | None = None) -> Path:
    return system_dir(root) / "registry.lock.json"


def registry_sources_path(root: Path | None = None) -> Path:
    return system_dir(root) / "registry.sources.json"


def ensure_registry_layout(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    system_dir(base).mkdir(parents=True, exist_ok=True)
    official_dir(base).mkdir(parents=True, exist_ok=True)
    community_dir(base).mkdir(parents=True, exist_ok=True)
    return base


def load_manifest(manifest_path: Path) -> PackageManifest:
    return PackageManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def load_registry_sources(root: Path | None = None) -> RegistrySources:
    path = registry_sources_path(root)
    if not path.exists():
        return RegistrySources()
    return RegistrySources.model_validate_json(path.read_text(encoding="utf-8"))


def save_registry_sources(sources: RegistrySources, root: Path | None = None) -> None:
    path = registry_sources_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sources.model_dump_json(indent=2), encoding="utf-8")


def load_registry_lock(root: Path | None = None) -> RegistryLock:
    path = registry_lock_path(root)
    if not path.exists():
        return RegistryLock()
    return RegistryLock.model_validate_json(path.read_text(encoding="utf-8"))


def save_registry_lock(lock: RegistryLock, root: Path | None = None) -> None:
    path = registry_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lock.model_dump_json(indent=2), encoding="utf-8")


def discover_local_skill_paths(root: Path | None = None) -> list[Path]:
    base = ontology_root() if root is None else Path(root).resolve()
    excluded = {
        system_dir(base),
        official_dir(base),
        community_dir(base),
    }
    paths: list[Path] = []
    for path in base.rglob("ontoskill.ttl"):
        if any(parent == path.parent or parent in path.parents for parent in excluded):
            continue
        paths.append(path.resolve())
    return sorted(paths)


def iter_installed_skill_paths(lock: RegistryLock) -> list[Path]:
    paths: list[Path] = []
    for package in lock.packages.values():
        for skill in package.skills:
            paths.append(Path(skill.module_path).resolve())
    return sorted(paths)


def iter_enabled_skill_paths(lock: RegistryLock) -> list[Path]:
    paths: list[Path] = []
    for package in lock.packages.values():
        for skill in package.skills:
            if skill.enabled:
                paths.append(Path(skill.module_path).resolve())
    return sorted(paths)


def rebuild_registry_indexes(root: Path | None = None) -> tuple[Path, Path]:
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)

    local_paths = discover_local_skill_paths(base)
    installed_paths = sorted({*local_paths, *iter_installed_skill_paths(lock)})
    enabled_paths = sorted({*local_paths, *iter_enabled_skill_paths(lock)})

    generate_index_manifest(installed_paths, installed_index_path(base), output_base=base)
    generate_index_manifest(enabled_paths, enabled_index_path(base), output_base=base)
    return installed_index_path(base), enabled_index_path(base)


def install_package_from_directory(
    package_dir: Path,
    root: Path | None = None,
    trust_tier: TrustTier | None = None,
    source_kind: SourceKind = "ontology",
) -> InstalledPackageState:
    base = ensure_registry_layout(root)
    manifest_path = package_dir / "package.json"
    manifest = load_manifest(manifest_path)

    effective_trust = trust_tier or manifest.trust_tier
    destination_base = official_dir(base) if effective_trust == "verified" else community_dir(base)
    install_root = destination_base / manifest.package_id

    if install_root.exists():
        shutil.rmtree(install_root)
    install_root.mkdir(parents=True, exist_ok=True)

    if source_kind == "source":
        package_state = install_source_package_from_directory(
            package_dir,
            root=base,
            trust_tier=effective_trust,
        )
    else:
        copied_modules = []
        module_paths = list(dict.fromkeys([*manifest.modules, *(skill.path for skill in manifest.skills)]))
        for relative in module_paths:
            source = package_dir / relative
            destination = install_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied_modules.append(destination)

        copied_manifest = install_root / "package.json"
        shutil.copy2(manifest_path, copied_manifest)

        package_state = InstalledPackageState(
            package_id=manifest.package_id,
            version=manifest.version,
            trust_tier=effective_trust,
            source=manifest.source,
            source_kind=source_kind,
            installed_at=datetime.now(UTC).isoformat(),
            install_root=str(install_root),
            manifest_path=str(copied_manifest),
            skills=[
                InstalledSkillState(
                    skill_id=skill.id,
                    module_path=str((install_root / skill.path).resolve()),
                    aliases=skill.aliases,
                    enabled=skill.default_enabled,
                    default_enabled=skill.default_enabled,
                )
                for skill in manifest.skills
            ],
        )

    lock = load_registry_lock(base)
    lock.packages[package_state.package_id] = package_state
    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return package_state


def install_source_package_from_directory(
    package_dir: Path,
    root: Path | None = None,
    trust_tier: TrustTier = "community",
) -> InstalledPackageState:
    base = ensure_registry_layout(root)
    manifest_path = package_dir / "package.json"
    manifest = load_manifest(manifest_path)
    if not manifest.source_root:
        raise ValueError("Source packages require a source_root in package.json")

    destination_base = official_dir(base) if trust_tier == "verified" else community_dir(base)
    install_root = destination_base / manifest.package_id
    if install_root.exists():
        shutil.rmtree(install_root)
    raw_root = install_root / "source"
    compiled_root = install_root / "compiled"
    raw_root.mkdir(parents=True, exist_ok=True)
    compiled_root.mkdir(parents=True, exist_ok=True)

    source_root = package_dir / manifest.source_root
    for item in source_root.rglob("*"):
        if not item.is_file():
            continue
        destination = raw_root / item.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)

    copied_manifest = install_root / "package.json"
    shutil.copy2(manifest_path, copied_manifest)

    compile_source_tree(raw_root, compiled_root)

    skills = []
    for skill in manifest.skills:
        module_path = compiled_root / skill.path
        skills.append(
            InstalledSkillState(
                skill_id=skill.id,
                module_path=str(module_path.resolve()),
                aliases=skill.aliases,
                enabled=False,
                default_enabled=False,
            )
        )

    package_state = InstalledPackageState(
        package_id=manifest.package_id,
        version=manifest.version,
        trust_tier=trust_tier,
        source=manifest.source,
        source_kind="source",
        installed_at=datetime.now(UTC).isoformat(),
        install_root=str(install_root),
        manifest_path=str(copied_manifest),
        skills=skills,
    )
    lock = load_registry_lock(base)
    lock.packages[package_state.package_id] = package_state
    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return package_state


def compile_source_tree(source_root: Path, compiled_root: Path) -> None:
    cli_path = Path(__file__).resolve().parent / "cli.py"
    command = [
        sys.executable,
        str(cli_path),
        "compile",
        "-i",
        str(source_root),
        "-o",
        str(compiled_root),
        "-y",
        "-f",
    ]
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Source package compilation failed with code {result.returncode}: {result.stderr or result.stdout}"
        )


def _best_available_skill_id(
    skill_id: str,
    preferred_package_id: str | None,
    lock: RegistryLock,
) -> tuple[str, InstalledSkillState] | None:
    if preferred_package_id and preferred_package_id in lock.packages:
        package = lock.packages[preferred_package_id]
        for skill in package.skills:
            if skill.skill_id == skill_id:
                return preferred_package_id, skill

    tier_rank = {"verified": 0, "trusted": 1, "community": 2, "local": 3}
    candidates: list[tuple[int, str, InstalledSkillState]] = []
    for package_id, package in lock.packages.items():
        for skill in package.skills:
            if skill.skill_id == skill_id:
                candidates.append((tier_rank.get(package.trust_tier, 99), package_id, skill))
    if not candidates:
        return None
    _, package_id, skill = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return package_id, skill


def _skill_relations(module_path: Path) -> tuple[str | None, set[str]]:
    graph = Graph()
    graph.parse(module_path, format="turtle")
    oc = get_oc_namespace()

    skill_subject = None
    for subject in graph.subjects(RDF.type, oc.Skill):
        skill_subject = subject
        break

    if skill_subject is None:
        return None, set()

    skill_id_literal = graph.value(skill_subject, DCTERMS.identifier)
    relations: set[str] = set()
    for predicate in (oc.extends, oc.dependsOn):
        for target in graph.objects(skill_subject, predicate):
            target_id = graph.value(target, DCTERMS.identifier)
            if target_id:
                relations.add(str(target_id))
            elif isinstance(target, URIRef):
                value = str(target)
                if "#skill_" in value:
                    relations.add(value.rsplit("#skill_", 1)[-1].replace("_", "-"))
    return str(skill_id_literal) if skill_id_literal else None, relations


def enable_skills(
    package_id: str,
    skill_ids: list[str] | None = None,
    root: Path | None = None,
) -> InstalledPackageState:
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)
    package = lock.packages[package_id]

    selected = skill_ids or [skill.skill_id for skill in package.skills]
    queue = list(selected)
    visited: set[tuple[str, str]] = set()

    while queue:
        current_skill_id = queue.pop(0)
        resolution = _best_available_skill_id(current_skill_id, package_id, lock)
        if resolution is None:
            continue
        resolved_package_id, state = resolution
        key = (resolved_package_id, state.skill_id)
        if key in visited:
            continue
        visited.add(key)
        state.enabled = True
        _, relations = _skill_relations(Path(state.module_path))
        queue.extend(sorted(relations))

    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return lock.packages[package_id]


def disable_skills(
    package_id: str,
    skill_ids: list[str] | None = None,
    root: Path | None = None,
) -> InstalledPackageState:
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)
    package = lock.packages[package_id]

    target_keys = {
        (package_id, skill.skill_id)
        for skill in package.skills
        if skill_ids is None or skill.skill_id in skill_ids
    }
    changed = True
    while changed:
        changed = False
        target_ids = {skill_id for _, skill_id in target_keys}
        for candidate_package_id, candidate_package in lock.packages.items():
            for skill in candidate_package.skills:
                if not skill.enabled:
                    continue
                _, relations = _skill_relations(Path(skill.module_path))
                if relations & target_ids:
                    key = (candidate_package_id, skill.skill_id)
                    if key not in target_keys:
                        target_keys.add(key)
                        changed = True

    for candidate_package_id, candidate_package in lock.packages.items():
        for skill in candidate_package.skills:
            if (candidate_package_id, skill.skill_id) in target_keys:
                skill.enabled = False

    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return lock.packages[package_id]


def list_installed_packages(root: Path | None = None) -> RegistryLock:
    ensure_registry_layout(root)
    return load_registry_lock(root)


def add_registry_source(
    name: str,
    index_url: str,
    root: Path | None = None,
    trust_tier: TrustTier = "community",
    source_kind: SourceKind = "ontology",
) -> RegistrySources:
    base = ensure_registry_layout(root)
    sources = load_registry_sources(base)
    sources.sources = [source for source in sources.sources if source.name != name]
    sources.sources.append(
        RegistrySource(
            name=name,
            index_url=index_url,
            trust_tier=trust_tier,
            source_kind=source_kind,
        )
    )
    save_registry_sources(sources, base)
    return sources


def list_registry_sources(root: Path | None = None) -> RegistrySources:
    ensure_registry_layout(root)
    return load_registry_sources(root)


def _read_text_from_ref(ref: str) -> str:
    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https", "file"):
        with urlopen(ref) as response:
            return response.read().decode("utf-8")
    return Path(ref).read_text(encoding="utf-8")


def _copy_ref_to_path(ref: str, destination: Path) -> None:
    parsed = urlparse(ref)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if parsed.scheme in ("http", "https", "file"):
        with urlopen(ref) as response:
            destination.write_bytes(response.read())
    else:
        shutil.copy2(Path(ref), destination)


def _resolve_child_ref(base_ref: str, child_path: str) -> str:
    parsed = urlparse(base_ref)
    if parsed.scheme in ("http", "https", "file"):
        return urljoin(base_ref, child_path)
    return str((Path(base_ref).parent / child_path).resolve())


def load_registry_index(index_ref: str) -> RegistryIndex:
    return RegistryIndex.model_validate_json(_read_text_from_ref(index_ref))


def resolve_package_from_sources(
    package_id: str,
    root: Path | None = None,
) -> tuple[RegistrySource, RegistryPackageEntry]:
    sources = load_registry_sources(root)
    for source in sources.sources:
        index = load_registry_index(source.index_url)
        for package in index.packages:
            if package.package_id == package_id:
                return source, package
    raise KeyError(f"Package not found in configured sources: {package_id}")


def install_package_from_manifest_ref(
    manifest_ref: str,
    root: Path | None = None,
    trust_tier: TrustTier | None = None,
    source_kind: SourceKind = "ontology",
) -> InstalledPackageState:
    with TemporaryDirectory() as tmp:
        package_dir = Path(tmp) / "package"
        package_dir.mkdir(parents=True, exist_ok=True)
        manifest_json = _read_text_from_ref(manifest_ref)
        manifest = PackageManifest.model_validate_json(manifest_json)
        local_manifest = package_dir / "package.json"
        local_manifest.write_text(manifest_json, encoding="utf-8")

        module_paths = list(dict.fromkeys([*manifest.modules, *(skill.path for skill in manifest.skills)]))
        for relative in module_paths:
            ref = _resolve_child_ref(manifest_ref, relative)
            _copy_ref_to_path(ref, package_dir / relative)

        return install_package_from_directory(
            package_dir,
            root=root,
            trust_tier=trust_tier or manifest.trust_tier,
            source_kind=source_kind,
        )


def install_package_from_sources(
    package_id: str,
    root: Path | None = None,
) -> InstalledPackageState:
    source, package = resolve_package_from_sources(package_id, root=root)
    effective_trust = package.trust_tier or source.trust_tier
    return install_package_from_manifest_ref(
        package.manifest_url,
        root=root,
        trust_tier=effective_trust,
        source_kind=package.source_kind or source.source_kind,
    )
