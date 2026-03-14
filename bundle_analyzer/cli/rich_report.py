"""Rich console report rendering for Bundle Analyzer CLI.

Contains all Rich-formatted output helpers for printing analysis results
to the terminal with color-coded severity, tables, and panels.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bundle_analyzer.models import (
    AnalysisResult,
    Finding,
    HistoricalEvent,
    PredictedFailure,
    TriageResult,
    UncertaintyGap,
)

console = Console()


def _severity_color(severity: str) -> str:
    """Return a Rich color string for a severity level."""
    return {
        "critical": "bold red",
        "warning": "yellow",
        "info": "dim",
    }.get(severity, "white")


def _print_summary_box(result: AnalysisResult) -> None:
    """Print a top-level summary panel with finding counts."""
    triage = result.triage
    n_critical = len(triage.critical_pods)
    n_high = len(triage.warning_pods) + len(triage.node_issues)
    n_medium = (
        len(triage.deployment_issues)
        + len(triage.config_issues)
        + len(triage.drift_issues)
    )
    n_silence = len(triage.silence_signals)
    n_events = len(triage.warning_events)
    ai_findings = len(result.findings)

    lines = [
        f"[bold red]{n_critical}[/bold red] critical  "
        f"[yellow]{n_high}[/yellow] high  "
        f"[cyan]{n_medium}[/cyan] medium  "
        f"[dim]{n_silence} silence signals, {n_events} warning events[/dim]",
    ]
    if ai_findings:
        lines.append(f"[bold]{ai_findings}[/bold] AI-identified findings")
    else:
        lines.append("[dim]AI analysis not performed (set OPEN_ROUTER_API_KEY or OPENAI_API_KEY to enable)[/dim]")

    lines.append(f"[dim]Analysis completed in {result.analysis_duration_seconds:.1f}s[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Bundle Analysis Summary[/bold]",
        border_style="blue",
    ))


def _print_triage_summary(result: TriageResult) -> None:
    """Print a Rich-formatted table of triage findings."""
    table = Table(title="Triage Findings", show_lines=True)
    table.add_column("Category", style="bold cyan")
    table.add_column("Count", justify="right")
    table.add_column("Details", style="dim")

    sections = [
        ("Critical Pods", "red", result.critical_pods,
         lambda p: f"{p.namespace}/{p.pod_name} ({p.issue_type})"),
        ("Warning Pods", "yellow", result.warning_pods,
         lambda p: f"{p.namespace}/{p.pod_name} ({p.issue_type})"),
        ("Node Issues", "red", result.node_issues,
         lambda n: f"{n.node_name} ({n.condition})"),
        ("Deployment Issues", "yellow", result.deployment_issues,
         lambda d: f"{d.namespace}/{d.name} ({d.issue})"),
        ("Config Issues", "yellow", result.config_issues,
         lambda c: f"{c.resource_type}/{c.resource_name} ({c.issue})"),
        ("Drift Issues", "cyan", result.drift_issues,
         lambda d: f"{d.resource_type}/{d.name} ({d.field})"),
        ("Silence Signals", "magenta", result.silence_signals,
         lambda s: f"{s.namespace}/{s.pod_name} ({s.signal_type})"),
        ("Warning Events", "yellow", result.warning_events,
         lambda e: f"{e.involved_object_name} ({e.reason})"),
    ]

    for label, color, items, fmt in sections:
        if not items:
            continue
        details = ", ".join(fmt(item) for item in items[:5])
        if len(items) > 5:
            details += f" ... +{len(items) - 5} more"
        table.add_row(f"[{color}]{label}[/{color}]", str(len(items)), details)

    if result.rbac_errors:
        table.add_row(
            "RBAC Errors",
            str(len(result.rbac_errors)),
            result.rbac_errors[0][:80] if result.rbac_errors else "",
        )

    console.print(table)


def _print_top_findings(findings: list[Finding]) -> None:
    """Print the top AI findings with descriptions and severity."""
    if not findings:
        return

    console.print()
    console.print("[bold blue]Top Findings (AI Analysis)[/bold blue]")
    console.print()

    for i, f in enumerate(findings[:10], 1):
        color = _severity_color(f.severity)
        console.print(f"  [{color}]{i}. [{f.severity.upper()}][/{color}] {f.resource}")
        console.print(f"     [bold]Symptom:[/bold] {f.symptom}")
        if f.root_cause:
            console.print(f"     [bold]Root cause:[/bold] {f.root_cause}")
        if f.fix:
            console.print(f"     [green]Fix:[/green] {f.fix.description}")
            for cmd in f.fix.commands[:3]:
                console.print(f"       $ {cmd}")
        console.print(f"     [dim]Confidence: {f.confidence:.0%}[/dim]")
        console.print()


def _print_root_cause(result: AnalysisResult) -> None:
    """Print root cause and causal chain if AI analysis ran."""
    if not result.root_cause:
        return

    console.print(Panel(
        result.root_cause,
        title="[bold red]Root Cause[/bold red]",
        border_style="red",
    ))


def _print_fixes(findings: list[Finding]) -> None:
    """Print numbered recommended fixes from AI findings."""
    fixes = [(f, f.fix) for f in findings if f.fix]
    if not fixes:
        return

    console.print()
    console.print("[bold green]Recommended Fixes[/bold green]")
    console.print()

    for i, (finding, fix) in enumerate(fixes[:10], 1):
        risk_color = {
            "safe": "green",
            "disruptive": "red",
            "needs-verification": "yellow",
        }.get(fix.risk, "white")
        console.print(f"  {i}. {fix.description}")
        console.print(f"     [dim]For: {finding.resource}[/dim]  [{risk_color}]Risk: {fix.risk}[/{risk_color}]")
        for cmd in fix.commands[:3]:
            console.print(f"     $ {cmd}")
        console.print()


def _print_uncertainty(gaps: list[UncertaintyGap]) -> None:
    """Print the 'What I Can't Tell You' section."""
    if not gaps:
        return

    impact_colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
    lines: list[str] = []
    for g in gaps[:10]:
        color = impact_colors.get(g.impact, "white")
        lines.append(f"  [{color}]\\[{g.impact}][/{color}] {g.question}")
        if g.reason:
            lines.append(f"     [dim]Reason: {g.reason}[/dim]")
        if g.collect_command:
            lines.append(f"     [cyan]Collect: {g.collect_command}[/cyan]")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="[bold magenta]What I Can't Tell You[/bold magenta]",
        border_style="magenta",
    ))


