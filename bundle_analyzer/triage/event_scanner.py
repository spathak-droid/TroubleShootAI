"""Event scanner — extracts Warning events sorted by timestamp.

Parses Kubernetes events from the bundle, filters for warnings,
and sorts them chronologically to build an event timeline.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import EventEscalation, K8sEvent

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class EventScanner:
    """Scans bundle events and returns all Warning events sorted by time.

    Reads events from all namespaces, filters to type==Warning,
    and returns them sorted by lastTimestamp (most recent first).
    """

    async def scan(self, index: "BundleIndex") -> list[K8sEvent]:
        """Scan all events and return Warning events sorted by time.

        Args:
            index: The bundle index providing access to event data.

        Returns:
            A list of K8sEvent objects for Warning events, most recent first.
        """
        events: list[K8sEvent] = []

        try:
            raw_events = index.get_events()
        except Exception as exc:
            logger.warning("Failed to read events from bundle: {}", exc)
            return events

        for raw in raw_events:
            try:
                event = self._parse_event(raw)
                if event is not None and event.type == "Warning":
                    events.append(event)
            except Exception as exc:
                logger.debug("Failed to parse event: {}", exc)

        # Sort by last_timestamp descending (most recent first), None sorts last
        events.sort(
            key=lambda e: e.last_timestamp or datetime.min.replace(tzinfo=None),
            reverse=True,
        )

        logger.info("EventScanner found {} warning events", len(events))
        return events

    def detect_escalations(self, events: list[K8sEvent]) -> list[EventEscalation]:
        """Detect escalation patterns in a list of events.

        Groups events by (namespace, involvedObject.kind, involvedObject.name)
        and checks for three escalation types:
        - repeated: total count > 10 across events for the same object
        - cascading: multiple different reasons appear for the same object
        - sustained: time span between first and last event > 1 hour

        Args:
            events: List of K8sEvent objects to analyze for patterns.

        Returns:
            A list of EventEscalation objects describing detected patterns.
        """
        # Group events by (namespace, kind, name)
        groups: dict[tuple[str, str, str], list[K8sEvent]] = defaultdict(list)
        for event in events:
            key = (event.namespace, event.involved_object_kind, event.involved_object_name)
            groups[key].append(event)

        escalations: list[EventEscalation] = []

        for (namespace, kind, name), group_events in groups.items():
            total_count = sum(e.count for e in group_events)
            reasons = list(dict.fromkeys(e.reason for e in group_events))  # ordered unique

            # Compute time boundaries
            first_seen = min(
                (e.first_timestamp for e in group_events if e.first_timestamp is not None),
                default=None,
            )
            last_seen = max(
                (e.last_timestamp for e in group_events if e.last_timestamp is not None),
                default=None,
            )

            detected_types: list[str] = []

            if total_count > 10:
                detected_types.append("repeated")

            if len(reasons) > 1:
                detected_types.append("cascading")

            if (
                first_seen is not None
                and last_seen is not None
                and (last_seen - first_seen) > timedelta(hours=1)
            ):
                detected_types.append("sustained")

            if not detected_types:
                continue

            # Pick the most severe escalation type for the primary classification
            # Priority: cascading > sustained > repeated
            if "cascading" in detected_types:
                escalation_type = "cascading"
            elif "sustained" in detected_types:
                escalation_type = "sustained"
            else:
                escalation_type = "repeated"

            # Determine severity based on escalation characteristics
            severity: str = "warning"
            if total_count > 50 or ("cascading" in detected_types and "sustained" in detected_types):
                severity = "critical"

            # Build a descriptive message
            reason_summary = ", ".join(reasons[:5])
            message = (
                f"{kind}/{name} has {total_count} events with reasons: [{reason_summary}] "
                f"({', '.join(detected_types)})"
            )

            escalations.append(
                EventEscalation(
                    namespace=namespace,
                    involved_object_kind=kind,
                    involved_object_name=name,
                    event_reasons=reasons,
                    total_count=total_count,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    escalation_type=escalation_type,  # type: ignore[arg-type]
                    message=message,
                    severity=severity,  # type: ignore[arg-type]
                    source_file=f"events/{namespace}.json",
                    evidence_excerpt=(
                        f"{kind}/{name}: {total_count} events, "
                        f"reasons=[{reason_summary}], "
                        f"types=[{', '.join(detected_types)}]"
                    ),
                )
            )

        logger.info("EventScanner detected {} escalation patterns", len(escalations))
        return escalations

    def _parse_event(self, raw: dict) -> K8sEvent | None:
        """Parse a raw event dict into a K8sEvent model."""
        metadata = raw.get("metadata", {})
        involved = raw.get("involvedObject", {})
        event_type = raw.get("type", "Normal")

        # Must have minimal data to be useful
        reason = raw.get("reason", "")
        if not reason:
            return None

        namespace = metadata.get("namespace", involved.get("namespace", "default"))
        name = metadata.get("name", "")

        first_ts = _parse_timestamp(raw.get("firstTimestamp"))
        last_ts = _parse_timestamp(raw.get("lastTimestamp"))
        # Fall back to metadata.creationTimestamp
        if first_ts is None:
            first_ts = _parse_timestamp(metadata.get("creationTimestamp"))
        if last_ts is None:
            last_ts = first_ts

        return K8sEvent(
            namespace=namespace,
            name=name,
            reason=reason,
            message=raw.get("message", ""),
            type=event_type if event_type in ("Normal", "Warning") else "Warning",
            involved_object_kind=involved.get("kind", "Unknown"),
            involved_object_name=involved.get("name", "unknown"),
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            count=raw.get("count", 1),
        )


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse a Kubernetes timestamp string to datetime, returning None on failure."""
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
