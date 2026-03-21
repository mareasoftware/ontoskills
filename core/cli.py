"""
OntoSkills Compiler CLI.

Click-based command-line interface for compiling skills
to modular OWL 2 RDF/Turtle ontology.
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from rdflib import Graph, RDF

from compiler.extractor import generate_skill_id, compute_skill_hash
from compiler.transformer import tool_use_loop
from compiler.security import security_check, SecurityError
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.storage import (
    generate_index_manifest,
    clean_orphaned_files,
)
from compiler.registry import (
    add_registry_source,
    enable_skills,
    disable_skills,
    ensure_registry_layout,
    enabled_index_path,
    import_source_repository,
    install_package_from_directory,
    install_package_from_sources,
    list_installed_packages,
    list_registry_sources,
    rebuild_registry_indexes,
)
from compiler.sparql import execute_sparql, format_results
from compiler.exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from compiler.differ import compute_diff
from compiler.drift_report import print_report, export_json, print_suggestions
from compiler.snapshot import save_snapshot, get_latest_snapshot
from compiler.linter import lint_ontology, LintIssue
from compiler.graph_export import build_graph
from compiler.explainer import explain_skill, list_skill_ids
from compiler.config import SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root

# Get version from pyproject.toml (single source of truth)
try:
    from importlib.metadata import version
    __version__ = version("ontoskills")
except Exception:
    __version__ = "0.5.0"  # Fallback during development

# Configure logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

console = Console()


def setup_logging(verbose: bool, quiet: bool):
    """Configure logging based on verbosity flags."""
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )


def infer_parent_skill_id(skill_dir: Path, input_path: Path) -> str | None:
    """Infer the nearest parent skill from the directory structure.

    A nested skill inherits from the closest ancestor directory that contains
    its own `SKILL.md`. This makes inheritance deterministic and avoids relying
    on the extractor to rediscover obvious filesystem relationships.
    """
    current = skill_dir.parent
    input_root = input_path.resolve()

    while current != input_root and current != current.parent:
        if (current / "SKILL.md").exists():
            return generate_skill_id(current.name)
        current = current.parent

    return None


def enrich_extracted_skill(extracted, skill_dir: Path, input_path: Path):
    """Apply deterministic compiler-side enrichments to extracted skills."""
    parent_skill_id = infer_parent_skill_id(skill_dir, input_path)
    if parent_skill_id and parent_skill_id != extracted.id and parent_skill_id not in extracted.extends:
        extracted.extends.append(parent_skill_id)
    if extracted.extends:
        extracted.depends_on = [
            dependency for dependency in extracted.depends_on
            if dependency not in extracted.extends
        ]
    return extracted


@click.group()
@click.version_option(version=__version__, prog_name="ontoskills")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """OntoSkills Compiler - Compile markdown skills to modular OWL 2 ontology."""
    setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet


@cli.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip security checks')
@click.option('-f', '--force', is_flag=True,
              help='Force recompilation of all skills (bypass cache)')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, force, yes, verbose, quiet):
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

    # Process Rule A: Core Skills (SKILL.md → ontoskill.ttl)
    compiled_skills = []
    skill_output_paths = []

    for skill_file in skill_md_files:
        skill_dir = skill_file.parent
        skill_id = generate_skill_id(skill_dir.name)
        skill_hash = compute_skill_hash(skill_dir)

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

        # Security check
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            try:
                threats, passed = security_check(content, skip_llm=skip_security)
                if not passed:
                    console.print(f"[red]Security check failed for {skill_id}[/red]")
                    for threat in threats:
                        console.print(f"  - {threat.type}: {threat.match}")
                    continue
            except SecurityError as e:
                console.print(f"[red]Security error: {e}[/red]")
                continue

        # LLM extraction
        try:
            extracted = tool_use_loop(skill_dir, skill_hash, skill_id)
            extracted = enrich_extracted_skill(extracted, skill_dir, input_path)
            compiled_skills.append(extracted)
            skill_output_paths.append(output_skill_path)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            continue

    # Process Rule B: Auxiliary Markdown (*.md → *.ttl)
    auxiliary_compiled = []
    for md_file in auxiliary_md_files:
        rel_path = md_file.relative_to(input_path)
        output_ttl_path = output_path / rel_path.with_suffix(".ttl")

        logger.info(f"Processing auxiliary markdown: {md_file.name}")

        # For now, skip auxiliary markdown compilation (can be implemented later)
        # These would need a different extraction pipeline
        logger.debug(f"Auxiliary markdown compilation not yet implemented: {md_file}")
        auxiliary_compiled.append((md_file, output_ttl_path))

    # Process Rule C: Asset Files (direct copy)
    assets_copied = 0
    for asset_file in asset_files:
        rel_path = asset_file.relative_to(input_path)
        output_asset_path = output_path / rel_path

        # Skip if output exists and not forcing (for assets, check if same size)
        if output_asset_path.exists() and not force:
            if output_asset_path.stat().st_size == asset_file.stat().st_size:
                logger.debug(f"Asset unchanged, skipping: {asset_file.name}")
                continue

        # Ensure output directory exists
        output_asset_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy asset
        import shutil
        shutil.copy2(asset_file, output_asset_path)
        assets_copied += 1
        logger.debug(f"Copied asset: {asset_file.name}")

    # Show summary
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

    # Serialize each skill module
    for skill, output_skill_path in zip(compiled_skills, skill_output_paths):
        serialize_skill_to_module(skill, output_skill_path, output_path)

    # Collect all skill output paths for index (including pre-existing)
    all_skill_paths = list(output_path.rglob("ontoskill.ttl"))

    # Generate index manifest
    index_path = ontology_root / "index.ttl"
    generate_index_manifest(all_skill_paths, index_path, ontology_root)
    rebuild_registry_indexes(ontology_root)

    # Summary output
    summary_parts = []
    if compiled_skills:
        summary_parts.append(f"{len(compiled_skills)} skill(s)")
    if assets_copied > 0:
        summary_parts.append(f"{assets_copied} asset(s)")
    if auxiliary_md_files:
        summary_parts.append(f"{len(auxiliary_md_files)} auxiliary md file(s)")

    if summary_parts:
        console.print(f"\n[green]Processed {', '.join(summary_parts)} to {output_path}[/green]")
        console.print(f"[green]Enabled index updated at {enabled_index_path(ontology_root)}[/green]")
    else:
        console.print(f"\n[yellow]No changes made[/yellow]")


@cli.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('-f', '--force', is_flag=True, help='Overwrite existing core ontology')
@click.pass_context
def init_core(ctx, output_dir, force):
    """Initialize the core ontology (ontoskills-core.ttl).

    Creates the foundational TBox with classes, properties, and predefined states.
    Safe to run multiple times - skips if file exists unless --force is used.
    """
    logger = logging.getLogger(__name__)
    output_path = Path(output_dir)
    core_path = output_path / "ontoskills-core.ttl"

    if core_path.exists() and not force:
        console.print(f"[yellow]Core ontology already exists at {core_path}[/yellow]")
        console.print("Use --force to overwrite")
        return

    create_core_ontology(core_path)
    console.print(f"[green]Created core ontology at {core_path}[/green]")


@cli.command('query')
@click.argument('query_string')
@click.option('-o', '--ontology', 'ontology_file', default=str(enabled_index_path(Path(resolve_ontology_root(OUTPUT_DIR)))),
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-f', '--format', 'output_format',
              type=click.Choice(['table', 'json', 'turtle']), default='table',
              help='Output format')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def query_cmd(ctx, query_string, ontology_file, output_format, verbose, quiet):
    """Execute SPARQL query against ontology.

    Example:
        ontoskills query "SELECT ?s ?n WHERE { ?s oc:nature ?n }" -f json
    """
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SPARQLError(f"Ontology not found: {ontology_path}")

    try:
        results, vars = execute_sparql(ontology_path, query_string)

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        output = format_results(results, output_format, vars)
        console.print(output)

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")
        raise


@cli.command('list-skills')
@click.option('-o', '--ontology', 'ontology_file', default=str(enabled_index_path(Path(resolve_ontology_root(OUTPUT_DIR)))),
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def list_skills(ctx, ontology_file, verbose, quiet):
    """List all skills in the ontology."""
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        return

    oc = get_oc_namespace()

    try:
        results, _ = execute_sparql(
            ontology_path,
            f"""PREFIX oc: <{str(oc)}>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?id ?nature WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       oc:nature ?nature .
            }}"""
        )

        if not results:
            console.print("[yellow]No skills found in ontology[/yellow]")
            return

        console.print(f"\n[bold]Skills in ontology ({len(results)}):[/bold]\n")
        for row in results:
            id_val = row.get('id', 'unknown')
            nature = row.get('nature', '')[:60]
            console.print(f"  • {id_val}: {nature}...")

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")


@cli.command('install-package')
@click.argument('package_path', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--trust-tier', type=click.Choice(['verified', 'trusted', 'community']), default=None)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def install_package_cmd(ctx, package_path, trust_tier, ontology_root_arg):
    """Install a package manifest from a local directory into the global ontology root."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = install_package_from_directory(package_path, root=root, trust_tier=trust_tier)
    console.print(f"[green]Installed package {package.package_id}@{package.version}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print(f"  Root: {package.install_root}")


@cli.command('import-source-repo')
@click.argument('repo_ref')
@click.option('--package-id', default=None, help='Override the inferred package id')
@click.option('--trust-tier', type=click.Choice(['verified', 'trusted', 'community']), default='community')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def import_source_repo_cmd(ctx, repo_ref, package_id, trust_tier, ontology_root_arg):
    """Clone/copy a source skill repository into skills/vendor and compile it into ontoskills/vendor."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = import_source_repository(repo_ref, root=root, trust_tier=trust_tier, package_id=package_id)
    console.print(f"[green]Imported source repository {package.package_id}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Source: {package.source}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print("  Enabled skills: (none by default)")


@cli.group('registry')
def registry_group():
    """Manage external registry sources."""


@registry_group.command('add-source')
@click.argument('name')
@click.argument('index_url')
@click.option('--trust-tier', type=click.Choice(['verified', 'trusted', 'community']), default='community')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def registry_add_source_cmd(ctx, name, index_url, trust_tier, ontology_root_arg):
    """Add or replace a configured registry source for compiled ontology packages."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    sources = add_registry_source(name, index_url, root=root, trust_tier=trust_tier, source_kind="ontology")
    console.print(f"[green]Configured registry source {name}[/green]")
    console.print(f"  Index: {index_url}")
    console.print(f"  Total sources: {len(sources.sources)}")


@registry_group.command('list')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def registry_list_cmd(ctx, ontology_root_arg):
    """List configured registry sources."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    sources = list_registry_sources(root=root)
    if not sources.sources:
        console.print("[yellow]No registry sources configured[/yellow]")
        return

    for source in sources.sources:
        console.print(f"\n[bold]{source.name}[/bold] [{source.trust_tier}]")
        console.print(f"  index: {source.index_url}")


@cli.command('install')
@click.argument('package_id')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def install_cmd(ctx, package_id, ontology_root_arg):
    """Install a compiled ontology package by id from configured registry sources."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = install_package_from_sources(package_id, root=root)
    console.print(f"[green]Installed package {package.package_id}@{package.version}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")


@cli.command('enable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def enable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Enable all skills in a package or selected skills only."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = enable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Enabled package {package.package_id}[/green]")
    console.print(f"  Enabled skills: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@cli.command('disable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def disable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Disable all skills in a package or selected skills only."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = disable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Disabled package {package.package_id}[/green]")
    console.print(f"  Still enabled: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@cli.command('list-installed')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def list_installed_cmd(ctx, ontology_root_arg):
    """List installed ontology packages and enabled skills."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    lock = list_installed_packages(root=root)
    if not lock.packages:
        console.print("[yellow]No installed packages[/yellow]")
        return

    for package in lock.packages.values():
        console.print(f"\n[bold]{package.package_id}[/bold] {package.version} [{package.trust_tier}]")
        enabled = [skill.skill_id for skill in package.skills if skill.enabled]
        disabled = [skill.skill_id for skill in package.skills if not skill.enabled]
        console.print(f"  enabled: {', '.join(enabled) if enabled else '(none)'}")
        console.print(f"  disabled: {', '.join(disabled) if disabled else '(none)'}")


@cli.command('rebuild-index')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def rebuild_index_cmd(ctx, ontology_root_arg):
    """Rebuild installed/enabled indices for the global ontology root."""
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    installed, enabled = rebuild_registry_indexes(root=root)
    console.print(f"[green]Rebuilt indices[/green]")
    console.print(f"  installed: {installed}")
    console.print(f"  enabled: {enabled}")


@cli.command('security-audit')
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def security_audit(ctx, input_dir, verbose, quiet):
    """Re-validate all skills against current security patterns."""
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[red]Skills directory not found: {input_path}[/red]")
        return

    skill_dirs = [
        d for d in input_path.rglob("*")
        if d.is_dir() and (d / "SKILL.md").exists()
    ]

    if not skill_dirs:
        console.print("[yellow]No skills found[/yellow]")
        return

    console.print(f"\n[bold]Security audit of {len(skill_dirs)} skill(s):[/bold]\n")

    issues_found = 0
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")

        threats, passed = security_check(content, skip_llm=True)

        if passed:
            console.print(f"  [green]✓[/green] {skill_dir.name}")
        else:
            console.print(f"  [red]✗[/red] {skill_dir.name}")
            for threat in threats:
                console.print(f"      - {threat.type}: {threat.match[:50]}")
            issues_found += 1

    console.print(f"\n[bold]Audit complete:[/bold] {issues_found} issue(s) found")


@cli.command('export-embeddings')
@click.option('--ontology-root', default=None, help='Ontology root directory')
@click.option('--output-dir', default=None, help='Output directory for embeddings')
@click.pass_context
def export_embeddings_cmd(ctx, ontology_root: str | None, output_dir: str | None):
    """Export embeddings for semantic intent discovery.

    Creates ONNX model, tokenizer, and pre-computed intent embeddings
    for use by the MCP server's search_intents tool.
    """
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))

    try:
        from compiler.embeddings.exporter import export_embeddings
    except ImportError as e:
        missing = str(e).split(": ")[-1].strip() if ": " in str(e) else "embeddings dependencies"
        console.print(f"[red]Error: Missing {missing}[/red]")
        console.print("[yellow]Install embeddings support with:[/yellow]")
        console.print("  pip install ontoskills[embeddings]")
        raise SystemExit(1)

    root = Path(ontology_root) if ontology_root else resolve_ontology_root(OUTPUT_DIR)
    out = Path(output_dir) if output_dir else (root / "system" / "embeddings")

    console.print(f"[blue]Exporting embeddings from {root} to {out}[/blue]")

    export_embeddings(root, out)

    console.print(f"[green]Embeddings exported to {out}[/green]")


def main():
    """Entry point with proper error handling."""
    try:
        cli()
    except SkillETLError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)


if __name__ == '__main__':
    main()
