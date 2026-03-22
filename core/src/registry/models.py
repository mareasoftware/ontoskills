"""Pydantic models for registry state and manifests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
