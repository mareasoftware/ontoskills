"""Registry package for OntoSkills package management.

This package provides:
- Pydantic models for manifests and state
- Path utilities for registry layout
- State management (load/save/sync)
- Index operations (enable/disable skills)
- Package installation from directories and registries
- Source compilation helpers
"""

# Models
from .models import (
    TrustTier,
    SourceKind,
    PackageSkillManifest,
    PackageManifest,
    InstalledSkillState,
    InstalledPackageState,
    RegistryLock,
    RegistrySource,
    RegistrySources,
    RegistryPackageEntry,
    RegistryIndex,
)

# Paths
from .paths import (
    ontology_root,
    skills_root,
    system_dir,
    skills_vendor_dir,
    ontology_vendor_dir,
    enabled_index_path,
    installed_index_path,
    registry_lock_path,
    registry_sources_path,
    ensure_registry_layout,
)

# State
from .state import (
    load_manifest,
    load_registry_sources,
    save_registry_sources,
    load_registry_lock,
    save_registry_lock,
    discover_local_skill_paths,
    sync_local_package,
)

# Index
from .index import (
    iter_installed_skill_paths,
    iter_enabled_skill_paths,
    rebuild_registry_indexes,
    enable_skills,
    disable_skills,
    list_installed_packages,
)

# Install
from .install import (
    install_package_from_directory,
    install_source_package_from_directory,
    import_source_repository,
    add_registry_source,
    list_registry_sources,
    load_registry_index,
    resolve_package_from_sources,
    install_package_from_manifest_ref,
    install_package_from_sources,
)

# Compile
from .compile import (
    compile_source_tree,
    rewrite_compiled_payload_paths,
    materialize_source_repository,
    infer_source_package_id,
    slugify_identifier,
    copy_source_tree,
    discover_skill_entries,
)

__all__ = [
    # Models
    "TrustTier",
    "SourceKind",
    "PackageSkillManifest",
    "PackageManifest",
    "InstalledSkillState",
    "InstalledPackageState",
    "RegistryLock",
    "RegistrySource",
    "RegistrySources",
    "RegistryPackageEntry",
    "RegistryIndex",
    # Paths
    "ontology_root",
    "skills_root",
    "system_dir",
    "skills_vendor_dir",
    "ontology_vendor_dir",
    "enabled_index_path",
    "installed_index_path",
    "registry_lock_path",
    "registry_sources_path",
    "ensure_registry_layout",
    # State
    "load_manifest",
    "load_registry_sources",
    "save_registry_sources",
    "load_registry_lock",
    "save_registry_lock",
    "discover_local_skill_paths",
    "sync_local_package",
    # Index
    "iter_installed_skill_paths",
    "iter_enabled_skill_paths",
    "rebuild_registry_indexes",
    "enable_skills",
    "disable_skills",
    "list_installed_packages",
    # Install
    "install_package_from_directory",
    "install_source_package_from_directory",
    "import_source_repository",
    "add_registry_source",
    "list_registry_sources",
    "load_registry_index",
    "resolve_package_from_sources",
    "install_package_from_manifest_ref",
    "install_package_from_sources",
    # Compile
    "compile_source_tree",
    "rewrite_compiled_payload_paths",
    "materialize_source_repository",
    "infer_source_package_id",
    "slugify_identifier",
    "copy_source_tree",
    "discover_skill_entries",
]
