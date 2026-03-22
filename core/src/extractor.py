import re
import hashlib
import json
from pathlib import Path


def generate_skill_id(directory_name: str) -> str:
    slug = directory_name.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]


def normalize_package_id(package_id: str) -> str:
    """
    Normalize a package ID for use in qualified IDs and URIs.

    Ensures the package ID follows the expected slash-separated format
    (e.g., "owner/repo") and normalizes each path segment to be
    QName-compatible (lowercase, alphanumeric with dashes).

    Args:
        package_id: Raw package ID from manifest (e.g., "@scope/My.Package")

    Returns:
        Normalized package ID (e.g., "scope/my-package")
    """
    # Remove npm scope prefix if present (@scope/name -> scope/name)
    normalized = package_id.lstrip("@")

    # Split on slashes to handle each segment independently
    segments = normalized.split("/")

    normalized_segments = []
    for segment in segments:
        # Lowercase and normalize each segment
        seg = segment.lower()
        seg = re.sub(r'[\s_]+', '-', seg)
        seg = re.sub(r'[^a-z0-9-]', '-', seg)
        seg = re.sub(r'-+', '-', seg)
        seg = seg.strip('-')
        if seg:
            normalized_segments.append(seg)

    return "/".join(normalized_segments) if normalized_segments else "local"


def generate_qualified_skill_id(package_id: str, skill_id: str) -> str:
    """
    Build a Qualified ID from package and skill components.

    Format: {package_id}/{skill_id}
    Example: obra/superpowers/brainstorming
    """
    return f"{package_id}/{skill_id}"


def generate_sub_skill_id(package_id: str, parent_skill_id: str, filename: str) -> str:
    """
    Build a Qualified ID for a sub-skill.

    Format: {package_id}/{parent_skill_id}/{sub_skill_name}
    Example: obra/superpowers/brainstorming/planning

    Args:
        package_id: The package namespace (e.g., "obra/superpowers")
        parent_skill_id: The parent skill's local ID (e.g., "brainstorming")
        filename: The markdown filename (e.g., "planning.md")
    """
    # Strip .md extension and slugify
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


def resolve_package_id(skill_dir: Path) -> str:
    """
    Resolve the package ID for a skill directory.

    Resolution order:
    1. package.json in skill directory or ancestors
    2. ontoskills.toml in skill directory or ancestors
    3. Fall back to "local"

    The returned package ID is normalized to ensure QName compatibility
    (lowercase, alphanumeric with dashes, slash-separated).

    Args:
        skill_dir: Path to the skill directory

    Returns:
        Normalized package ID string (e.g., "obra/superpowers" or "local")
    """
    current = skill_dir.resolve()

    while current != current.parent:
        # Check for package.json
        pkg_json = current / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                if "name" in data:
                    return normalize_package_id(data["name"])
            except (json.JSONDecodeError, KeyError):
                pass

        # Check for ontoskills.toml (simple parse)
        toml_file = current / "ontoskills.toml"
        if toml_file.exists():
            try:
                content = toml_file.read_text()
                for line in content.splitlines():
                    if line.startswith("name ="):
                        raw_name = line.split("=", 1)[1].strip().strip('"\'')
                        return normalize_package_id(raw_name)
            except Exception:
                pass

        current = current.parent

    return "local"


def compute_sub_skill_hash(md_file: Path) -> str:
    """
    Compute a content hash for a single markdown file.

    The hash is INDEPENDENT of the parent skill - only the file's
    content is hashed. This enables efficient caching since inheritance
    is resolved at runtime by the Reasoner/MCP.

    Args:
        md_file: Path to the .md file

    Returns:
        SHA-256 hexdigest string
    """
    hasher = hashlib.sha256()
    hasher.update(md_file.read_bytes())
    return hasher.hexdigest()
