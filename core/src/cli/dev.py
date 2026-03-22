"""Dev commands - initialization and index rebuilding."""

from pathlib import Path

import click
from rich.console import Console

from compiler.core_ontology import create_core_ontology
from compiler.registry import rebuild_registry_indexes
from compiler.config import OUTPUT_DIR, resolve_ontology_root

console = Console()


@click.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('-f', '--force', is_flag=True, help='Overwrite existing core ontology')
@click.pass_context
def init_core(ctx, output_dir, force):
    """Initialize the core ontology (ontoskills-core.ttl).

    Creates the foundational TBox with classes, properties, and predefined states.
    Safe to run multiple times - skips if file exists unless --force is used.
    """
    import logging
    _logger = logging.getLogger(__name__)  # Use underscore prefix for internal use
    output_path = Path(output_dir)
    core_path = output_path / "ontoskills-core.ttl"

    if core_path.exists() and not force:
        console.print(f"[yellow]Core ontology already exists at {core_path}[/yellow]")
        console.print("Use --force to overwrite")
        return

    create_core_ontology(core_path)
    console.print(f"[green]Created core ontology at {core_path}[/green]")


@click.command('rebuild-index')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def rebuild_index_cmd(ctx, ontology_root_arg):
    """Rebuild installed/enabled indices for the global ontology root."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    installed, enabled = rebuild_registry_indexes(root=root)
    console.print("[green]Rebuilt indices[/green]")
    console.print(f"  installed: {installed}")
    console.print(f"  enabled: {enabled}")