def _print_timeline(events: list[HistoricalEvent]) -> None:
    """Print a timeline summary of reconstructed events."""
    if not events:
        return

    console.print()
    table = Table(title="Timeline (Reconstructed Events)", show_lines=False)
    table.add_column("Time", style="cyan", width=22)
    table.add_column("Type", style="bold")
    table.add_column("Resource")
    table.add_column("Description", style="dim")

    for ev in events[:20]:
        ts_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        trigger = " *" if ev.is_trigger else ""
        table.add_row(
            ts_str,
            ev.event_type + trigger,
            f"{ev.namespace}/{ev.resource_name}" if ev.namespace else ev.resource_name,
            ev.description[:80],
        )

    console.print(table)
    if len(events) > 20:
        console.print(f"  [dim]... and {len(events) - 20} more events[/dim]")


def _print_predictions(predictions: list[PredictedFailure]) -> None:
    """Print forward-looking failure predictions."""
    if not predictions:
        return

    console.print()
    console.print("[bold yellow]Predicted Failures[/bold yellow]")
    console.print()

    for p in predictions[:5]:
        eta = f"~{p.estimated_eta_seconds}s" if p.estimated_eta_seconds else "imminent"
        console.print(f"  [{_severity_color('warning')}]{p.failure_type}[/] on {p.resource}")
        console.print(f"     ETA: {eta}  Confidence: {p.confidence:.0%}")
        console.print(f"     [green]Prevention:[/green] {p.prevention}")
        console.print()


def _print_rich_report(result: AnalysisResult) -> None:
    """Print the complete Rich report to stdout."""
    console.print()
    _print_summary_box(result)
    console.print()
    _print_triage_summary(result.triage)

    if result.findings:
        _print_root_cause(result)
        _print_top_findings(result.findings)
        _print_fixes(result.findings)

    _print_uncertainty(result.uncertainty)
    _print_timeline(result.timeline)
    _print_predictions(result.predictions)

    console.print()
    console.print(f"[dim]Cluster: {result.cluster_summary}[/dim]")
    console.print()
