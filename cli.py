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

from extractor import generate_skill_id, compute_skill_hash
from transformer import tool_use_loop
from security import security_check, SecurityError
from loader import (
    create_core_ontology,
    serialize_skill_to_module,
    generate_index_manifest,
    get_oc_namespace,
)
from sparql import execute_sparql, format_results
from exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from config import SKILLS_DIR, OUTPUT_DIR

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


@click.group()
@click.version_option(version="0.2.0", prog_name="ontoclaw-compiler")
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
              type=click.Path(), help='Output directory for semantic-skills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip security checks')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, yes, verbose, quiet):
    """Compile skills into modular ontology.

    Without SKILL_NAME: Compile all skills in input directory.
    With SKILL_NAME: Compile specific skill.

    Output structure:
      semantic-skills/
      ├── ontoclaw-core.ttl
      ├── index.ttl
      └── <mirrored paths>/skill.ttl
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

    # Find skills to compile
    if skill_name:
        # Single skill
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        skill_dirs = [skill_dir]
    else:
        # All skills - find directories containing SKILL.md
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            return

        skill_dirs = [
            d for d in input_path.rglob("*")
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        if not skill_dirs:
            console.print("[yellow]No SKILL.md files found in input directory[/yellow]")
            return

    logger.info(f"Found {len(skill_dirs)} skill(s) to compile")

    # Process each skill
    compiled_skills = []
    skill_output_paths = []

    for skill_dir in skill_dirs:
        skill_id = generate_skill_id(skill_dir.name)
        skill_hash = compute_skill_hash(skill_dir)

        logger.info(f"Processing skill: {skill_id}")

        # Security check
        skill_file = skill_dir / "SKILL.md"
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
            compiled_skills.append(extracted)

            # Calculate output path (mirror directory structure)
            rel_path = skill_dir.relative_to(input_path)
            output_skill_path = output_path / rel_path / "skill.ttl"
            skill_output_paths.append(output_skill_path)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            continue

    if not compiled_skills:
        console.print("[yellow]No skills compiled[/yellow]")
        return

    # Show preview
    console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

    for skill in compiled_skills:
        console.print(f"\n[bold]{skill.id}[/bold]")
        console.print(f"  Nature: {skill.nature[:80]}...")
        console.print(f"  Genus: {skill.genus}")
        console.print(f"  Intents: {', '.join(skill.intents)}")
        if skill.state_transitions.requires_state:
            console.print(f"  Requires: {', '.join(skill.state_transitions.requires_state)}")
        if skill.state_transitions.yields_state:
            console.print(f"  Yields: {', '.join(skill.state_transitions.yields_state)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation
    if not yes and skill_name:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Serialize each skill module
    for skill, output_skill_path in zip(compiled_skills, skill_output_paths):
        serialize_skill_to_module(skill, output_skill_path, output_path)

    # Generate index manifest
    index_path = output_path / "index.ttl"
    generate_index_manifest(skill_output_paths, index_path, output_path)

    console.print(f"\n[green]Compiled {len(compiled_skills)} skill(s) to {output_path}[/green]")


@cli.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for semantic-skills')
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
