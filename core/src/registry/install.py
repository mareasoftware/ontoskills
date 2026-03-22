"""Package installation from directories, manifests, and registries."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from .models import (
    InstalledPackageState,
    InstalledSkillState,
    PackageManifest,
    RegistryIndex,
    RegistryPackageEntry,
    RegistrySource,
    TrustTier,
    SourceKind,
)
from .paths import ensure_registry_layout, ontology_vendor_dir, skills_vendor_dir
from .state import load_manifest, load_registry_lock, save_registry_lock
from .index import rebuild_registry_indexes
from .compile import compile_source_tree, rewrite_compiled_payload_paths, discover_skill_entries


def install_package_from_directory(
    package_dir: Path,
    root: Path | None = None,
    trust_tier: TrustTier | None = None,
    source_kind: SourceKind = "ontology",
) -> InstalledPackageState:
    """Install a package from a local directory."""
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
            package_dir, root=base, trust_tier=effective_trust
        )
    else:
        package_state = _install_ontology_package(
            package_dir, manifest, install_root, effective_trust, source_kind
        )

    lock = load_registry_lock(base)
    lock.packages[package_state.package_id] = package_state
    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return package_state


def _install_ontology_package(
    package_dir: Path,
    manifest: PackageManifest,
    install_root: Path,
    trust_tier: TrustTier,
    source_kind: SourceKind,
) -> InstalledPackageState:
    """Copy ontology package files and create state."""
    copied_modules = []
    module_paths = list(dict.fromkeys([*manifest.modules, *(skill.path for skill in manifest.skills)]))
    for relative in module_paths:
        source = package_dir / relative
        destination = install_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_modules.append(destination)

    copied_manifest = install_root / "package.json"
    shutil.copy2(package_dir / "package.json", copied_manifest)

    return InstalledPackageState(
        package_id=manifest.package_id,
        version=manifest.version,
        trust_tier=trust_tier,
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


def install_source_package_from_directory(
    package_dir: Path,
    root: Path | None = None,
    trust_tier: TrustTier = "community",
) -> InstalledPackageState:
    """Install a source package by compiling it locally."""
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

    skills = [
        InstalledSkillState(
            skill_id=skill.id,
            module_path=str((compiled_root / skill.path).resolve()),
            aliases=skill.aliases,
            enabled=False,
            default_enabled=False,
        )
        for skill in manifest.skills
    ]

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
    """Import and compile a source repository (local path or git URL)."""
    from .compile import materialize_source_repository, infer_source_package_id, copy_source_tree

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
        manifest_path.write_text(json.dumps(synthetic_manifest, indent=2), encoding="utf-8")
        package_state.manifest_path = str(manifest_path)

        lock = load_registry_lock(base)
        lock.packages[package_state.package_id] = package_state
        save_registry_lock(lock, base)
        rebuild_registry_indexes(base)
        return package_state


# Registry source operations

def add_registry_source(
    name: str,
    index_url: str,
    root: Path | None = None,
    trust_tier: TrustTier = "community",
    source_kind: SourceKind = "ontology",
) -> RegistrySources:
    """Add a registry source to the configuration."""
    from .state import load_registry_sources, save_registry_sources

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
    """List configured registry sources."""
    from .state import load_registry_sources
    ensure_registry_layout(root)
    return load_registry_sources(root)


def load_registry_index(index_ref: str) -> RegistryIndex:
    """Load a registry index from a URL or file path."""
    parsed = urlparse(index_ref)
    if parsed.scheme in ("http", "https", "file"):
        with urlopen(index_ref) as response:
            return RegistryIndex.model_validate_json(response.read().decode("utf-8"))
    return RegistryIndex.model_validate_json(Path(index_ref).read_text(encoding="utf-8"))


def resolve_package_from_sources(
    package_id: str,
    root: Path | None = None,
) -> tuple[RegistrySource, RegistryPackageEntry]:
    """Resolve a package from configured registry sources."""
    from .state import load_registry_sources

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
    """Install a package from a manifest URL or file path."""
    parsed = urlparse(manifest_ref)
    if parsed.scheme in ("http", "https", "file"):
        with urlopen(manifest_ref) as response:
            manifest_json = response.read().decode("utf-8")
    else:
        manifest_json = Path(manifest_ref).read_text(encoding="utf-8")

    manifest = PackageManifest.model_validate_json(manifest_json)

    with TemporaryDirectory() as tmp:
        package_dir = Path(tmp) / "package"
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "package.json").write_text(manifest_json, encoding="utf-8")

        if source_kind == "source":
            raise ValueError("Registry sources support compiled ontology packages only")

        module_paths = list(
            dict.fromkeys([*manifest.modules, *(skill.path for skill in manifest.skills)])
        )
        for relative in module_paths:
            ref = urljoin(manifest_ref, relative)
            destination = package_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if parsed.scheme in ("http", "https", "file"):
                with urlopen(ref) as response:
                    destination.write_bytes(response.read())
            else:
                shutil.copy2(Path(manifest_ref).parent / relative, destination)

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
    """Install a package from configured registry sources."""
    source, package = resolve_package_from_sources(package_id, root=root)
    effective_trust = package.trust_tier or source.trust_tier
    manifest_ref = urljoin(source.index_url, package.manifest_url)
    return install_package_from_manifest_ref(
        manifest_ref,
        root=root,
        trust_tier=effective_trust,
        source_kind=package.source_kind or source.source_kind,
    )
