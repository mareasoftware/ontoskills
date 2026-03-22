"""Source compilation helpers for registry packages."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from compiler.core_ontology import get_oc_namespace

IGNORED_SOURCE_DIRS = {".git", "node_modules", ".venv", "target", "dist", "build", "__pycache__"}
SKILL_SCRIPT_PATH_RE = re.compile(r"skills/([A-Za-z0-9._-]+)/([^\s\"']+)")
RELATIVE_SCRIPT_PATH_RE = re.compile(r"(?<![A-Za-z0-9._/-])scripts/([^\s\"']+)")
BROKEN_ABSOLUTE_PATH_RE = re.compile(r"~/\.claude//(?=[A-Za-z])")


def compile_source_tree(source_root: Path, compiled_root: Path) -> None:
    """Compile a source tree using the CLI compiler."""
    cli_path = Path(__file__).resolve().parent.parent / "cli.py"
    command = [
        sys.executable,
        str(cli_path),
        "compile",
        "-i", str(source_root),
        "-o", str(compiled_root),
        "-y", "-f",
    ]
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Source package compilation failed with code {result.returncode}: {result.stderr or result.stdout}"
        )


def rewrite_compiled_payload_paths(compiled_root: Path) -> None:
    """Rewrite payload paths in compiled TTL files."""
    for ttl_path in compiled_root.rglob("*.ttl"):
        original = ttl_path.read_text(encoding="utf-8")
        rewritten = rewrite_payload_text(original, compiled_root, ttl_path)
        if rewritten != original:
            ttl_path.write_text(rewritten, encoding="utf-8")


def rewrite_payload_text(payload: str, compiled_root: Path, ttl_path: Path) -> str:
    """Rewrite payload paths in TTL content."""
    def replace_skill_path(match: re.Match[str]) -> str:
        skill_id = match.group(1)
        relative_path = Path(match.group(2))
        for candidate in (
            compiled_root / ".claude" / "skills" / skill_id / relative_path,
            compiled_root / "src" / skill_id / relative_path,
            compiled_root / skill_id / relative_path,
        ):
            if candidate.exists():
                return candidate.resolve().as_posix()
        return match.group(0)

    def replace_relative_script_path(match: re.Match[str]) -> str:
        relative_path = Path("scripts") / match.group(1)
        candidate = ttl_path.parent / relative_path
        if candidate.exists():
            return candidate.resolve().as_posix()
        return match.group(0)

    rewritten = BROKEN_ABSOLUTE_PATH_RE.sub("/", payload)
    rewritten = SKILL_SCRIPT_PATH_RE.sub(replace_skill_path, rewritten)
    rewritten = RELATIVE_SCRIPT_PATH_RE.sub(replace_relative_script_path, rewritten)
    return rewritten


def materialize_source_repository(repo_ref: str, tmp_dir: Path) -> tuple[Path, str]:
    """Clone or resolve a source repository."""
    local_path = Path(repo_ref)
    if local_path.exists():
        return local_path.resolve(), str(local_path.resolve())

    repo_dir = tmp_dir / "repo"
    command = ["git", "clone", "--depth", "1", repo_ref, str(repo_dir)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to clone source repository '{repo_ref}': {result.stderr or result.stdout}")
    return repo_dir, repo_ref


def infer_source_package_id(repo_ref: str, repo_path: Path) -> str:
    """Infer a package ID from a repository reference."""
    from urllib.parse import urlparse
    parsed = urlparse(repo_ref)
    if parsed.scheme in ("http", "https") and parsed.netloc.endswith("github.com"):
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            owner = slugify_identifier(parts[0])
            repo = slugify_identifier(parts[1].removesuffix(".git"))
            return f"{owner}/{repo}"
    return slugify_identifier(repo_path.name)


def slugify_identifier(value: str) -> str:
    """Convert a string to a URL-safe identifier."""
    normalized = []
    for char in value.lower():
        if char.isalnum():
            normalized.append(char)
        elif not normalized or normalized[-1] != "-":
            normalized.append("-")
    return "".join(normalized).strip("-") or "imported"


def is_ignored_source_path(path: Path, source_root: Path) -> bool:
    """Check if a path should be ignored during source copy."""
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return True
    return any(part in IGNORED_SOURCE_DIRS for part in relative.parts)


def copy_source_tree(source_root: Path, destination_root: Path) -> None:
    """Copy a source tree, excluding ignored directories."""
    for path in source_root.rglob("*"):
        if is_ignored_source_path(path, source_root):
            continue
        relative = path.relative_to(source_root)
        destination = destination_root / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def discover_skill_entries(source_root: Path) -> list[tuple[str, Path]]:
    """Discover SKILL.md files and their expected output paths."""
    skills: list[tuple[str, Path]] = []
    for skill_file in source_root.rglob("SKILL.md"):
        if is_ignored_source_path(skill_file, source_root):
            continue
        skill_dir = skill_file.parent
        relative = skill_dir.relative_to(source_root)
        module_path = relative / "ontoskill.ttl"
        skill_id = slugify_identifier(skill_dir.name)
        skills.append((skill_id, module_path))
    skills.sort(key=lambda item: (str(item[1]), item[0]))
    return skills
