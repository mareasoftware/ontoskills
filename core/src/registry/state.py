"""Registry state management: load, save, sync, discovery."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from rdflib import Graph, RDF, URIRef
from rdflib.namespace import DCTERMS

from compiler.config import CORE_ONTOLOGY_FILENAME, ONTOLOGY_SYSTEM_DIR, ONTOLOGY_VENDOR_DIR
from compiler.core_ontology import get_oc_namespace

from .models import (
    InstalledPackageState,
    InstalledSkillState,
    PackageManifest,
    RegistryLock,
    RegistrySources,
)
from .paths import (
    enabled_index_path,
    ontology_root,
    registry_lock_path,
    registry_sources_path,
    system_dir,
)

if TYPE_CHECKING:
    from rdflib import RDF, URIRef

logger = logging.getLogger(__name__)


def load_manifest(manifest_path: Path) -> PackageManifest:
    """Load a package manifest from a JSON file."""
    return PackageManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def load_registry_sources(root: Path | None = None) -> RegistrySources:
    """Load registry sources configuration."""
    path = registry_sources_path(root)
    if not path.exists():
        return RegistrySources()
    return RegistrySources.model_validate_json(path.read_text(encoding="utf-8"))


def save_registry_sources(sources: RegistrySources, root: Path | None = None) -> None:
    """Save registry sources configuration."""
    path = registry_sources_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sources.model_dump_json(indent=2), encoding="utf-8")


def load_registry_lock(root: Path | None = None) -> RegistryLock:
    """Load the registry lock file."""
    path = registry_lock_path(root)
    if not path.exists():
        return RegistryLock()
    return RegistryLock.model_validate_json(path.read_text(encoding="utf-8"))


def save_registry_lock(lock: RegistryLock, root: Path | None = None) -> None:
    """Save the registry lock file."""
    path = registry_lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lock.model_dump_json(indent=2), encoding="utf-8")


def discover_local_skill_paths(root: Path | None = None) -> list[Path]:
    """Discover parent skill TTL files only (ontoskill.ttl).

    Sub-skills are compiled as auxiliary .ttl files (e.g., planning.ttl),
    but are NOT standalone installable units — they are accessible
    through the parent skill's oc:extends relationship.
    Only the parent skill (ontoskill.ttl) appears in the registry.
    """
    base = ontology_root() if root is None else Path(root).resolve()
    excluded = {
        system_dir(base),
        base / Path(ONTOLOGY_VENDOR_DIR).name,
        base / "official",
        base / "community",
    }
    paths: list[Path] = []
    for path in base.rglob("ontoskill.ttl"):
        # Skip if in excluded directories
        if any(parent == path.parent or parent in path.parents for parent in excluded):
            continue
        paths.append(path.resolve())
    return sorted(paths)


def sync_local_package(lock: RegistryLock, root: Path) -> RegistryLock:
    """Synchronize the local package with discovered skill paths."""
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
            installed_at=datetime.now(timezone.utc).isoformat(),
            install_root=str(root),
            manifest_path="",
            skills=local_skills,
        )
    else:
        lock.packages.pop("local", None)
    return lock


def _skill_relations(module_path: Path) -> tuple[str | None, set[str]]:
    """Extract skill ID and relation IDs from a skill module."""
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
    for predicate in (oc.extends, oc.dependsOnSkill, oc.dependsOn):
        for target in graph.objects(skill_subject, predicate):
            target_id = graph.value(target, DCTERMS.identifier)
            if target_id:
                relations.add(str(target_id))
            elif isinstance(target, URIRef):
                value = str(target)
                if "#skill_" in value:
                    relations.add(value.rsplit("#skill_", 1)[-1].replace("_", "-"))
    return str(skill_id_literal) if skill_id_literal else None, relations
