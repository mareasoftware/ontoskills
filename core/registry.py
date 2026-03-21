"""Global ontology registry helpers.

This module manages installed package state, enabled skill state, and aggregated
index manifests for the global ontology root.
"""

from __future__ import annotations

import json
import logging
import os
import re
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
    ONTOLOGY_ROOT,
    ONTOLOGY_SYSTEM_DIR,
    ONTOLOGY_VENDOR_DIR,
    SKILLS_DIR,
    SKILLS_VENDOR_DIR,
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
    source_files: list[str] = Field(default_factory=list)


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


IGNORED_SOURCE_DIRS = {".git", "node_modules", ".venv", "target", "dist", "build", "__pycache__"}
SKILL_SCRIPT_PATH_RE = re.compile(r"skills/([A-Za-z0-9._-]+)/([^\s\"']+)")
RELATIVE_SCRIPT_PATH_RE = re.compile(r"(?<![A-Za-z0-9._/-])scripts/([^\s\"']+)")
BROKEN_ABSOLUTE_PATH_RE = re.compile(r"~/\.claude//(?=[A-Za-z])")


def ontology_root() -> Path:
    return Path(ONTOLOGY_ROOT).resolve()


def skills_root(root: Path | None = None) -> Path:
    if root is None:
        return Path(SKILLS_DIR).resolve()
    ontology_base = Path(root).resolve()
    return (ontology_base.parent / "skills").resolve()


def system_dir(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_SYSTEM_DIR).name


def skills_vendor_dir(root: Path | None = None) -> Path:
    base = skills_root(root)
    return base / Path(SKILLS_VENDOR_DIR).name


def ontology_vendor_dir(root: Path | None = None) -> Path:
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_VENDOR_DIR).name


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
    skills_root(base).mkdir(parents=True, exist_ok=True)
    skills_vendor_dir(base).mkdir(parents=True, exist_ok=True)
    system_dir(base).mkdir(parents=True, exist_ok=True)
    ontology_vendor_dir(base).mkdir(parents=True, exist_ok=True)
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
        ontology_vendor_dir(base),
        base / "official",
        base / "community",
    }
    paths: list[Path] = []
    for path in base.rglob("ontoskill.ttl"):
        if any(parent == path.parent or parent in path.parents for parent in excluded):
            continue
        paths.append(path.resolve())
    return sorted(paths)


def sync_local_package(lock: RegistryLock, root: Path) -> RegistryLock:
    local_paths = discover_local_skill_paths(root)
    existing = lock.packages.get("local")
    previous_by_path = {
        Path(skill.module_path).resolve(): skill
        for skill in (existing.skills if existing else [])
    }

    local_skills: list[InstalledSkillState] = []
    for module_path in local_paths:
        skill_id, _ = _skill_relations(module_path)
        if not skill_id:
            continue
        previous = previous_by_path.get(module_path.resolve())
        local_skills.append(
            InstalledSkillState(
                skill_id=skill_id,
                module_path=str(module_path.resolve()),
                aliases=previous.aliases if previous else [],
                enabled=previous.enabled if previous else True,
                default_enabled=True,
            )
        )

    if local_skills:
        lock.packages["local"] = InstalledPackageState(
            package_id="local",
            version="workspace",
            trust_tier="local",
            source=None,
            installed_at=datetime.now(UTC).isoformat(),
            install_root=str(root),
            manifest_path="",
            skills=local_skills,
        )
    else:
        lock.packages.pop("local", None)
    return lock


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
    lock = sync_local_package(lock, base)
    save_registry_lock(lock, base)

    installed_paths = iter_installed_skill_paths(lock)
    enabled_paths = iter_enabled_skill_paths(lock)

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
    install_root = ontology_vendor_dir(base) / manifest.package_id

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

    raw_root = skills_vendor_dir(base) / manifest.package_id
    compiled_root = ontology_vendor_dir(base) / manifest.package_id
    if raw_root.exists():
        shutil.rmtree(raw_root)
    if compiled_root.exists():
        shutil.rmtree(compiled_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    compiled_root.mkdir(parents=True, exist_ok=True)

    source_root = package_dir / manifest.source_root
    for item in source_root.rglob("*"):
        if not item.is_file():
            continue
        destination = raw_root / item.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)

    copied_manifest = compiled_root / "package.json"
    shutil.copy2(manifest_path, copied_manifest)

    compile_source_tree(raw_root, compiled_root)
    rewrite_compiled_payload_paths(compiled_root)

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
        install_root=str(compiled_root),
        manifest_path=str(copied_manifest),
        skills=skills,
    )
    lock = load_registry_lock(base)
    lock.packages[package_state.package_id] = package_state
    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return package_state


