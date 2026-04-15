import re
import functools
import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_skill_id(directory_name: str) -> str:
    slug = directory_name.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]


def normalize_package_id(package_id: str) -> str:
    """Normalize a package ID for use in qualified IDs and URIs.

    Removes npm scope prefix, present (@scope/name -> scope/name).
    Normalizes each segment to lowercase, alphanumeric with dashes.
    """
    normalized = package_id.lstrip("@")
    segments = normalized.split("/")
    normalized_segments = []
    for segment in segments:
        seg = segment.lower()
        seg = re.sub(r'[\s_]+', '-', seg)
        seg = re.sub(r'[^a-z0-9-]', '-', seg)
        seg = re.sub(r'-+', '-', seg)
        seg = seg.strip('-')
        if seg:
            normalized_segments.append(seg)
    return "/".join(normalized_segments) if normalized_segments else "local"


def generate_qualified_skill_id(package_id: str, skill_id: str) -> str:
    return f"{package_id}/{skill_id}"


def generate_sub_skill_id(package_id: str, parent_skill_id: str, filename: str) -> str:
    sub_name = Path(filename).stem
    sub_slug = generate_skill_id(sub_name)
    return f"{package_id}/{parent_skill_id}/{sub_slug}"


def compute_skill_hash(skill_dir: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(
        f for f in skill_dir.rglob('*')
        if f.is_file() and not f.name.startswith('.')
    )
    for file_path in files:
        rel_path = file_path.relative_to(skill_dir)
        hasher.update(str(rel_path).encode('utf-8'))
        hasher.update(file_path.read_bytes())
    return hasher.hexdigest()


def resolve_package_id(skill_dir: Path, input_path: Path | None = None) -> str:
    """Resolve package ID from directory structure.

    The package_id is the path between input_path and skill_dir,
    representing author/package. Falls back to DEFAULT_SKILLS_AUTHOR
    env var if skill is at root of input and no author can be derived,
    and 'local' if unset.

    When input_path is provided, the path between input_path and skill_dir
    is used to derive the package_id. The function auto-detects whether
    input_path is an author directory or a skills root:
    - Author dir (e.g., .agents/skills/obra/): uses input_path.name as author
    - Skills root (e.g., .agents/skills/): derives author from relative path

    When input_path is not provided, falls back to searching for
    package.json/toml (legacy behavior), then 'local'.

    Args:
        skill_dir: Path to the skill directory
        input_path: Root input directory (e.g., .agents/skills/obra/)

    Returns:
        Package ID string (e.g., "obra/superpowers", "coinbase/agentic-wallet-skills")
    """
    if input_path is None:
        return _resolve_package_id_from_manifest(skill_dir)

    try:
        rel = skill_dir.resolve().relative_to(input_path.resolve())
    except ValueError:
        return _resolve_package_id_from_manifest(skill_dir)

    segments = tuple(p for p in rel.parts if p != '.')

    if not segments:
        # skill_dir == input_path
        return os.environ.get('DEFAULT_SKILLS_AUTHOR', 'local')

    # Last segment is the skill directory name — exclude it from package path
    path_parts = segments[:-1]

    # Auto-detect: is input_path an author directory or a skills root?
    # Cached per resolved path to avoid O(N * tree_size) filesystem scans.
    if _is_author_dir_cached(str(input_path.resolve())):
        # input_path is an author dir (batch mode or explicit author path)
        # rel does NOT include the author — prepend it from input_path.name
        author = _normalize_package_id_segment(input_path.resolve().name)
        if path_parts:
            return "/".join([author] + [_normalize_package_id_segment(p) for p in path_parts])
        return author
    else:
        # input_path is a skills root — rel already includes author segment
        if path_parts:
            return "/".join(_normalize_package_id_segment(p) for p in path_parts)
        # Skill directly under root with no package structure — use fallback
        return os.environ.get('DEFAULT_SKILLS_AUTHOR', 'local')


@functools.lru_cache(maxsize=32)
def _is_author_dir_cached(resolved_path: str) -> bool:
    """Cache wrapper for _is_author_dir keyed by resolved path string."""
    return _is_author_dir(Path(resolved_path))


def _is_author_dir(path: Path) -> bool:
    """Heuristic: is this path an author directory vs a skills root?

    Detection strategy (checked in order):
    1. Depth-1 check: if any direct child contains SKILL.md, children are
       skills/packages and the parent is an author directory.
    2. Multi-child check: if multiple children each contain SKILL.md files
       at depth 2+, those children are likely authors (each grouping its
       own packages) → the parent is a skills root, not an author dir.
    3. Default to author dir — most paths passed to resolve_package_id
       are author directories (batch mode recurses into each author).
    """
    try:
        children_with_skills = 0
        for child in path.iterdir():
            if not child.is_dir() or child.name.startswith('.'):
                continue
            # Depth-1: child IS a skill → definitely an author dir
            if (child / "SKILL.md").exists():
                return True
            # Count children that contain skills at any depth
            if any(child.rglob("SKILL.md")):
                children_with_skills += 1
        # Multiple children each containing skills → they are authors,
        # so input_path is a skills root (e.g., skills/obra/, skills/coinbase/)
        if children_with_skills >= 2:
            return False
    except (PermissionError, OSError):
        return False

    # Default: treat as author dir
    return True


def _normalize_package_id_segment(segment: str) -> str:
    """Normalize a single path segment for use in package IDs."""
    slug = segment.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]


def _resolve_package_id_from_manifest(skill_dir: Path) -> str:
    """Legacy fallback: search for package.json or ontoskills.toml."""
    current = skill_dir.resolve()
    for _ in range(8):
        if current == current.parent:
            break
        pkg_json = current / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                if "name" in data:
                    return normalize_package_id(data["name"])
            except (json.JSONDecodeError, KeyError):
                pass
        toml_file = current / "ontoskills.toml"
        if toml_file.exists():
            try:
                content = toml_file.read_text()
                for line in content.splitlines():
                    if line.startswith("name ="):
                        raw_name = line.split("=", 1)[1].strip("\"'")
                        return normalize_package_id(raw_name)
            except Exception:
                pass
        current = current.parent
    return "local"


def compute_sub_skill_hash(md_file: Path) -> str:
    """Compute a content hash for a single markdown file."""
    hasher = hashlib.sha256()
    hasher.update(md_file.read_bytes())
    return hasher.hexdigest()
