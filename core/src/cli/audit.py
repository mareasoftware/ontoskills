"""Audit commands - security audit and diff."""

from pathlib import Path

import click
from rich.console import Console

from compiler.security import security_check
from compiler.differ import compute_diff
from compiler.drift_report import print_report, export_json, print_suggestions
from compiler.snapshot import get_latest_snapshot
from compiler.config import SKILLS_DIR

console = Console()


@click.command('security-audit')
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def security_audit(ctx, input_dir, verbose, quiet):
    """Re-validate all skills against current security patterns."""
    from . import setup_logging
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


@click.command('diff')
@click.option('--from', 'from_file', default=None, type=click.Path(exists=False),
              help='Base ontology file (default: latest snapshot)')
@click.option('--to', 'to_file', required=True, type=click.Path(exists=True),
              help='New ontology file to compare against')
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text',
              help='Output format')
@click.option('--output', 'output_path', default=None, type=click.Path(),
              help='Output file for JSON report')
@click.option('--breaking-only', is_flag=True,
              help='Show only breaking changes')
@click.option('--suggest', is_flag=True,
              help='Show migration suggestions for breaking changes')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def diff_cmd(ctx, from_file, to_file, output_format, output_path, breaking_only, suggest, verbose, quiet):
    """Compare two ontology files for semantic drift.

    Detects breaking, additive, and cosmetic changes between two ontology versions.
    Exit codes:
        0 = No breaking changes
        9 = Breaking changes detected

    Example:
        ontocore diff --from old.ttl --to new.ttl
        ontocore diff --to new.ttl --suggest
    """
    from . import setup_logging
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    # Determine base file
    if from_file:
        base_path = Path(from_file)
        if not base_path.exists():
            console.print(f"[red]Base file not found: {base_path}[/red]")
            raise SystemExit(2)
    else:
        base_path = get_latest_snapshot()
        if not base_path:
            console.print("[red]No snapshot found. Use --from to specify a base file.[/red]")
            raise SystemExit(2)

    new_path = Path(to_file)

    # Compute diff
    report = compute_diff(str(base_path), str(new_path))

    # Output
    if output_format == 'json' and output_path:
        export_json(report, output_path)
    else:
        print_report(report, breaking_only=breaking_only)

        if suggest and report.has_breaking:
            suggestions = report.suggestions()
            print_suggestions(suggestions)

    # Exit with appropriate code
    if report.has_breaking:
        raise SystemExit(9)
