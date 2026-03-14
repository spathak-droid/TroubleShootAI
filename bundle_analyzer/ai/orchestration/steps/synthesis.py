"""Synthesis step — cross-correlate analyst findings."""

from __future__ import annotations

from typing import Any

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.synthesis import SynthesisEngine
from bundle_analyzer.models import AnalystOutput, TriageResult


async def run_synthesis(
    client: BundleAnalyzerClient,
    analyst_outputs: list[AnalystOutput],
    triage: TriageResult,
) -> dict[str, Any]:
    """Run the synthesis pass to cross-correlate analyst findings.

    Args:
        client: API client for Claude calls.
        analyst_outputs: All analyst outputs to synthesize.
        triage: Raw triage data for additional context.

    Returns:
        Synthesis result dictionary.
    """
    engine = SynthesisEngine()
    return await engine.synthesize(client, analyst_outputs, triage)
