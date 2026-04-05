"""Compile command - compile skills into modular ontology."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rdflib import Graph, RDF

from compiler.extractor import (
    generate_skill_id,
    generate_qualified_skill_id,
    generate_sub_skill_id,
    resolve_package_id,
    compute_sub_skill_hash,
)
from compiler.transformer import tool_use_loop
from compiler.security import security_check, SecurityError
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.storage import (
    generate_index_manifest,
    clean_orphaned_files,
    generate_registry_json,
)
from compiler.registry import (
    ensure_registry_layout,
    enabled_index_path,
    rebuild_registry_indexes,
)
from compiler.exceptions import (
    ExtractionError,
    SkillNotFoundError,
    OrphanSubSkillsError,
    OntologyValidationError,
)
from compiler.config import CORE_ONTOLOGY_FILENAME, SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root, ANTHROPIC_MODEL
from compiler.loader import scan_skill_directory, LoaderError
from compiler.schemas import CompiledSkill

console = Console()
logger = logging.getLogger(__name__)


def find_skill_root_dir(start_path: Path, boundary_path: Path) -> Path | None:
    """Walk up from start_path to find the nearest ancestor containing SKILL.md.

    Args:
        start_path: Directory to start searching from
        boundary_path: Stop walking at this path (exclusive)

    Returns:
        The nearest parent directory containing SKILL.md, or None.
    """
    candidate = start_path.resolve()
    boundary = boundary_path.resolve()
    while candidate != boundary and candidate != candidate.parent:
        if (candidate / "SKILL.md").exists():
            return candidate
        candidate = candidate.parent
    return None


def infer_parent_skill_id(skill_dir: Path, input_path: Path, skill_parent_map: dict | None = None) -> str | None:
    """Infer the nearest parent skill from the directory structure.

    A nested skill inherits from the closest ancestor directory that contains
    its own `SKILL.md`. This makes inheritance deterministic and avoids relying
    on the extractor to rediscover obvious filesystem relationships.

    Args:
        skill_dir: Path to the skill directory
        input_path: Root input path
        skill_parent_map: Optional map of skill_dir -> (qualified_id, package_id)
                         to get canonical frontmatter-based skill IDs

    Returns:
        The canonical parent skill ID (from frontmatter if available) or None
    """
    # Normalize skill_parent_map keys for consistent lookups
    normalized_map: dict | None = None
    if skill_parent_map is not None:
        normalized_map = {Path(p).resolve(): v for p, v in skill_parent_map.items()}

    # Walk up from parent of skill_dir to find nearest SKILL.md
    parent_dir = find_skill_root_dir(skill_dir.resolve().parent, input_path.resolve())
    if parent_dir is None:
        return None

    if normalized_map is not None:
        if parent_dir in normalized_map:
            qualified_id, _ = normalized_map[parent_dir]
            return qualified_id.split('/')[-1]
        return None  # Parent has SKILL.md but failed Phase 1
    else:
        return generate_skill_id(parent_dir.name)


def enrich_extracted_skill(extracted, skill_dir: Path, input_path: Path, skill_parent_map: dict | None = None):
    """Apply deterministic compiler-side enrichments to extracted skills."""
    parent_skill_id = infer_parent_skill_id(skill_dir, input_path, skill_parent_map)
    if parent_skill_id and parent_skill_id != extracted.id and parent_skill_id not in extracted.extends:
        extracted.extends.append(parent_skill_id)
    if extracted.extends:
        extracted.depends_on = [
            dependency for dependency in extracted.depends_on
            if dependency not in extracted.extends
        ]
    return extracted


# In-memory error collector for compile-errors.json
_compile_errors: list[dict] = []


def _record_error(skill_id: str, error: str, kind: str = "extraction") -> None:
    """Append a compile error to the in-memory collector."""
    _compile_errors.append({
        "skill_id": skill_id,
        "error": str(error),
        "kind": kind,
        "timestamp": datetime.now().isoformat(),
    })


def _write_error_log(output_path: Path) -> None:
    """Flush collected errors to compile-errors.json in the output directory."""
    if not _compile_errors:
        return
    error_file = output_path / "compile-errors.json"
    existing = []
    if error_file.exists():
        try:
            existing = json.loads(error_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    existing.extend(_compile_errors)
    error_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(_compile_errors)} error(s) to {error_file}")


MAX_EXTRACTION_RETRIES = 3


def retry_extraction(extract_fn, skill_id: str, *args, **kwargs):
    """Call extract_fn with retries on ExtractionError.

    Args:
        extract_fn: Callable that performs LLM extraction (e.g., tool_use_loop)
        skill_id: Skill identifier for logging
        *args, **kwargs: Forwarded to extract_fn

    Returns:
        The extraction result

    Raises:
        ExtractionError: After MAX_EXTRACTION_RETRIES failed attempts
    """
    last_error = None
    for attempt in range(1, MAX_EXTRACTION_RETRIES + 1):
        try:
            return extract_fn(*args, **kwargs)
        except ExtractionError as e:
            last_error = e
            if attempt < MAX_EXTRACTION_RETRIES:
                logger.warning(
                    f"Extraction attempt {attempt}/{MAX_EXTRACTION_RETRIES} failed for {skill_id}: {e}. Retrying..."
                )
            else:
                logger.error(
                    f"Extraction failed for {skill_id} after {MAX_EXTRACTION_RETRIES} attempts: {e}"
                )
    raise last_error

@click.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip LLM security review (regex-based checks still run)')
@click.option('-f', '--force', is_flag=True,
              help='Force recompilation of all skills (bypass cache)')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile_cmd(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, force, yes, verbose, quiet):
    """Compile skills into modular ontology with perfect mirroring.

    Without SKILL_NAME: Compile all files in input directory.
    With SKILL_NAME: Compile specific skill directory.

    File Processing Rules:
      - SKILL.md → ontoskill.ttl (LLM compilation)
      - *.md → *.ttl (LLM compilation)
      - Other files → direct copy (assets)

    Output structure:
      ontoskills/
      ├── core.ttl
      ├── index.ttl
      └── <mirrored paths>/
          ├── ontoskill.ttl
          ├── *.ttl (auxiliary)
          └── <assets>
    """
    from . import setup_logging
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    ontology_root = output_path if output_dir != OUTPUT_DIR else resolve_ontology_root(output_path)
    ensure_registry_layout(ontology_root)

    # Clean orphaned files before compilation
    orphans_removed = clean_orphaned_files(input_path, output_path, dry_run=dry_run)
    if orphans_removed > 0:
        console.print(f"[yellow]Cleaned {orphans_removed} orphaned file(s)[/yellow]")

    # Find all files to process
    if skill_name:
        # Single skill directory - process all files within it
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        files_to_process = [f for f in skill_dir.rglob("*") if f.is_file()]
    else:
        # All files in input directory
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            return

        files_to_process = [f for f in input_path.rglob("*") if f.is_file()]

    if not files_to_process:
        console.print("[yellow]No files found in input directory[/yellow]")
        return

    logger.info(f"Found {len(files_to_process)} file(s) to process")

    # Categorize files by processing rule
    skill_md_files = []      # Rule A: SKILL.md → ontoskill.ttl
    auxiliary_md_files = []  # Rule B: *.md → *.ttl (excluding reference docs)
    asset_files = []         # Rule C: direct copy

    for file_path in files_to_process:
        # Apply same security filters as scan_skill_directory()
        # - Skip symlinked files to avoid copying external targets
        # - Skip paths with backslash (valid on POSIX but problematic)
        if file_path.is_symlink():
            continue
        rel_path = file_path.relative_to(input_path)
        if any('\\' in part for part in rel_path.parts):
            continue

        if file_path.name == "SKILL.md":
            skill_md_files.append(file_path)
        elif file_path.suffix == ".md":
            # Exclude reference/** paths - these are progressive disclosure docs, not sub-skills
            # They're already scanned in Phase 1 for hashing/metadata
            if "reference" in rel_path.parts:
                asset_files.append(file_path)  # Treat as asset, not sub-skill
            else:
                auxiliary_md_files.append(file_path)
        else:
            asset_files.append(file_path)

    logger.info(f"Core skills: {len(skill_md_files)}, Auxiliary md: {len(auxiliary_md_files)}, Assets: {len(asset_files)}")

    # VALIDATION: Sub-skills require parent SKILL.md
    # Group files by directory and check each
    skill_dirs_with_auxiliary = {}
    for md_file in auxiliary_md_files:
        parent_dir = md_file.parent
        if parent_dir not in skill_dirs_with_auxiliary:
            skill_dirs_with_auxiliary[parent_dir] = []
        skill_dirs_with_auxiliary[parent_dir].append(md_file.name)

    for skill_dir, aux_files in skill_dirs_with_auxiliary.items():
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            # Auxiliary content directories (rules, examples, references, etc.)
            # within a valid skill tree are not orphans — just support content.
            logger.warning(
                "Directory '%s' has auxiliary .md files %s but no SKILL.md — treating as support content",
                skill_dir, aux_files,
            )

    # Counters for summary
    skills_serialized = 0
    sub_skills_serialized = 0
    assets_copied = 0
    compiled_skills = []  # Track extracted skills for summary display
    _registry_entries = []  # Per-skill metadata for index.json

    # Build skill_parent_map for Rule A using frontmatter names (not directory names)
    # This ensures parent/child IDs remain consistent
    # Also cache DirectoryScan results to avoid double scanning
    skill_parent_map = {}  # skill_dir -> (qualified_parent_id, package_id)
    dir_scan_cache = {}  # skill_dir -> DirectoryScan (cached from first pass)
    for skill_file in skill_md_files:
        skill_dir = skill_file.parent
        try:
            # Scan to get frontmatter name (canonical skill ID)
            dir_scan = scan_skill_directory(skill_dir)
            dir_scan_cache[skill_dir] = dir_scan  # Cache for reuse
            skill_id = dir_scan.skill_id  # From frontmatter.name
            package_id = resolve_package_id(skill_dir, input_path)
            qualified_parent_id = generate_qualified_skill_id(package_id, skill_id)
            skill_parent_map[skill_dir] = (qualified_parent_id, package_id)
        except LoaderError as e:
            # Phase 1 scan failed; do not add to skill_parent_map
            # so this directory cannot be selected as a parent during inheritance inference
            console.print(f"[red]Phase 1 scan failed while building parent map for {skill_dir.name}: {e}[/red]")
            continue

    # Process Rule A: Core Skills (SKILL.md → ontoskill.ttl)
    # Each skill is serialized to disk immediately after extraction.
    for skill_file in skill_md_files:
        skill_dir = skill_file.parent

        # Phase 1: Use cached scan result (or rescan if not cached)
        dir_scan = dir_scan_cache.get(skill_dir)
        if dir_scan is None:
            try:
                dir_scan = scan_skill_directory(skill_dir)
            except LoaderError as e:
                console.print(f"[red]Phase 1 scan failed for {skill_dir.name}: {e}[/red]")
                continue

        # Use Phase 1 data for IDs and hash
        skill_id = dir_scan.skill_id
        skill_hash = dir_scan.content_hash
        # Derive package_id from directory structure
        package_id = resolve_package_id(skill_dir, input_path)

        logger.info(f"Processing skill: {skill_id}")

        # Compute output path
        rel_path = skill_dir.relative_to(input_path)
        output_skill_path = output_path / rel_path / "ontoskill.ttl"

        # Check if skill is unchanged (unless --force)
        if not force and output_skill_path.exists():
            existing_graph = Graph()
            try:
                existing_graph.parse(output_skill_path, format="turtle")
                oc = get_oc_namespace()
                existing_hash = None
                for skill_uri in existing_graph.subjects(RDF.type, oc.Skill):
                    hash_val = existing_graph.value(skill_uri, oc.contentHash)
                    if hash_val:
                        existing_hash = str(hash_val)
                        break

                if existing_hash == skill_hash:
                    logger.info(f"Skill {skill_id} unchanged (hash match), skipping")
                    continue
            except Exception as e:
                logger.debug(f"Could not read existing skill: {e}")

        # Security check (use Phase 1 content)
        try:
            threats, passed = security_check(dir_scan.skill_md_content, skip_llm=skip_security)
            if not passed:
                console.print(f"[red]Security check failed for {skill_id}[/red]")
                for threat in threats:
                    console.print(f"  - {threat.type}: {threat.match}")
                continue
        except SecurityError as e:
            console.print(f"[red]Security error: {e}[/red]")
            continue

        # Phase 2: LLM extraction
        try:
            extracted = retry_extraction(tool_use_loop, skill_id, skill_dir, skill_hash, skill_id)
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map)

            # Create CompiledSkill with Phase 1 data
            compiled = CompiledSkill(
                **extracted.model_dump(),
                frontmatter=dir_scan.frontmatter,
                files=dir_scan.files,
            )

            # Serialize immediately to disk (unless dry_run)
            if not dry_run:
                _, pkg_id = skill_parent_map.get(skill_dir, (skill_id, "local"))
                qualified_id = f"{pkg_id}/{compiled.id}"
                try:
                    serialize_skill_to_module(
                        compiled, output_skill_path, output_path,
                        qualified_id=qualified_id
                    )
                    skills_serialized += 1
                    # Track for registry index.json
                    rel_skill_path = output_skill_path.relative_to(output_path)
                    _registry_entries.append({
                        "skill_id": compiled.id,
                        "package_id": package_id,
                        "manifest_url": f"./{rel_skill_path}",
                        "generated_by": ANTHROPIC_MODEL,
                        "generated_at": datetime.now().isoformat(),
                    })
                except OntologyValidationError as e:
                    console.print(f"[red]Validation failed for {skill.id}: {e}[/red]")
                    _record_error(skill_id, e, "validation")

            # Track for summary display
            compiled_skills.append(compiled)
            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            _record_error(skill_id, e, "main_skill")
            continue

    # Process Rule B: Auxiliary Markdown (*.md → *.ttl)
    # Each sub-skill is serialized to disk immediately after extraction.
    resolved_parent_map = {Path(p).resolve(): v for p, v in skill_parent_map.items()}
    for md_file in auxiliary_md_files:
        # Walk up to find the parent skill directory (the one with SKILL.md)
        skill_dir = find_skill_root_dir(md_file.parent, input_path)
        if skill_dir is None:
            logger.warning(f"Skipping {md_file.name}: no parent SKILL.md found in ancestor directories")
            continue
        rel_path = md_file.relative_to(input_path)
        output_ttl_path = output_path / rel_path.with_suffix(".ttl")

        # Skip sub-skills whose parent failed Phase 1 (not in skill_parent_map)
        if skill_dir not in resolved_parent_map:
            logger.warning(f"Skipping {md_file.name}: parent skill not in skill_parent_map (failed Phase 1)")
            continue

        # Get parent context
        parent_qualified_id, package_id = resolved_parent_map[skill_dir]

        # Extract parent local ID from qualified ID (uses frontmatter name, not directory name)
        # Format: {package_id}/{skill_id}
        parent_local_id = parent_qualified_id.split('/')[-1] if '/' in parent_qualified_id else parent_qualified_id

        # Generate IDs: short ID from filename, qualified ID from full path
        sub_skill_short_id = generate_skill_id(md_file.stem)  # Normalized/slugified
        sub_skill_qualified_id = generate_sub_skill_id(package_id, parent_local_id, md_file.name)
        sub_skill_hash = compute_sub_skill_hash(md_file)

        logger.info(f"Processing auxiliary markdown: {md_file.name} -> {sub_skill_short_id}")

        # Check cache
        if not force and output_ttl_path.exists():
            existing_graph = Graph()
            try:
                existing_graph.parse(output_ttl_path, format="turtle")
                oc = get_oc_namespace()
                existing_hash = None
                for skill_uri in existing_graph.subjects(RDF.type, oc.Skill):
                    hash_val = existing_graph.value(skill_uri, oc.contentHash)
                    if hash_val:
                        existing_hash = str(hash_val)
                        break

                if existing_hash == sub_skill_hash:
                    logger.info(f"Sub-skill {sub_skill_short_id} unchanged (hash match), skipping")
                    continue
            except Exception as e:
                logger.debug(f"Could not read existing sub-skill: {e}")

        # Get sibling names for context
        sibling_names = [f.name for f in auxiliary_md_files if f.parent == skill_dir and f != md_file]

        # Build parent context
        parent_context = {
            "filename": md_file.name,
            "parent_skill_id": parent_qualified_id,  # Pass qualified ID for prompt context
            "sibling_names": sibling_names
        }

        # LLM extraction with context - use SHORT ID for extracted.id
        try:
            extracted = retry_extraction(tool_use_loop, sub_skill_short_id, skill_dir, sub_skill_hash, sub_skill_short_id, parent_context=parent_context)
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map)

            # Serialize immediately to disk (unless dry_run)
            if not dry_run:
                try:
                    serialize_skill_to_module(
                        extracted,
                        output_ttl_path,
                        output_path,
                        qualified_id=sub_skill_qualified_id,
                        extends_parent=parent_local_id,
                        extends_parent_qualified=parent_qualified_id,
                    )
                    sub_skills_serialized += 1
                    # Sub-skills are NOT tracked in registry — only the parent skill is installable
                except OntologyValidationError as e:
                    console.print(f"[red]Validation failed for sub-skill {extracted.id}: {e}[/red]")
                    _record_error(sub_skill_short_id, e, "validation")

            logger.info(f"Successfully extracted sub-skill: {sub_skill_short_id}")

        except ExtractionError as e:
            console.print(f"[red]Extraction failed for sub-skill {sub_skill_short_id}: {e}[/red]")
            _record_error(sub_skill_short_id, e, "sub_skill")
            continue

    # Process Rule C: Asset Files (collect for later - copy deferred until after dry_run check)
    assets_to_copy = []
    for asset_file in asset_files:
        rel_path = asset_file.relative_to(input_path)
        output_asset_path = output_path / rel_path

        # Skip if output exists and not forcing (for assets, check if same size)
        if output_asset_path.exists() and not force:
            if output_asset_path.stat().st_size == asset_file.stat().st_size:
                logger.debug(f"Asset unchanged, skipping: {asset_file.name}")
                continue

        assets_to_copy.append((asset_file, output_asset_path))

    # Show summary of extracted skills
    if compiled_skills:
        console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

        for skill in compiled_skills:
            console.print(f"\n[bold]{skill.id}[/bold]")
            console.print(f"  Nature: {skill.nature[:80]}...")
            console.print(f"  Genus: {skill.genus}")
            console.print(f"  Intents: {', '.join(skill.intents)}")
            if skill.state_transitions and skill.state_transitions.requires_state:
                console.print(f"  Requires: {', '.join(skill.state_transitions.requires_state)}")
            if skill.state_transitions and skill.state_transitions.yields_state:
                console.print(f"  Yields: {', '.join(skill.state_transitions.yields_state)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation for single skill (only when a specific skill is requested)
    if skill_name and compiled_skills and not yes:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Copy assets (after dry_run check)
    for asset_file, output_asset_path in assets_to_copy:
        output_asset_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_file, output_asset_path)
        assets_copied += 1
        logger.debug(f"Copied asset: {asset_file.name}")

    # Collect only parent skill output paths for index (ontoskill.ttl = parent, *.ttl = sub-skill)
    all_skill_paths = list(output_path.rglob("ontoskill.ttl"))

    # Generate index manifest in system/
    index_path = ontology_root / "system" / "index.ttl"
    generate_index_manifest(all_skill_paths, index_path, ontology_root)
    rebuild_registry_indexes(ontology_root)

    # Flush error log to output directory
    _write_error_log(output_path)

    # Generate registry index.json
    if _registry_entries:
        registry_path = ontology_root / "system" / "index.json"
        generate_registry_json(_registry_entries, registry_path, output_path)

    # Summary output
    summary_parts = []
    if skills_serialized > 0:
        summary_parts.append(f"{skills_serialized} skill(s)")
    if sub_skills_serialized > 0:
        summary_parts.append(f"{sub_skills_serialized} sub-skill(s)")
    if assets_copied > 0:
        summary_parts.append(f"{assets_copied} asset(s)")

    if summary_parts:
        console.print(f"\n[green]Processed {', '.join(summary_parts)} to {output_path}[/green]")
        console.print(f"[green]Enabled index updated at {enabled_index_path(ontology_root)}[/green]")
    else:
        console.print("\n[yellow]No changes made[/yellow]")
