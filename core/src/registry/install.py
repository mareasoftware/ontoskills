"""Package installation from directories, manifests, and registries."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
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
from .paths import ensure_registry_layout, ontology_author_dir, skills_author_dir
from .state import load_manifest, load_registry_lock, save_registry_lock
from .index import rebuild_registry_indexes
from .compile import compile_source_tree, rewrite_compiled_payload_paths, discover_skill_entries
from .resolve import NotFoundError


def _extract_skill_metadata_from_ttl(ttl_path: Path) -> dict:
    """Read optional metadata fields from a compiled TTL module.

    Returns a dict with category, version, is_user_invocable, depends_on_skills.
    """
    from rdflib import Graph, Namespace, RDF, Literal as RDFLiteral

    OC = Namespace("https://ontoskills.sh/ontology#")
    metadata: dict = {}

    if not ttl_path.exists():
        return metadata

    try:
        g = Graph()
        g.parse(str(ttl_path), format="turtle")
    except Exception:
        return metadata

    # Find the skill subject (type oc:Skill)
    for subject in g.subjects(RDF.type, OC.Skill):
        # category
        cat = g.value(subject, OC.hasCategory)
        if cat:
            metadata["category"] = str(cat)

        # is_user_invocable
        inv = g.value(subject, OC.isUserInvocable)
        if inv is not None:
            metadata["is_user_invocable"] = str(inv).lower() in ("true", "1", "yes")

        # depends_on_skills (repeatable)
        deps = [
            str(o).rsplit("#", 1)[-1].removeprefix("skill_").replace("_", "-")
            for o in g.objects(subject, OC.dependsOnSkill)
        ]
        if deps:
            metadata["depends_on_skills"] = deps

        break  # only first skill subject

    return metadata


def install_package_from_directory(
    package_dir: Path,
    root: Path | None = None,
    trust_tier: TrustTier | None = None,
    source_kind: SourceKind = "ontology",
    with_embeddings: bool = False,
) -> InstalledPackageState:
    """Install a package from a local directory."""
    base = ensure_registry_layout(root)
    manifest_path = package_dir / "package.json"
    manifest = load_manifest(manifest_path)

    effective_trust = trust_tier or manifest.trust_tier
    install_root = ontology_author_dir(base) / manifest.package_id

    if install_root.exists():
        shutil.rmtree(install_root)
    install_root.mkdir(parents=True, exist_ok=True)

    if source_kind == "source":
        package_state = install_source_package_from_directory(
            package_dir, root=base, trust_tier=effective_trust
        )
    else:
        package_state = _install_ontology_package(
            package_dir, manifest, install_root, effective_trust, source_kind,
            with_embeddings=with_embeddings,
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
    with_embeddings: bool = False,
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

    # Optionally copy embedding files
    if with_embeddings and manifest.embedding_files:
        for ef_rel in manifest.embedding_files:
            source = package_dir / ef_rel
            if source.exists():
                destination = install_root / ef_rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

    copied_manifest = install_root / "package.json"
    shutil.copy2(package_dir / "package.json", copied_manifest)

    return InstalledPackageState(
        package_id=manifest.package_id,
        version=manifest.version,
        trust_tier=trust_tier,
        source=manifest.source,
        source_kind=source_kind,
        installed_at=datetime.now(timezone.utc).isoformat(),
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

    raw_root = skills_author_dir(base) / manifest.package_id
    compiled_root = ontology_author_dir(base) / manifest.package_id
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
        installed_at=datetime.now(timezone.utc).isoformat(),
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

        raw_root = skills_author_dir(base) / resolved_package_id
        compiled_root = ontology_author_dir(base) / resolved_package_id
        if raw_root.exists():
            shutil.rmtree(raw_root)
        if compiled_root.exists():
            shutil.rmtree(compiled_root)
        copy_source_tree(repo_path, raw_root)
        compiled_root.mkdir(parents=True, exist_ok=True)
        compile_source_tree(raw_root, compiled_root)
        rewrite_compiled_payload_paths(compiled_root)

        # Build skill states with metadata extracted from compiled TTLs
        skill_states = []
        skill_manifests = []
        for skill_id, module_path in skill_entries:
            ttl_path = compiled_root / module_path
            meta = _extract_skill_metadata_from_ttl(ttl_path)
            skill_states.append(InstalledSkillState(
                skill_id=skill_id,
                module_path=str((compiled_root / module_path).resolve()),
                aliases=[],
                enabled=False,
                default_enabled=False,
                category=meta.get("category"),
                version=meta.get("version"),
                is_user_invocable=meta.get("is_user_invocable"),
                depends_on_skills=meta.get("depends_on_skills", []),
            ))
            skill_manifests.append({
                "id": skill_id,
                "path": str(module_path),
                "default_enabled": False,
                "aliases": [],
                **({k: v for k, v in meta.items() if v is not None and v != []}),
            })

        package_state = InstalledPackageState(
            package_id=resolved_package_id,
            version=datetime.now(timezone.utc).strftime("import-%Y%m%d%H%M%S"),
            trust_tier=trust_tier,
            source=source_ref,
            source_kind="source",
            installed_at=datetime.now(timezone.utc).isoformat(),
            install_root=str(compiled_root),
            manifest_path="",
            skills=skill_states,
        )

        synthetic_manifest = {
            "package_id": package_state.package_id,
            "version": package_state.version,
            "trust_tier": package_state.trust_tier,
            "source": package_state.source,
            "skills": skill_manifests,
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
    with_embeddings: bool = False,
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

        # Optionally download embedding files
        if with_embeddings and manifest.embedding_files:
            for ef_rel in manifest.embedding_files:
                destination = package_dir / ef_rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if parsed.scheme in ("http", "https", "file"):
                        ef_url = urljoin(manifest_ref, ef_rel)
                        with urlopen(ef_url) as resp:
                            destination.write_bytes(resp.read())
                    else:
                        src = Path(manifest_ref).parent / ef_rel
                        if src.exists():
                            shutil.copy2(src, destination)
                except Exception:
                    pass  # Non-fatal — embeddings may not be available

        return install_package_from_directory(
            package_dir,
            root=root,
            trust_tier=trust_tier or manifest.trust_tier,
            source_kind=source_kind,
            with_embeddings=with_embeddings,
        )


def install_package_from_sources(
    package_id: str,
    root: Path | None = None,
    with_embeddings: bool = False,
) -> InstalledPackageState:
    """Install a package from configured registry sources."""
    source, package = resolve_package_from_sources(package_id, root=root)
    effective_trust = package.trust_tier or source.trust_tier
    manifest_ref = urljoin(source.index_url, package.manifest_path)
    return install_package_from_manifest_ref(
        manifest_ref,
        root=root,
        trust_tier=effective_trust,
        source_kind=package.source_kind or source.source_kind,
        with_embeddings=with_embeddings,
    )


def install_author(
    author_name: str,
    packages: list,
    root: Path | None = None,
    with_embeddings: bool = False,
) -> list[InstalledPackageState]:
    """Install all packages from an author.

    Args:
        author_name: Author name (e.g., "anthropics")
        packages: List of RegistryPackageEntry objects for this author
        root: Ontology root path
        with_embeddings: Download per-skill embedding files

    Returns:
        List of installed package states
    """
    base = ensure_registry_layout(root)
    results = []
    for package_entry in packages:
        source, _ = resolve_package_from_sources(package_entry.package_id, root=base)
        effective_trust = package_entry.trust_tier or source.trust_tier
        manifest_ref = urljoin(source.index_url, package_entry.manifest_path)
        pkg_state = install_package_from_manifest_ref(
            manifest_ref,
            root=base,
            trust_tier=effective_trust,
            source_kind=package_entry.source_kind or source.source_kind,
            with_embeddings=with_embeddings,
        )
        results.append(pkg_state)
    return results


def install_single_skill(
    package_entry,
    skill_id: str,
    root: Path | None = None,
    with_embeddings: bool = False,
) -> InstalledPackageState:
    """Install a single skill from a package.

    Copies the skill directory (ontoskill.ttl + sibling .ttl files + assets)
    and registers it as a partial package in the lock.

    Args:
        package_entry: RegistryPackageEntry for the containing package
        skill_id: Skill to install
        root: Ontology root path

    Returns:
        InstalledPackageState with only the requested skill enabled
    """
    base = ensure_registry_layout(root)
    source, _ = resolve_package_from_sources(package_entry.package_id, root=base)
    effective_trust = package_entry.trust_tier or source.trust_tier
    manifest_ref = urljoin(source.index_url, package_entry.manifest_path)

    parsed = urlparse(manifest_ref)
    if parsed.scheme in ("http", "https", "file"):
        with urlopen(manifest_ref) as response:
            manifest_json = response.read().decode("utf-8")
    else:
        manifest_json = Path(manifest_ref).read_text(encoding="utf-8")

    manifest = PackageManifest.model_validate_json(manifest_json)
    install_root = ontology_author_dir(base) / manifest.package_id

    # Find the target skill in the manifest
    target_skill = None
    for skill in manifest.skills:
        if skill.id == skill_id:
            target_skill = skill
            break

    if target_skill is None:
        raise NotFoundError(f"Skill '{skill_id}' not found in {manifest.package_id}")

    # The skill path is like "superpowers/brainstorming/ontoskill.ttl"
    # The skill directory is the parent: "superpowers/brainstorming/"
    skill_path = Path(target_skill.path)
    skill_dir = skill_path.parent

    # Collect all modules under the skill directory
    modules_to_copy = []
    for module_rel in manifest.modules:
        module_path = Path(module_rel)
        try:
            module_path.relative_to(skill_dir)
            modules_to_copy.append(module_rel)
        except ValueError:
            if module_path == skill_path:
                modules_to_copy.append(module_rel)

    # Collect embedding files under the skill directory
    embedding_files_to_copy = []
    if with_embeddings and manifest.embedding_files:
        for ef_rel in manifest.embedding_files:
            ef_path = Path(ef_rel)
            try:
                ef_path.relative_to(skill_dir)
                embedding_files_to_copy.append(ef_rel)
            except ValueError:
                pass

    # Copy modules to install root
    install_root.mkdir(parents=True, exist_ok=True)
    copied_modules = []

    manifest_dir = Path(manifest_ref).parent if parsed.scheme == "" else None
    for module_rel in modules_to_copy:
        if manifest_dir:
            src = manifest_dir / module_rel
        else:
            # Build URL from manifest's parent directory, not from the JSON file itself
            base_url = manifest_ref[:manifest_ref.rfind("/")] + "/"
            module_url = urljoin(base_url, module_rel)
            dest = install_root / module_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urlopen(module_url) as resp:
                    dest.write_bytes(resp.read())
                copied_modules.append(dest)
            except Exception as e:
                raise NotFoundError(
                    f"Failed to download module '{module_rel}' from {module_url}: {e}"
                )
            continue

        if src and src.exists():
            dest = install_root / module_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_modules.append(dest)

    # Copy embedding files for this skill
    for ef_rel in embedding_files_to_copy:
        if manifest_dir:
            src = manifest_dir / ef_rel
        else:
            base_url = manifest_ref[:manifest_ref.rfind("/")] + "/"
            ef_url = urljoin(base_url, ef_rel)
            dest = install_root / ef_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urlopen(ef_url) as resp:
                    dest.write_bytes(resp.read())
            except Exception:
                pass  # Non-fatal — embeddings may not exist
            continue

        if src and src.exists():
            dest = install_root / ef_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    # Write a partial manifest with only this skill
    partial_manifest = {
        "package_id": manifest.package_id,
        "version": manifest.version,
        "trust_tier": effective_trust,
        "source_kind": "ontology",
        "modules": [str(p) for p in modules_to_copy],
        "embedding_files": [str(p) for p in embedding_files_to_copy],
        "skills": [{
            "id": target_skill.id,
            "path": target_skill.path,
            "default_enabled": True,
            "aliases": target_skill.aliases,
        }],
    }
    (install_root / "package.json").write_text(
        json.dumps(partial_manifest, indent=2), encoding="utf-8"
    )

    # Register in lock
    package_state = InstalledPackageState(
        package_id=manifest.package_id,
        version=manifest.version,
        trust_tier=effective_trust,
        source=manifest.source,
        source_kind="ontology",
        installed_at=datetime.now(timezone.utc).isoformat(),
        install_root=str(install_root),
        manifest_path=str((install_root / "package.json").resolve()),
        skills=[
            InstalledSkillState(
                skill_id=target_skill.id,
                module_path=str((install_root / target_skill.path).resolve()),
                aliases=target_skill.aliases,
                enabled=True,
                default_enabled=True,
            )
        ],
    )

    lock = load_registry_lock(base)
    # Merge with existing package if already partially installed
    existing = lock.packages.get(package_state.package_id)
    if existing:
        existing_skills = {s.skill_id: s for s in existing.skills}
        existing_skills[target_skill.id] = package_state.skills[0]
        existing.skills = list(existing_skills.values())
        existing.version = package_state.version
        lock.packages[package_state.package_id] = existing
    else:
        lock.packages[package_state.package_id] = package_state

    save_registry_lock(lock, base)
    rebuild_registry_indexes(base)
    return lock.packages[package_state.package_id]
