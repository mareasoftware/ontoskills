"""Install reference resolution: maps a user-facing ref to a typed install target."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    InstallTarget,
    PackageTarget,
    RegistryIndex,
    SkillTarget,
    VendorTarget,
)

if TYPE_CHECKING:
    from .models import PackageManifest, RegistryPackageEntry


class ResolveError(Exception):
    """Base for resolution errors."""


class NotFoundError(ResolveError):
    """Reference not found in index."""


class AmbiguousRefError(ResolveError):
    """Short name matches multiple packages."""



def _load_manifest_for_package(
    package: RegistryPackageEntry,
    manifest_base: Path,
) -> PackageManifest:
    """Load a package.json manifest from disk relative to manifest_base."""
    from .state import load_manifest

    manifest_path = manifest_base / package.manifest_path.lstrip("./")
    return load_manifest(manifest_path)


def is_standalone_skill(
    skill_id: str,
    skills: list[dict],
) -> bool:
    """Check if a skill can be installed standalone (no sibling deps).

    A skill is standalone if none of its depends_on_skills reference
    other skills within the same package (sibling skills).
    """
    sibling_ids = {s["id"] for s in skills}
    for skill in skills:
        if skill["id"] == skill_id:
            deps = skill.get("depends_on_skills", [])
            sibling_deps = [d for d in deps if d in sibling_ids]
            return len(sibling_deps) == 0
    return False


def _get_sibling_deps(
    skill_id: str,
    skills: list[dict],
) -> list[str]:
    """Return list of sibling dependencies for a skill."""
    sibling_ids = {s["id"] for s in skills}
    for skill in skills:
        if skill["id"] == skill_id:
            deps = skill.get("depends_on_skills", [])
            return [d for d in deps if d in sibling_ids]
    return []


def resolve_install_ref(
    ref: str,
    index: RegistryIndex,
    manifest_base: Path | None = None,
) -> InstallTarget:
    """Resolve a user-facing reference to a typed install target.

    Resolution order:
    1. Exact match on package_id
    2. Prefix match (vendor-level)
    3. Short name (last segment of package_id, unique match only)
    4. Skill-level (if ref has 3+ segments or short_name/skill form)

    Args:
        ref: User-facing reference (e.g., "anthropics", "pbakaus/impeccable/harden")
        index: Registry index with all known packages
        manifest_base: Base directory for resolving manifest_path paths (needed for skill-level)

    Returns:
        VendorTarget, PackageTarget, or SkillTarget

    Raises:
        NotFoundError: Reference not found
        AmbiguousRefError: Short name matches multiple packages
    """
    package_map = {p.package_id: p for p in index.packages}

    # Step 1: Exact match
    if ref in package_map:
        return PackageTarget(package=package_map[ref])

    # Step 2: Prefix match (vendor-level, single-segment refs only)
    if "/" not in ref:
        prefix = ref + "/"
        matching = [p for p in index.packages if p.package_id.startswith(prefix)]
        if matching:
            return VendorTarget(vendor=ref, packages=matching)

    # Step 3: Short name resolution
    candidates = [
        p for p in index.packages
        if p.package_id.endswith("/" + ref) or p.package_id == ref
    ]
    if len(candidates) == 1:
        resolved_package = candidates[0]
        return PackageTarget(package=resolved_package)
    elif len(candidates) > 1:
        matches = ", ".join(p.package_id for p in candidates)
        raise AmbiguousRefError(
            f"Ambiguous: matches {matches}. Use full path."
        )

    # Step 4: Skill-level resolution
    parts = ref.split("/")
    if len(parts) >= 2:
        for split_at in range(1, len(parts)):
            package_ref = "/".join(parts[:split_at])
            skill_id = "/".join(parts[split_at:])

            pkg = package_map.get(package_ref)
            if pkg is None:
                short_candidates = [
                    p for p in index.packages
                    if p.package_id.endswith("/" + package_ref) or p.package_id == package_ref
                ]
                if len(short_candidates) == 1:
                    pkg = short_candidates[0]
                else:
                    continue

            if manifest_base is None:
                raise NotFoundError(
                    f"Skill-level resolution requires manifest_base, "
                    f"but got ref '{ref}'"
                )

            manifest = _load_manifest_for_package(pkg, manifest_base)
            skill_ids_in_pkg = {s.id for s in manifest.skills}

            if skill_id not in skill_ids_in_pkg:
                raise NotFoundError(
                    f"Skill '{skill_id}' not found in package '{pkg.package_id}'. "
                    f"Available: {', '.join(sorted(skill_ids_in_pkg))}"
                )

            skills_dicts = [s.model_dump() for s in manifest.skills]
            standalone = is_standalone_skill(skill_id, skills_dicts)
            sibling_deps = _get_sibling_deps(skill_id, skills_dicts)

            return SkillTarget(
                package=pkg,
                skill_id=skill_id,
                standalone=standalone,
                sibling_deps=sibling_deps,
            )

    raise NotFoundError(f"Package not found: {ref}")
