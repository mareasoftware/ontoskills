"""Query commands - SPARQL queries and skill listing."""

from pathlib import Path

import click
from rich.console import Console

from compiler.core_ontology import get_oc_namespace
from compiler.sparql import execute_sparql, format_results
from compiler.exceptions import SPARQLError
from compiler.config import OUTPUT_DIR, resolve_ontology_root
from compiler.registry import enabled_index_path

console = Console()


@click.command('query')
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
        ontocore query "SELECT ?s ?n WHERE { ?s oc:nature ?n }" -f json
    """
    from . import setup_logging
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


@click.command('list-skills')
@click.option('-o', '--ontology', 'ontology_file', default=str(enabled_index_path(Path(resolve_ontology_root(OUTPUT_DIR)))),
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def list_skills(ctx, ontology_file, verbose, quiet):
    """List all skills in the ontology."""
    from . import setup_logging
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
