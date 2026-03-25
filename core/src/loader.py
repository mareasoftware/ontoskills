"""
Phase 1: Python-only preprocessing. No LLM calls.

Handles:
- YAML frontmatter parsing with Anthropic-compatible validation
- Directory structure scanning
- File hash computation for progressive disclosure
"""

import re
import hashlib
from pathlib import Path
from typing import Any

import yaml

from compiler.schemas import Frontmatter, FileInfo, DirectoryScan
from compiler.extractor import resolve_package_id, generate_qualified_skill_id


class LoaderError(Exception):
    """Error during Phase 1 loading."""
    pass


# MIME type mapping for common file extensions
MIME_MAP = {
    '.md': 'text/markdown',
    '.py': 'text/x-python',
    '.sh': 'text/x-shellscript',
    '.js': 'text/javascript',
    '.ts': 'text/typescript',
    '.json': 'application/json',
    '.yaml': 'application/x-yaml',
    '.yml': 'application/x-yaml',
    '.txt': 'text/plain',
    '.pdf': 'application/pdf',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.csv': 'text/csv',
    '.html': 'text/html',
    '.css': 'text/css',
    '.xml': 'application/xml',
    '.toml': 'application/toml',
    '.ini': 'text/plain',
    '.cfg': 'text/plain',
    '.env': 'text/plain',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.ico': 'image/x-icon',
}


def mime_type_from_path(path: Path) -> str:
    """Infer MIME type from file extension."""
    return MIME_MAP.get(path.suffix.lower(), 'application/octet-stream')


def parse_frontmatter(content: str) -> Frontmatter:
    """Parse YAML frontmatter from SKILL.md content.

    Validates Anthropic skill authoring requirements:
    - name: max 64 chars, lowercase, hyphens only, no reserved words
    - description: max 1024 chars, no XML tags

    Args:
        content: Full SKILL.md content

    Returns:
        Validated Frontmatter object

    Raises:
        LoaderError: If frontmatter is missing or invalid
    """
    # Match YAML frontmatter between --- delimiters
    # Supports both LF and CRLF, and allows optional trailing newline
    match = re.match(r'^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)', content, re.DOTALL)
    if not match:
        raise LoaderError("SKILL.md missing YAML frontmatter (--- delimiters)")

    try:
        raw = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise LoaderError(f"Invalid YAML frontmatter: {e}")

    if not isinstance(raw, dict):
        raise LoaderError("Frontmatter must be a YAML mapping")

    if 'name' not in raw:
        raise LoaderError("Frontmatter missing required 'name' field")
    if 'description' not in raw:
        raise LoaderError("Frontmatter missing required 'description' field")

    # Build metadata dict from extra fields
    metadata = {k: v for k, v in raw.items()
                if k not in ('name', 'description', 'version')}

    try:
        return Frontmatter(
            name=raw['name'],
            description=raw['description'],
            version=raw.get('version'),
            metadata=metadata
        )
    except ValueError as e:
        raise LoaderError(str(e))


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file content.

    Args:
        path: Path to file

    Returns:
        Hexadecimal SHA-256 hash string
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_skill_directory(skill_dir: Path, package_id: str | None = None) -> DirectoryScan:
    """Phase 1: Scan skill directory and extract filesystem metadata.

    Performs:
    - Frontmatter parsing and validation
    - Directory structure enumeration
    - File hash computation for progressive disclosure
    - Security check for path traversal attempts

    Args:
        skill_dir: Path to skill directory containing SKILL.md
        package_id: Optional package ID (resolved from parents if not provided)

    Returns:
        DirectoryScan with all Phase 1 data

    Raises:
        LoaderError: If SKILL.md missing or frontmatter invalid
    """
    skill_dir = skill_dir.resolve()
    skill_md = skill_dir / 'SKILL.md'

    if not skill_md.exists():
        raise LoaderError(f"Skill directory missing SKILL.md: {skill_dir}")

    content = skill_md.read_text(encoding='utf-8')
    frontmatter = parse_frontmatter(content)

    # Resolve package ID if not provided
    if package_id is None:
        package_id = resolve_package_id(skill_dir)

    # Use frontmatter name as canonical skill ID
    skill_id = frontmatter.name
    qualified_id = generate_qualified_skill_id(package_id, skill_id)

    # Scan all files
    files: list[FileInfo] = []
    dir_hash = hashlib.sha256()

    for f in sorted(skill_dir.rglob('*')):
        # Skip hidden files and symlinks (security: prevent escape via symlink)
        if f.is_file() and not f.name.startswith('.') and not f.is_symlink():
            # Use as_posix() for cross-platform compatibility (always uses /)
            rel_path = f.relative_to(skill_dir).as_posix()

            # SECURITY: Path traversal protection
            # Reject paths containing '..' in any path component
            if '..' in rel_path.split('/'):
                continue

            # SECURITY: Verify resolved path stays within skill_dir
            try:
                resolved = f.resolve()
                resolved.relative_to(skill_dir)
            except ValueError:
                # Path escapes skill_dir boundary
                continue

            file_hash = compute_file_hash(f)
            files.append(FileInfo(
                relative_path=rel_path,
                content_hash=file_hash,
                file_size=f.stat().st_size,
                mime_type=mime_type_from_path(f)
            ))

            # Update directory hash
            dir_hash.update(rel_path.encode())
            dir_hash.update(file_hash.encode())

    # Build file tree string for LLM context
    file_tree_lines = [f"  {f.relative_path} ({f.file_size} bytes, {f.mime_type})"
                       for f in files]
    file_tree = "\n".join(file_tree_lines)

    return DirectoryScan(
        frontmatter=frontmatter,
        skill_id=skill_id,
        qualified_id=qualified_id,
        content_hash=dir_hash.hexdigest(),
        provenance_path=str(skill_dir),
        files=files,
        skill_md_content=content,
        file_tree=file_tree
    )
