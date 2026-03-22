"""Registry commands - manage external registry sources."""

from pathlib import Path

import click
from rich.console import Console

from compiler.registry import (
    add_registry_source,
    list_registry_sources,
)
from compiler.config import OUTPUT_DIR, resolve_ontology_root

console = Console()


@click.group('registry')
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
    from . import setup_logging
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
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    sources = list_registry_sources(root=root)
    if not sources.sources:
        console.print("[yellow]No registry sources configured[/yellow]")
        return

    for source in sources.sources:
        console.print(f"\n[bold]{source.name}[/bold] [{source.trust_tier}]")
        console.print(f"  index: {source.index_url}")