def import_source_repository(
    repo_ref: str,
    root: Path | None = None,
    trust_tier: TrustTier = "community",
    package_id: str | None = None,
) -> InstalledPackageState:
    base = ensure_registry_layout(root)

    with TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        repo_path, source_ref = materialize_source_repository(repo_ref, tmp_dir)
        resolved_package_id = package_id or infer_source_package_id(repo_ref, repo_path)
        skill_entries = discover_skill_entries(repo_path)
        if not skill_entries:
            raise ValueError(f"No SKILL.md files found in source repository: {repo_ref}")

        raw_root = skills_vendor_dir(base) / resolved_package_id
        compiled_root = ontology_vendor_dir(base) / resolved_package_id
        if raw_root.exists():
            shutil.rmtree(raw_root)
        if compiled_root.exists():
            shutil.rmtree(compiled_root)
        copy_source_tree(repo_path, raw_root)
        compiled_root.mkdir(parents=True, exist_ok=True)
        compile_source_tree(raw_root, compiled_root)
        rewrite_compiled_payload_paths(compiled_root)

        package_state = InstalledPackageState(
            package_id=resolved_package_id,
            version=datetime.now(UTC).strftime("import-%Y%m%d%H%M%S"),
            trust_tier=trust_tier,
            source=source_ref,
            source_kind="source",
            installed_at=datetime.now(UTC).isoformat(),
            install_root=str(compiled_root),
            manifest_path="",
            skills=[
                InstalledSkillState(
                    skill_id=skill_id,
                    module_path=str((compiled_root / module_path).resolve()),
                    aliases=[],
                    enabled=False,
                    default_enabled=False,
                )
                for skill_id, module_path in skill_entries
            ],
        )

        synthetic_manifest = {
            "package_id": package_state.package_id,
            "version": package_state.version,
            "trust_tier": package_state.trust_tier,
            "source": package_state.source,
            "skills": [
                {
                    "id": skill.skill_id,
                    "path": str(Path(skill.module_path).relative_to(compiled_root)),
                    "default_enabled": False,
                    "aliases": [],
                }
                for skill in package_state.skills
            ],
        }
        manifest_path = compiled_root / "package.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(synthetic_manifest, indent=2), encoding="utf-8")
        package_state.manifest_path = str(manifest_path)

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


def rewrite_compiled_payload_paths(compiled_root: Path) -> None:
    for ttl_path in compiled_root.rglob("*.ttl"):
        original = ttl_path.read_text(encoding="utf-8")
        rewritten = rewrite_payload_text(original, compiled_root, ttl_path)
        if rewritten != original:
            ttl_path.write_text(rewritten, encoding="utf-8")


def rewrite_payload_text(payload: str, compiled_root: Path, ttl_path: Path) -> str:
    def replace_skill_path(match: re.Match[str]) -> str:
        skill_id = match.group(1)
        relative_path = Path(match.group(2))
        for candidate in (
            compiled_root / ".claude" / "skills" / skill_id / relative_path,
            compiled_root / "src" / skill_id / relative_path,
            compiled_root / skill_id / relative_path,
        ):
            if candidate.exists():
                return candidate.resolve().as_posix()
        return match.group(0)

    def replace_relative_script_path(match: re.Match[str]) -> str:
        relative_path = Path("scripts") / match.group(1)
        candidate = ttl_path.parent / relative_path
        if candidate.exists():
            return candidate.resolve().as_posix()
        return match.group(0)

    rewritten = BROKEN_ABSOLUTE_PATH_RE.sub("/", payload)
    rewritten = SKILL_SCRIPT_PATH_RE.sub(replace_skill_path, rewritten)
    rewritten = RELATIVE_SCRIPT_PATH_RE.sub(replace_relative_script_path, rewritten)
    return rewritten


def materialize_source_repository(repo_ref: str, tmp_dir: Path) -> tuple[Path, str]:
    local_path = Path(repo_ref)
    if local_path.exists():
        return local_path.resolve(), str(local_path.resolve())

    repo_dir = tmp_dir / "repo"
    command = ["git", "clone", "--depth", "1", repo_ref, str(repo_dir)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to clone source repository '{repo_ref}': {result.stderr or result.stdout}")
    return repo_dir, repo_ref


def infer_source_package_id(repo_ref: str, repo_path: Path) -> str:
    parsed = urlparse(repo_ref)
    if parsed.scheme in ("http", "https") and parsed.netloc.endswith("github.com"):
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            owner = slugify_identifier(parts[0])
            repo = slugify_identifier(parts[1].removesuffix(".git"))
            return f"{owner}.{repo}"
    return slugify_identifier(repo_path.name)


def slugify_identifier(value: str) -> str:
    normalized = []
    for char in value.lower():
        if char.isalnum():
            normalized.append(char)
        elif not normalized or normalized[-1] != "-":
            normalized.append("-")
    return "".join(normalized).strip("-") or "imported"


def is_ignored_source_path(path: Path, source_root: Path) -> bool:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return True
    return any(part in IGNORED_SOURCE_DIRS for part in relative.parts)


def copy_source_tree(source_root: Path, destination_root: Path) -> None:
    for path in source_root.rglob("*"):
        if is_ignored_source_path(path, source_root):
            continue
        relative = path.relative_to(source_root)
        destination = destination_root / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def discover_skill_entries(source_root: Path) -> list[tuple[str, Path]]:
    skills: list[tuple[str, Path]] = []
    for skill_file in source_root.rglob("SKILL.md"):
        if is_ignored_source_path(skill_file, source_root):
            continue
        skill_dir = skill_file.parent
        relative = skill_dir.relative_to(source_root)
        module_path = relative / "ontoskill.ttl"
        skill_id = slugify_identifier(skill_dir.name)
        skills.append((skill_id, module_path))
    skills.sort(key=lambda item: (str(item[1]), item[0]))
    return skills


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
    lock = sync_local_package(lock, base)
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
    lock = sync_local_package(lock, base)
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
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)
    lock = sync_local_package(lock, base)
    save_registry_lock(lock, base)
    return lock


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

        if source_kind == "source":
            raise ValueError("Registry sources support compiled ontology packages only")

        module_paths = list(
            dict.fromkeys([*manifest.modules, *(skill.path for skill in manifest.skills)])
        )
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
    manifest_ref = _resolve_child_ref(source.index_url, package.manifest_url)
    return install_package_from_manifest_ref(
        manifest_ref,
        root=root,
        trust_tier=effective_trust,
        source_kind=package.source_kind or source.source_kind,
    )
