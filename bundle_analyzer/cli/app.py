"""Typer application definition and CLI commands for Bundle Analyzer.

Defines the ``bundle-analyzer`` command with ``analyze``, ``serve``,
and ``version`` subcommands.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from bundle_analyzer.cli.diff_report import _print_diff_report
from bundle_analyzer.cli.html_report import _generate_html_report
from bundle_analyzer.cli.pipeline import _run_full_analysis
from bundle_analyzer.cli.rich_report import _print_rich_report

# Load .env from the project root (or cwd)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv()  # also try cwd

app = typer.Typer(
    name="bundle-analyzer",
    help="Bundle Analyzer -- AI-powered Kubernetes support bundle forensics engine",
)

console = Console()


@app.command()
def analyze(
    bundle_path: Path = typer.Argument(
        ..., help="Path to support bundle .tar.gz or extracted directory"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Save HTML report to file"
    ),
    context: Path | None = typer.Option(
        None, "--context", help="ISV context file (Helm values, README)"
    ),
    compare: Path | None = typer.Option(
        None, "--compare", help="Second bundle for diff analysis"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug logging"
    ),
) -> None:
    """Analyze a Kubernetes support bundle and surface root causes."""
    # Configure logging
    if not verbose:
        logger.remove()
        logger.add(sys.stderr, level="WARNING")

    # Step 1: Validate bundle path
    bundle_path = Path(bundle_path).resolve()
    if not bundle_path.exists():
        console.print(f"[red]Error:[/red] Bundle not found: {bundle_path}")
        raise typer.Exit(code=1)

    # Validate compare path if given
    compare_path = None
    if compare:
        compare_path = Path(compare).resolve()
        if not compare_path.exists():
            console.print(f"[red]Error:[/red] Compare bundle not found: {compare_path}")
            raise typer.Exit(code=1)

    # Validate context path if given
    context_path = None
    if context:
        context_path = Path(context).resolve()
        if not context_path.exists():
            console.print(f"[yellow]Warning:[/yellow] Context file not found: {context_path}")
            context_path = None

    console.print(Panel(
        f"Analyzing [bold]{bundle_path.name}[/bold]"
        + (f"\nComparing with [bold]{compare_path.name}[/bold]" if compare_path else ""),
        title="Bundle Analyzer",
    ))

    # Check API key status
    has_api_key = any(os.environ.get(k) for k in (
        "OPEN_ROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"
    ))
    if not has_api_key:
        console.print(
            "[yellow]Note:[/yellow] No AI provider key set. "
            "Running triage-only mode (no AI analysis)."
        )

    # Run analysis
    start = time.monotonic()
    analysis_result, diff_result = asyncio.run(
        _run_full_analysis(bundle_path, context_path, compare_path)
    )
    elapsed = time.monotonic() - start
    console.print(f"[dim]Total analysis completed in {elapsed:.1f}s[/dim]")

    # Print diff report if available
    if diff_result:
        _print_diff_report(diff_result)

    # Print rich report to stdout
    _print_rich_report(analysis_result)

    if output:
        # Save HTML report
        output_path = Path(output).resolve()
        html_content = _generate_html_report(analysis_result)
        output_path.write_text(html_content, encoding="utf-8")
        console.print(f"[green]HTML report saved to:[/green] {output_path}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8001, "--port", "-p", help="Port to serve on"),
    dev: bool = typer.Option(
        False, "--dev", help="Enable CORS for localhost:3000 (Next.js dev server)"
    ),
    bundle_path: Path | None = typer.Argument(
        None, help="Optional bundle path to pre-load"
    ),
) -> None:
    """Serve the Bundle Analyzer web API via uvicorn."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]Error:[/red] uvicorn not installed.\n"
            "  [dim]pip install uvicorn[standard][/dim]"
        )
        raise typer.Exit(code=1) from None

    display_host = host if host != "0.0.0.0" else "localhost"
    console.print(
        f"[bold green]Serving Bundle Analyzer API at[/bold green] "
        f"http://{display_host}:{port}"
    )
    if dev:
        console.print("[dim]CORS enabled for http://localhost:3000[/dim]")

    uvicorn.run(
        "bundle_analyzer.api.main:app",
        host=host,
        port=port,
        reload=dev,
    )


@app.command()
def version() -> None:
    """Show the Bundle Analyzer version."""
    console.print("[bold]Bundle Analyzer[/bold] v0.1.0")
