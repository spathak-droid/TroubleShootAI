"""ChangeCorrelator facade -- the main entry point for change correlation.

Provides the ``ChangeCorrelator`` class which orchestrates failure onset
detection, change finding, and correlation analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.triage.change_correlation.change_finders import (
    find_node_changes,
    find_recent_config_changes,
    find_recent_deployments,
    find_rollout_events,
    find_scaling_events,
)
from bundle_analyzer.triage.change_correlation.correlation_engine import (
    correlate_changes,
)
from bundle_analyzer.triage.change_correlation.failure_detection import (
    find_failure_onset,
)
from bundle_analyzer.triage.change_correlation.models import (
    ChangeEvent,
    ChangeReport,
)

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex
    from bundle_analyzer.models import TriageResult


class ChangeCorrelator:
    """Scans a bundle for recent changes and correlates them with failures.

    Identifies what changed shortly before failures began -- deployments,
    config changes, scaling events, node additions -- and ranks those
    changes by how likely they are to have caused the observed problems.
    """

    def __init__(self, lookback_minutes: int = 60) -> None:
        self._lookback_minutes = lookback_minutes

    async def scan(
        self, index: BundleIndex, triage: TriageResult
    ) -> ChangeReport:
        """Run the full change-correlation analysis.

        Args:
            index: Bundle index for reading resource data.
            triage: Completed triage result containing detected failures.

        Returns:
            A ``ChangeReport`` with recent changes and their correlations.
        """
        failure_onset = find_failure_onset(triage, index)
        if failure_onset is None:
            logger.info("ChangeCorrelator: no failure onset found, skipping")
            return ChangeReport(timeline_window_minutes=self._lookback_minutes)

        logger.info(
            "ChangeCorrelator: failure onset at {}, lookback {} min",
            failure_onset.isoformat(),
            self._lookback_minutes,
        )

        # Gather changes from multiple resource types
        changes: list[ChangeEvent] = []
        changes.extend(find_recent_deployments(index, failure_onset, self._lookback_minutes))
        changes.extend(find_recent_config_changes(index, failure_onset, self._lookback_minutes))
        changes.extend(find_scaling_events(index, failure_onset, self._lookback_minutes))
        changes.extend(find_node_changes(index, failure_onset, self._lookback_minutes))
        changes.extend(find_rollout_events(index, failure_onset, self._lookback_minutes))

        # Sort changes by timestamp descending (most recent first)
        changes.sort(key=lambda c: c.timestamp, reverse=True)

        # Correlate with failures
        correlations = correlate_changes(changes, triage, failure_onset)

        logger.info(
            "ChangeCorrelator: found {} changes, {} correlations",
            len(changes),
            len(correlations),
        )

        return ChangeReport(
            recent_changes=changes,
            correlations=correlations,
            timeline_window_minutes=self._lookback_minutes,
        )
