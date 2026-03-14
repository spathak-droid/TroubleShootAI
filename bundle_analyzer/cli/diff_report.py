"""Diff report rendering for Bundle Analyzer CLI.

Prints Rich-formatted diff reports comparing two support bundles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from bundle_analyzer.ai.engines.diff import DiffResult

console = Console()


def _print_diff_report(diff_result: DiffResult) -> None:
    """Print a Rich-formatted diff report to stdout.

    Args:
        diff_result: The result of comparing two bundles.
    """
    from bundle_analyzer.ai.engines.diff import DiffResult  # noqa: F811

    console.print()
    console.print(Panel(
        diff_result.summary,
        title="[bold]Bundle Diff[/bold]",
        border_style="blue",
    ))

    if diff_result.new_findings:
        console.print()
        console.print("[bold red]New Findings (appeared in AFTER bundle)[/bold red]")
        for f in diff_result.new_findings:
            console.print(f"  [red]+[/red] [{f.category}] {f.resource}: {f.description}")

    if diff_result.resolved_findings:
        console.print()
        console.print("[bold green]Resolved Findings (gone in AFTER bundle)[/bold green]")
        for f in diff_result.resolved_findings:
            console.print(f"  [green]-[/green] [{f.category}] {f.resource}: {f.description}")

    if diff_result.worsened_findings:
        console.print()
        console.print("[bold yellow]Worsened Findings[/bold yellow]")
        for f in diff_result.worsened_findings:
            console.print(f"  [yellow]![/yellow] [{f.category}] {f.resource}: {f.description}")

    delta = diff_result.resource_delta
    if delta:
        console.print()
        table = Table(title="Resource Delta", show_lines=False)
        table.add_column("Metric")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        for key in sorted(delta.keys()):
            if key.endswith("_before"):
                base = key.replace("_before", "")
                label = base.replace("_", " ").title()
                before_val = str(delta.get(f"{base}_before", "?"))
                after_val = str(delta.get(f"{base}_after", "?"))
                table.add_row(label, before_val, after_val)
        console.print(table)

    console.print()
