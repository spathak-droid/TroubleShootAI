"""Archaeology step — temporal timeline reconstruction."""

from __future__ import annotations

from loguru import logger

from bundle_analyzer.ai.orchestration.helpers import timeline_from_triage
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import HistoricalEvent, TriageResult


async def run_archaeology(
    triage: TriageResult,
    index: BundleIndex,
) -> list[HistoricalEvent]:
    """Run the temporal archaeology engine to build a timeline.

    Args:
        triage: Triage results containing events with timestamps.
        index: Bundle index for reading resource files.

    Returns:
        List of historical events sorted by timestamp.
    """
    events: list[HistoricalEvent] = []
    try:
        from bundle_analyzer.ai.engines.archaeology import TemporalArchaeologyEngine

        engine = TemporalArchaeologyEngine()
        timeline = await engine.build_timeline(index)
        events = timeline.events
    except (ImportError, AttributeError, TypeError) as exc:
        logger.debug("Archaeology engine not available: {}", exc)
        events = timeline_from_triage(triage)
    except Exception as exc:
        logger.warning("Archaeology engine failed: {}", exc)
        events = timeline_from_triage(triage)
    return events
