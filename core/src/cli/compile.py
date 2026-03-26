"""Compile command - compile skills into modular ontology."""

import logging
import shutil
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
)
from compiler.config import SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root
from compiler.loader import scan_skill_directory, LoaderError
from compiler.schemas import CompiledSkill

console = Console()


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
    current = skill_dir.parent
    input_root = input_path.resolve()

    while current != input_root and current != current.parent:
        if (current / "SKILL.md").exists():
            # Use frontmatter-based ID from skill_parent_map if available
            if skill_parent_map and current in skill_parent_map:
                qualified_id, _ = skill_parent_map[current]
                # Extract short ID from qualified ID (package/skill_id -> skill_id)
                return qualified_id.split('/')[-1]
            # Fallback to directory name (for cases outside main compilation)
            return generate_skill_id(current.name)
        current = current.parent

    return None


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
      ├── ontoskills-core.ttl
      ├── index.ttl
      └── <mirrored paths>/
          ├── ontoskill.ttl
          ├── *.ttl (auxiliary)
          └── <assets>
    """
    from . import setup_logging
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))
    logger = logging.getLogger(__name__)

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    ontology_root = resolve_ontology_root(output_path)
    ensure_registry_layout(ontology_root)

    # Ensure core ontology exists
    core_path = ontology_root / "ontoskills-core.ttl"
    if not core_path.exists():
        logger.info("Creating core ontology...")
        create_core_ontology(core_path)

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
    auxiliary_md_files = []  # Rule B: *.md → *.ttl
    asset_files = []         # Rule C: direct copy

    for file_path in files_to_process:
        if file_path.name == "SKILL.md":
            skill_md_files.append(file_path)
        elif file_path.suffix == ".md":
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
            error = OrphanSubSkillsError(str(skill_dir), aux_files)
            console.print(f"[red]{error}[/red]")
            raise error

    # Process Rule A: Core Skills (SKILL.md → ontoskill.ttl)
    compiled_skills = []
    skill_output_paths = []

    # Build skill_parent_map for Rule A using frontmatter names (not directory names)
    # This ensures parent/child IDs remain consistent
    # Also cache DirectoryScan results to avoid double scanning
    skill_parent_map = {}  # skill_dir -> (parent_skill_id, package_id)
    dir_scan_cache = {}  # skill_dir -> DirectoryScan (cached from first pass)
    for skill_file in skill_md_files:
        skill_dir = skill_file.parent
        try:
            # Scan to get frontmatter name (canonical skill ID)
            dir_scan = scan_skill_directory(skill_dir)
            dir_scan_cache[skill_dir] = dir_scan  # Cache for reuse
            skill_id = dir_scan.skill_id  # From frontmatter.name
        except LoaderError:
            # Fallback to directory name if frontmatter invalid
            skill_id = generate_skill_id(skill_dir.name)
        package_id = resolve_package_id(skill_dir)
        qualified_parent_id = generate_qualified_skill_id(package_id, skill_id)
        skill_parent_map[skill_dir] = (qualified_parent_id, package_id)

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
        # Get package_id from pre-built map (consistent with parent map)
        _, package_id = skill_parent_map.get(skill_dir, (skill_id, "local"))

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
            extracted = tool_use_loop(skill_dir, skill_hash, skill_id)
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map)

            # Create CompiledSkill with Phase 1 data
            compiled = CompiledSkill(
                **extracted.model_dump(),
                frontmatter=dir_scan.frontmatter,
                files=dir_scan.files,
            )

            # Keep short/local ID for parent skill (sub-skills extend to this short parent ID)
            # Note: compiled.id remains the short skill ID (e.g., "brainstorming"), used as extends_parent
            # Store with package_id for later serialization
            _, pkg_id = skill_parent_map.get(skill_dir, (skill_id, "local"))
            compiled_skills.append((compiled, pkg_id))
            skill_output_paths.append(output_skill_path)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            continue

    # Process Rule B: Auxiliary Markdown (*.md → *.ttl)
    # skill_parent_map already built above for Rule A

    # Process auxiliary files (extraction only - serialization deferred until after dry_run check)
    # Tuple: (extracted, output_ttl_path, qualified_id, extends_parent, extends_parent_qualified)
    sub_skills_to_serialize = []
    for md_file in auxiliary_md_files:
        skill_dir = md_file.parent
        rel_path = md_file.relative_to(input_path)
        output_ttl_path = output_path / rel_path.with_suffix(".ttl")

        # Get parent context
        parent_qualified_id, package_id = skill_parent_map.get(skill_dir, ("local/unknown", "local"))

        # Generate IDs: short ID from filename, qualified ID from full path
        parent_local_id = generate_skill_id(skill_dir.name)
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
            extracted = tool_use_loop(skill_dir, sub_skill_hash, sub_skill_short_id, parent_context=parent_context)
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path, skill_parent_map)

            # Defer serialization until after dry_run check
            sub_skills_to_serialize.append((
                extracted, output_ttl_path, sub_skill_qualified_id,
                parent_local_id, parent_qualified_id
            ))
            logger.info(f"Successfully extracted sub-skill: {sub_skill_short_id}")

        except ExtractionError as e:
            console.print(f"[red]Extraction failed for sub-skill {sub_skill_short_id}: {e}[/red]")
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

    # Show summary
    if compiled_skills:
        console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

        for skill, _ in compiled_skills:
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

    # Serialize each skill module (with qualified ID for URI)
    for (skill, package_id), output_skill_path in zip(compiled_skills, skill_output_paths):
        qualified_id = f"{package_id}/{skill.id}"
        serialize_skill_to_module(
            skill, output_skill_path, output_path,
            qualified_id=qualified_id
        )

    # Serialize sub-skill modules (after dry_run check)
    sub_skills_serialized = 0
    for item in sub_skills_to_serialize:
        extracted, output_ttl_path, qualified_id, extends_parent, extends_parent_qualified = item
        serialize_skill_to_module(
            extracted,
            output_ttl_path,
            output_path,
            qualified_id=qualified_id,
            extends_parent=extends_parent,
            extends_parent_qualified=extends_parent_qualified,
        )
        sub_skills_serialized += 1

    # Copy assets (after dry_run check)
    assets_copied = 0
    for asset_file, output_asset_path in assets_to_copy:
        output_asset_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_file, output_asset_path)
        assets_copied += 1
        logger.debug(f"Copied asset: {asset_file.name}")

    # Collect all skill output paths for index (including sub-skills)
    all_skill_paths = list(output_path.rglob("*.ttl"))
    # Exclude system files
    all_skill_paths = [p for p in all_skill_paths if p.name not in {"ontoskills-core.ttl", "index.ttl", "index.enabled.ttl", "index.installed.ttl"}]

    # Generate index manifest
    index_path = ontology_root / "index.ttl"
    generate_index_manifest(all_skill_paths, index_path, ontology_root)
    rebuild_registry_indexes(ontology_root)

    # Summary output
    summary_parts = []
    if compiled_skills:
        summary_parts.append(f"{len(compiled_skills)} skill(s)")
    if sub_skills_serialized > 0:
        summary_parts.append(f"{sub_skills_serialized} sub-skill(s)")
    if assets_copied > 0:
        summary_parts.append(f"{assets_copied} asset(s)")

    if summary_parts:
        console.print(f"\n[green]Processed {', '.join(summary_parts)} to {output_path}[/green]")
        console.print(f"[green]Enabled index updated at {enabled_index_path(ontology_root)}[/green]")
    else:
        console.print("\n[yellow]No changes made[/yellow]")
