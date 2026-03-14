"""Log analysis step — AI-powered crash log forensics."""

from __future__ import annotations

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import LogDiagnosis, TriageResult


async def run_log_analysis(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
) -> list[LogDiagnosis]:
    """Run AI log analysis on crash-looping containers.

    Creates a LogAnalyst and passes all crash contexts for concurrent
    AI-powered log forensics.

    Args:
        client: API client for AI calls.
        triage: Triage results containing crash contexts.
        index: Bundle index for reading events and logs.

    Returns:
        List of AI-generated log diagnoses.
    """
    try:
        from bundle_analyzer.ai.analysts.log_analyst import LogAnalyst

        analyst = LogAnalyst()
        diagnoses = await analyst.analyze_crash_contexts(
            client, triage.crash_contexts, index
        )
        logger.info(
            "Log analysis complete: {} diagnosis(es) for {} crash context(s)",
            len(diagnoses),
            len(triage.crash_contexts),
        )
        return diagnoses
    except (ImportError, AttributeError) as exc:
        logger.warning("Log analyst not available: {}", exc)
        return []
    except Exception as exc:
        logger.error("Log analysis failed: {}", exc)
        return []
