"""Export commands - embeddings export."""

from pathlib import Path

import click
from rich.console import Console

from compiler.config import OUTPUT_DIR, resolve_ontology_root

console = Console()


@click.command('export-embeddings')
@click.option('--ontology-root', default=None, help='Ontology root directory')
@click.option('--output-dir', default=None, help='Output directory for embeddings')
@click.pass_context
def export_embeddings_cmd(ctx, ontology_root: str | None, output_dir: str | None):
    """Export embeddings for semantic intent discovery.

    Creates ONNX model, tokenizer, and pre-computed intent embeddings
    for use by the MCP server's search_intents tool.
    """
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))

    try:
        from compiler.embeddings.exporter import export_embeddings
    except ImportError as e:
        missing = str(e).split(": ")[-1].strip() if ": " in str(e) else "embeddings dependencies"
        console.print(f"[red]Error: Missing {missing}[/red]")
        console.print("[yellow]Install embeddings support with:[/yellow]")
        console.print("  pip install ontocore[embeddings]")
        raise SystemExit(1)

    root = Path(ontology_root) if ontology_root else resolve_ontology_root(OUTPUT_DIR)
    out = Path(output_dir) if output_dir else (root / "system" / "embeddings")

    console.print(f"[blue]Exporting embeddings from {root} to {out}[/blue]")

    export_embeddings(root, out)

    console.print(f"[green]Embeddings exported to {out}[/green]")
