"""Registry index operations: rebuild indexes, enable/disable skills."""

from __future__ import annotations

import logging
from pathlib import Path

from compiler.storage import generate_index_manifest

from .models import InstalledPackageState, InstalledSkillState, RegistryLock
from .paths import ensure_registry_layout, enabled_index_path
from .state import load_registry_lock, save_registry_lock, sync_local_package, _skill_relations

logger = logging.getLogger(__name__)


def iter_enabled_skill_paths(lock: RegistryLock) -> list[Path]:
    """Get all enabled skill module paths."""
    paths: list[Path] = []
    for package in lock.packages.values():
        for skill in package.skills:
            if skill.enabled:
                paths.append(Path(skill.module_path).resolve())
    return sorted(paths)


def rebuild_registry_indexes(root: Path | None = None) -> Path:
    """Rebuild enabled index manifest."""
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)
    lock = sync_local_package(lock, base)
    save_registry_lock(lock, base)

    enabled_paths = iter_enabled_skill_paths(lock)

    generate_index_manifest(enabled_paths, enabled_index_path(base), output_base=base)
    return enabled_index_path(base)


def _best_available_skill_id(
    skill_id: str,
    preferred_package_id: str | None,
    lock: RegistryLock,
) -> tuple[str, InstalledSkillState] | None:
    """Find the best available skill matching the given ID."""
    if preferred_package_id and preferred_package_id in lock.packages:
        package = lock.packages[preferred_package_id]
        for skill in package.skills:
            if skill.skill_id == skill_id:
                return preferred_package_id, skill

    tier_rank = {"official": 0, "local": 1, "verified": 2, "community": 3}
    candidates: list[tuple[int, str, InstalledSkillState]] = []
    for package_id, package in lock.packages.items():
        for skill in package.skills:
            if skill.skill_id == skill_id:
                candidates.append((tier_rank.get(package.trust_tier, 99), package_id, skill))
    if not candidates:
        return None
    _, package_id, skill = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
    return package_id, skill


def enable_skills(
    package_id: str,
    skill_ids: list[str] | None = None,
    root: Path | None = None,
) -> InstalledPackageState:
    """Enable skills in a package, including their dependencies."""
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
    """Disable skills in a package, including dependents."""
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
    """List all installed packages with synced local state."""
    base = ensure_registry_layout(root)
    lock = load_registry_lock(base)
    lock = sync_local_package(lock, base)
    save_registry_lock(lock, base)
    return lock
