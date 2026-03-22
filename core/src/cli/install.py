"""Install commands - package installation and skill management."""

from pathlib import Path

import click
from rich.console import Console

from compiler.registry import (
    enable_skills,
    disable_skills,
    enabled_index_path,
    import_source_repository,
    install_package_from_directory,
    install_package_from_sources,
    list_installed_packages,
)
from compiler.config import OUTPUT_DIR, resolve_ontology_root

console = Console()


@click.command('install-package')
@click.argument('package_path', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--trust-tier', type=click.Choice(['verified', 'trusted', 'community']), default=None)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def install_package_cmd(ctx, package_path, trust_tier, ontology_root_arg):
    """Install a package manifest from a local directory into the global ontology root."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = install_package_from_directory(package_path, root=root, trust_tier=trust_tier)
    console.print(f"[green]Installed package {package.package_id}@{package.version}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print(f"  Root: {package.install_root}")


@click.command('import-source-repo')
@click.argument('repo_ref')
@click.option('--package-id', default=None, help='Override the inferred package id')
@click.option('--trust-tier', type=click.Choice(['verified', 'trusted', 'community']), default='community')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def import_source_repo_cmd(ctx, repo_ref, package_id, trust_tier, ontology_root_arg):
    """Clone/copy a source skill repository into skills/vendor and compile it into ontoskills/vendor."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = import_source_repository(repo_ref, root=root, trust_tier=trust_tier, package_id=package_id)
    console.print(f"[green]Imported source repository {package.package_id}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Source: {package.source}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print("  Enabled skills: (none by default)")


@click.command('install')
@click.argument('package_id')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def install_cmd(ctx, package_id, ontology_root_arg):
    """Install a compiled ontology package by id from configured registry sources."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = install_package_from_sources(package_id, root=root)
    console.print(f"[green]Installed package {package.package_id}@{package.version}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")


@click.command('enable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def enable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Enable all skills in a package or selected skills only."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = enable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Enabled package {package.package_id}[/green]")
    console.print(f"  Enabled skills: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@click.command('disable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def disable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Disable all skills in a package or selected skills only."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = disable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Disabled package {package.package_id}[/green]")
    console.print(f"  Still enabled: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@click.command('list-installed')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def list_installed_cmd(ctx, ontology_root_arg):
    """List installed ontology packages and enabled skills."""
    from . import setup_logging
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
