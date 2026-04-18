"""
OntoCore Compiler CLI.

Click-based command-line interface for compiling skills
to modular OWL 2 RDF/Turtle ontology.
"""

import logging
import sys

import click
from rich.console import Console

# Get version from pyproject.toml (single source of truth)
try:
    from importlib.metadata import version
    __version__ = version("ontocore")
except Exception:
    __version__ = "0.9.1"  # Fallback during development

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
@click.version_option(version=__version__, prog_name="ontocore")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """OntoCore Compiler - Compile markdown skills to modular OWL 2 ontology."""
    setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet


# Import and register commands
from .compile import compile_cmd
from .query import query_cmd, list_skills
from .registry import registry_group
from .install import (
    install_package_cmd,
    import_source_repo_cmd,
    install_cmd,
    enable_cmd,
    disable_cmd,
    list_installed_cmd,
)
from .dev import init_core, rebuild_index_cmd
from .audit import security_audit, diff_cmd
from .export import export_embeddings_cmd
from .lint import lint_cmd

# Register commands
cli.add_command(compile_cmd, name='compile')
cli.add_command(query_cmd, name='query')
cli.add_command(list_skills, name='list-skills')
cli.add_command(install_package_cmd, name='install-package')
cli.add_command(import_source_repo_cmd, name='import-source-repo')
cli.add_command(install_cmd, name='install')
cli.add_command(enable_cmd, name='enable')
cli.add_command(disable_cmd, name='disable')
cli.add_command(list_installed_cmd, name='list-installed')
cli.add_command(init_core, name='init-core')
cli.add_command(rebuild_index_cmd, name='rebuild-index')
cli.add_command(security_audit, name='security-audit')
cli.add_command(diff_cmd, name='diff')
cli.add_command(export_embeddings_cmd, name='export-embeddings')
cli.add_command(lint_cmd, name='lint')
cli.add_command(registry_group, name='registry')


def main():
    """Entry point with proper error handling."""
    from compiler.exceptions import SkillETLError
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
