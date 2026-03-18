"""
Ontoclaw Compiler CLI.

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
from compiler.config import SKILLS_DIR, OUTPUT_DIR

# Get version from pyproject.toml (single source of truth)
try:
    from importlib.metadata import version
    __version__ = version("ontocore")
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
@click.version_option(version=__version__, prog_name="ontocore")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """Ontoclaw Compiler - Compile markdown skills to modular OWL 2 ontology."""
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
      ├── ontoclaw-core.ttl
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

    # Ensure core ontology exists
    core_path = output_path / "ontoclaw-core.ttl"
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
    index_path = output_path / "index.ttl"
    generate_index_manifest(all_skill_paths, index_path, output_path)

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
    else:
        console.print(f"\n[yellow]No changes made[/yellow]")

    index_ttl = output_path / "index.ttl"
    if index_ttl.exists():
        snap = save_snapshot(index_ttl)
        console.print(f"[dim]Snapshot saved to {snap}[/dim]")


@cli.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('-f', '--force', is_flag=True, help='Overwrite existing core ontology')
@click.pass_context
def init_core(ctx, output_dir, force):
    """Initialize the core ontology (ontoclaw-core.ttl).

    Creates the foundational TBox with classes, properties, and predefined states.
    Safe to run multiple times - skips if file exists unless --force is used.
    """
    logger = logging.getLogger(__name__)
    output_path = Path(output_dir)
    core_path = output_path / "ontoclaw-core.ttl"

    if core_path.exists() and not force:
        console.print(f"[yellow]Core ontology already exists at {core_path}[/yellow]")
        console.print("Use --force to overwrite")
        return

    create_core_ontology(core_path)
    console.print(f"[green]Created core ontology at {core_path}[/green]")


@cli.command('query')
@click.argument('query_string')
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
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
        ontoclaw query "SELECT ?s ?n WHERE { ?s oc:nature ?n }" -f json
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
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
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


@cli.command('lint')
@click.option(
    '-o', '--ontology', 'ontology_file',
    default=OUTPUT_DIR + '/index.ttl',
    type=click.Path(exists=False),
    help='Ontology file to lint (default: ./ontoskills/index.ttl)',
)
@click.option(
    '--format', 'fmt',
    default='rich',
    type=click.Choice(['rich', 'json']),
    help='Output format',
)
@click.option('--errors-only', is_flag=True, help='Show only errors, suppress warnings and info')
@click.pass_context
def lint_cmd(ctx, ontology_file, fmt, errors_only):
    """Run static analysis on the compiled ontology.

    Checks for four categories of structural issues without calling the LLM:

    \b
    dead-state       A skill requiresState X but no skill yieldsState X
    circular-dep     A dependsOn B dependsOn ... dependsOn A  [error]
    duplicate-intent Two skills resolve the same intent string  [error]
    orphan-skill     Skill has no dependents and unreachable required states
    """
    import json as json_mod

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SystemExit(1)

    result = lint_ontology(ontology_path)

    if errors_only:
        result.issues = result.errors

    if fmt == 'json':
        data = [
            {
                'severity': i.severity,
                'code': i.code,
                'skill_id': i.skill_id,
                'message': i.message,
                'detail': i.detail,
            }
            for i in result.issues
        ]
        console.print(json_mod.dumps(data, indent=2))
    else:
        _ICONS = {'error': '🔴', 'warning': '⚠️ ', 'info': '🔵'}
        if result.is_clean:
            from rich.panel import Panel
            from rich import box
            console.print(Panel('[bold green]✓ No issues found — ontology is clean[/]', box=box.ROUNDED))
        else:
            from rich.table import Table
            from rich import box
            t = Table(title='Lint Results', box=box.SIMPLE_HEAVY)
            t.add_column('Severity', width=10)
            t.add_column('Code', width=18)
            t.add_column('Skill', width=22)
            t.add_column('Message')
            for issue in result.issues:
                icon = _ICONS.get(issue.severity, '⚪')
                t.add_row(f'{icon} {issue.severity}', issue.code, issue.skill_id, issue.message)
            console.print(t)
            console.print(
                f'\nSummary: [red]{len(result.errors)} error(s)[/] | '
                f'[yellow]{len(result.warnings)} warning(s)[/] | '
                f'[blue]{len([i for i in result.issues if i.severity == "info"])} info[/]'
            )

    if result.has_errors:
        raise SystemExit(1)


@cli.command('explain')
@click.argument('skill_id')
@click.option(
    '-o', '--ontology', 'ontology_file',
    default=OUTPUT_DIR + '/index.ttl',
    type=click.Path(exists=False),
    help='Ontology file to read from (default: ./ontoskills/index.ttl)',
)
@click.pass_context
def explain_cmd(ctx, skill_id, ontology_file):
    """Show a human-readable summary card for a compiled skill.

    \b
    Example:
      ontoclaw explain create-pdf
      ontoclaw explain create-pdf -o ./ontoskills/index.ttl
    """
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        available = list_skill_ids(ontology_path) if ontology_path.exists() else []
        if available:
            console.print(f"[dim]Available skills: {', '.join(available)}[/dim]")
        raise SystemExit(1)

    summary = explain_skill(ontology_path, skill_id)

    if summary is None:
        console.print(f"[red]Skill '{skill_id}' not found in {ontology_path}[/red]")
        available = list_skill_ids(ontology_path)
        if available:
            console.print(f"[dim]Available skills: {', '.join(available)}[/dim]")
        raise SystemExit(1)

    def _row(label, values):
        return f"[bold]{label}[/bold]", ", ".join(values) if values else "[dim]—[/dim]"

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="cyan", width=18)
    t.add_column()

    t.add_row("Type",     f"[green]{summary.skill_type}[/green]")
    t.add_row("Nature",   summary.nature or "[dim]—[/dim]")
    t.add_row(*_row("Intents",         summary.intents))
    t.add_row(*_row("Requires state",  summary.requires_states))
    t.add_row(*_row("Yields state",    summary.yields_states))
    t.add_row(*_row("Handles failure", summary.handles_failures))

    # Show requirements
    if summary.requirements:
        req_strs = []
        for req in summary.requirements:
            opt_marker = " (optional)" if req.is_optional else ""
            req_strs.append(f"{req.requirement_value}{opt_marker}")
        t.add_row(*_row("Requirements", req_strs))

    # Show knowledge nodes summary
    if summary.knowledge_nodes:
        kn_types = {}
        for kn in summary.knowledge_nodes:
            kn_types[kn.node_type] = kn_types.get(kn.node_type, 0) + 1
        kn_strs = [f"{t} ({c})" for t, c in sorted(kn_types.items())]
        t.add_row(*_row("Knowledge", kn_strs))

    if summary.executor:
        t.add_row("Executor",  f"[yellow]{summary.executor}[/yellow]")
    if summary.content_hash:
        t.add_row("Hash",      f"[dim]{summary.content_hash}[/dim]")
    if summary.generated_by:
        t.add_row("Generated by", f"[dim]{summary.generated_by}[/dim]")

    console.print(Panel(t, title=f"[bold]{skill_id}[/bold]", box=box.ROUNDED))

    # Print knowledge nodes in detail if present
    if summary.knowledge_nodes:
        kn_table = Table(title="Knowledge Nodes", box=box.SIMPLE)
        kn_table.add_column("Type", style="cyan", width=16)
        kn_table.add_column("Directive", width=50)
        kn_table.add_column("Severity", width=8)

        for kn in summary.knowledge_nodes:
            severity = kn.severity_level or "—"
            severity_style = {
                "CRITICAL": "red",
                "HIGH": "yellow",
                "MEDIUM": "blue",
                "LOW": "dim",
            }.get(severity, "dim")

            # Truncate directive for display
            directive = kn.directive_content[:80] + "..." if len(kn.directive_content) > 80 else kn.directive_content

            kn_table.add_row(
                kn.node_type,
                directive,
                f"[{severity_style}]{severity}[/{severity_style}]"
            )

        console.print()
        console.print(kn_table)


@cli.command('graph')
@click.option(
    '-o', '--ontology', 'ontology_file',
    default=OUTPUT_DIR + '/index.ttl',
    type=click.Path(exists=False),
    help='Ontology file to visualise (default: ./ontoskills/index.ttl)',
)
@click.option(
    '--format', 'fmt',
    default='mermaid',
    type=click.Choice(['mermaid', 'dot']),
    help='Output format (default: mermaid)',
)
@click.option('--skill', default=None, help='Show only this skill and its direct neighbours')
@click.option('--output', default=None, help='Write output to file instead of stdout')
@click.pass_context
def graph_cmd(ctx, ontology_file, fmt, skill, output):
    """Visualise the skill state transition graph.

    Shows how skills connect through shared states:
    - An edge from Skill A to Skill B means A yieldsState X and B requiresState X
    - This visualizes the execution flow: A must complete before B can run

    \b
    Examples:
      ontoclaw graph                          # Mermaid to stdout
      ontoclaw graph --format dot             # DOT to stdout
      ontoclaw graph --skill create-pdf       # 1-hop subgraph
      ontoclaw graph --output graph.mmd       # save to file
    """
    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SystemExit(1)

    src = build_graph(ontology_path, fmt=fmt, skill_filter=skill)

    if output:
        Path(output).write_text(src)
        console.print(f"[green]Graph saved to {output}[/green]")
    else:
        console.print(src)


@cli.command('diff')
@click.option('--skill', default=None, help='Analyse only this specific skill')
@click.option('--from', 'from_path', default=None, help='Previous .ttl snapshot path')
@click.option('--to', 'to_path', default=None, help='Current .ttl ontology path')
@click.option('--breaking-only', is_flag=True, help='Show only breaking changes (exit code 9 if found)')
@click.option(
    '--format', 'fmt',
    default='rich',
    type=click.Choice(['rich', 'json', 'md']),
    help='Output format',
)
@click.option('--output', default=None, help='Output file path for JSON/MD format')
@click.option('--suggest', is_flag=True, help='Show migration guidance for each breaking change')
def diff_cmd(skill, from_path, to_path, breaking_only, fmt, output, suggest):
    """Detect semantic drift between ontology versions.

    Compares the current ontology against a previous snapshot and reports
    changes classified by impact: breaking, additive, or cosmetic.

    Exit code 9 if breaking changes are detected (useful for CI/CD pipelines).
    """
    if not to_path:
        to_path = './ontoskills/index.ttl'
    if not from_path:
        snap = get_latest_snapshot()
        if not snap:
            raise click.ClickException(
                'No snapshot found. Run compile first to create a snapshot.'
            )
        from_path = str(snap)

    report = compute_diff(from_path, to_path)

    if fmt == 'json':
        out = output or 'drift-report.json'
        export_json(report, out)
    else:
        print_report(report, breaking_only=breaking_only)
        if suggest and report.has_breaking:
            print_suggestions(report.suggestions())

    if report.has_breaking:
        raise SystemExit(9)


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
