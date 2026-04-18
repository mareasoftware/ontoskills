"""
OntoCore lint command — run structural analysis on compiled TTL files.
"""

import sys

import click
from rich.console import Console
from rich.table import Table

from compiler.linter import lint_ontology, LintResult

console = Console()

SEVERITY_STYLE = {
    "error": "[bold red]error[/]",
    "warning": "[bold yellow]warning[/]",
    "info": "[bold blue]info[/]",
}


@click.command("lint")
@click.argument("ttl_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--errors-only", is_flag=True, help="Only show errors")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def lint_cmd(ttl_path: str, errors_only: bool, as_json: bool):
    """Run structural lint checks on a compiled TTL file."""
    result: LintResult = lint_ontology(ttl_path)

    if errors_only:
        issues = result.errors
    else:
        issues = result.issues

    if not issues:
        if as_json:
            click.echo("[]")
        else:
            console.print("[bold green]✔ No issues found.[/]")
        sys.exit(0)

    if as_json:
        import json
        click.echo(json.dumps([
            {"severity": i.severity, "code": i.code, "skill_id": i.skill_id, "message": i.message, "detail": i.detail}
            for i in issues
        ], indent=2))
        sys.exit(1 if result.has_errors else 0)

    table = Table(title="Lint Results", show_lines=True)
    table.add_column("Severity", width=10)
    table.add_column("Code", width=18)
    table.add_column("Skill", width=24)
    table.add_column("Message", min_width=40)
    table.add_column("Detail", min_width=30)

    for issue in issues:
        table.add_row(
            SEVERITY_STYLE.get(issue.severity, issue.severity),
            issue.code,
            issue.skill_id,
            issue.message,
            issue.detail,
        )

    console.print(table)
    console.print(f"\n{len(issues)} issue(s): {len(result.errors)} errors, {len(result.warnings)} warnings")

    sys.exit(1 if result.has_errors else 0)
