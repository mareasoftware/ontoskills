"""
Report formatter for OntoSkills Skill Drift Detector.

Renders a DriftReport in the terminal using Rich, or serializes it
to JSON for CI/CD pipelines.
"""

import json

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from compiler.differ import DriftReport, MigrationSuggestion

console = Console()

ICONS = {'breaking': '🔴', 'additive': '🟢', 'cosmetic': '🔵'}


def print_report(report: DriftReport, breaking_only: bool = False) -> None:
    """Print the drift report to the terminal with Rich formatting."""
    if report.is_clean:
        console.print(
            Panel(
                '[bold green]✓ No drift detected — ontology is consistent[/]',
                box=box.ROUNDED,
            )
        )
        return

    # Removed skills are always breaking
    if report.removed_skills:
        console.print(
            Panel(
                '[bold red]REMOVED SKILLS (BREAKING)[/]\n'
                + '\n'.join(f'  🔴 {s}' for s in report.removed_skills),
                box=box.HEAVY_EDGE,
                border_style='red',
            )
        )

    if report.added_skills and not breaking_only:
        console.print('[bold green]+ ADDED SKILLS[/]')
        for s in report.added_skills:
            console.print(f'  🟢 {s}')

    changes = report.breaking
    if not breaking_only:
        changes = changes + report.additive + report.cosmetic

    if changes:
        t = Table(title='Detected Changes', box=box.SIMPLE_HEAVY)
        t.add_column('Impact', style='bold', width=12)
        t.add_column('Skill', width=20)
        t.add_column('Category', width=14)
        t.add_column('Description')
        for c in changes:
            icon = ICONS.get(c.change_type, '⚪')
            t.add_row(f'{icon} {c.change_type}', c.skill_id, c.category, c.description)
        console.print(t)

    console.print(
        f'\nSummary: [red]{len(report.breaking)} breaking[/] | '
        f'[green]{len(report.additive)} additive[/] | '
        f'[blue]{len(report.cosmetic)} cosmetic[/]'
    )


def print_suggestions(suggestions: list[MigrationSuggestion]) -> None:
    """Print migration suggestions for all breaking changes."""
    if not suggestions:
        return

    console.print("\n[bold yellow]Migration Guidance[/bold yellow]")
    for i, s in enumerate(suggestions, 1):
        console.print(f"\n[bold]{i}. {s.summary}[/bold]")
        console.print(f"   [cyan]Action:[/cyan] {s.action}")
        console.print("   [dim]SPARQL to find affected agents:[/dim]")
        for line in s.sparql_query.splitlines():
            console.print(f"     [dim]{line}[/dim]")


def export_json(report: DriftReport, output_path: str) -> None:
    """Serialize the DriftReport to JSON for CI/CD pipelines."""
    data = {
        'has_breaking': report.has_breaking,
        'removed_skills': report.removed_skills,
        'added_skills': report.added_skills,
        'breaking': [vars(c) for c in report.breaking],
        'additive': [vars(c) for c in report.additive],
        'cosmetic': [vars(c) for c in report.cosmetic],
    }
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    console.print(f'[dim]Report saved to {output_path}[/]')
