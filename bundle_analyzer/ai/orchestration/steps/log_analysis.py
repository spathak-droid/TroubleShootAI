"""Log analysis step — AI-powered crash log forensics."""

from __future__ import annotations

import asyncio

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import LogDiagnosis, TriageResult

# Timeout for the entire log analysis batch (seconds)
LOG_ANALYSIS_TIMEOUT = 120


async def run_log_analysis(
    client: BundleAnalyzerClient,
    triage: TriageResult,
    index: BundleIndex,
) -> list[LogDiagnosis]:
    """Run AI log analysis on crash-looping containers.

    Creates a LogAnalyst and passes all crash contexts for concurrent
    AI-powered log forensics. The call is guarded by LOG_ANALYSIS_TIMEOUT
    to prevent hung LLM calls from blocking the pipeline.

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
        diagnoses = await asyncio.wait_for(
            analyst.analyze_crash_contexts(
                client, triage.crash_contexts, index
            ),
            timeout=LOG_ANALYSIS_TIMEOUT,
        )
        logger.info(
            "Log analysis complete: {} diagnosis(es) for {} crash context(s)",
            len(diagnoses),
            len(triage.crash_contexts),
        )
        return diagnoses
    except asyncio.TimeoutError:
        logger.error("Log analysis timed out after {}s", LOG_ANALYSIS_TIMEOUT)
        return []
    except (ImportError, AttributeError) as exc:
        logger.warning("Log analyst not available: {}", exc)
        return []
    except Exception as exc:
        logger.error("Log analysis failed: {}", exc)
        return []
