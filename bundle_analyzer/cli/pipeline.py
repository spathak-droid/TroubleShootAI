"""Core analysis pipeline for Bundle Analyzer CLI.

Contains the extraction, triage, and full analysis orchestration logic
that drives both CLI and programmatic usage.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from bundle_analyzer.bundle.extractor import BundleExtractor
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalysisResult, TriageResult
from bundle_analyzer.triage.engine import TriageEngine

if TYPE_CHECKING:
    from bundle_analyzer.ai.engines.diff import DiffResult

console = Console()


async def _run_extraction_and_triage(
    bundle_path: Path,
) -> tuple[BundleIndex, TriageResult]:
    """Extract bundle (if needed), build index, run triage.

    Args:
        bundle_path: Path to a .tar.gz bundle or extracted directory.

    Returns:
        Tuple of (BundleIndex, TriageResult).
    """
    if bundle_path.is_dir():
        index = await BundleIndex.build(bundle_path)
        console.print(
            f"[green]Indexed:[/green] {len(index.namespaces)} namespaces, "
            f"{sum(1 for v in index.has_data.values() if v)} data types"
        )
        engine = TriageEngine()
        result = await engine.run(index)
        return index, result
    else:
        async with BundleExtractor() as extractor:
            root = await extractor.extract(bundle_path)
            console.print(f"[green]Extracted bundle to:[/green] {root}")

            index = await BundleIndex.build(root)
            console.print(
                f"[green]Indexed:[/green] {len(index.namespaces)} namespaces, "
                f"{sum(1 for v in index.has_data.values() if v)} data types"
            )

            engine = TriageEngine()
            result = await engine.run(index)
            return index, result


async def _run_full_analysis(
    bundle_path: Path,
    context_path: Path | None = None,
    compare_path: Path | None = None,
) -> tuple[AnalysisResult, DiffResult | None]:
    """Run the full analysis pipeline: extract, triage, AI.

    Args:
        bundle_path: Path to bundle file or directory.
        context_path: Optional ISV context file.
        compare_path: Optional second bundle for diff.

    Returns:
        Tuple of (AnalysisResult, optional DiffResult).
    """
    from bundle_analyzer.ai.context_injector import ContextInjector
    from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator

    start = time.monotonic()
    diff_result = None

    # Step 1-3: Extract + index + triage
    index, triage = await _run_extraction_and_triage(bundle_path)
    console.print(f"[dim]Triage completed[/dim]")

    # Step 5: Diff comparison if requested
    if compare_path:
        try:
            from bundle_analyzer.ai.engines.diff import DiffEngine

            console.print(f"[cyan]Running diff against {compare_path.name}...[/cyan]")
            compare_index, compare_triage = await _run_extraction_and_triage(compare_path)
            diff_engine = DiffEngine()
            diff_result = await diff_engine.compare(
                index, compare_index, triage, compare_triage
            )
            console.print(f"[green]Diff complete:[/green] {diff_result.summary}")
        except Exception as exc:
            logger.warning("Diff engine failed: {}", exc)
            console.print(f"[yellow]Warning:[/yellow] Diff engine failed: {exc}")

    # Step 6: Context injector
    context_injector = ContextInjector(context_path)

    # Step 7: AI orchestrator (skip if no API key)
    def progress_callback(stage: str, pct: float, message: str) -> None:
        console.print(f"  [dim][{pct:.0%}][/dim] {message}")

    orchestrator = AnalysisOrchestrator()
    analysis_result = await orchestrator.run(
        triage=triage,
        index=index,
        context_injector=context_injector,
        progress_callback=progress_callback,
    )

    return analysis_result, diff_result
