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
    category: str | None = None
    version: str | None = None
    is_user_invocable: bool | None = None
    depends_on_skills: list[str] = Field(default_factory=list)


class PackageManifest(BaseModel):
    package_id: str
    version: str
    core_version: str | None = None
    trust_tier: TrustTier
    source: str | None = None
    checksum: str | None = None
    modules: list[str] = Field(default_factory=list)
    skills: list[PackageSkillManifest]
    embedding_files: list[str] = Field(default_factory=list)
    source_root: str | None = None
    source_files: list[str] = Field(default_factory=list)


class InstalledSkillState(BaseModel):
    skill_id: str
    module_path: str
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = False
    default_enabled: bool = False
    category: str | None = None
    version: str | None = None
    is_user_invocable: bool | None = None
    depends_on_skills: list[str] = Field(default_factory=list)


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
    manifest_path: str
    trust_tier: TrustTier | None = None
    source_kind: SourceKind = "ontology"


class EmbeddingModelInfo(BaseModel):
    """Global embedding model declaration for the registry."""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    model_file: str = "model.onnx"
    tokenizer_file: str = "tokenizer.json"


class RegistryIndex(BaseModel):
    packages: list[RegistryPackageEntry] = Field(default_factory=list)
    embedding_model: EmbeddingModelInfo = Field(default_factory=EmbeddingModelInfo)


class VendorTarget(BaseModel):
    """Resolution result for a vendor-level install."""
    vendor: str
    packages: list[RegistryPackageEntry]


class PackageTarget(BaseModel):
    """Resolution result for a package-level install."""
    package: RegistryPackageEntry


class SkillTarget(BaseModel):
    """Resolution result for a skill-level install."""
    package: RegistryPackageEntry
    skill_id: str
    standalone: bool
    sibling_deps: list[str] = Field(default_factory=list)


InstallTarget = VendorTarget | PackageTarget | SkillTarget
