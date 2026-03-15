"""Temporal archaeology — reconstructs cluster history from metadata timestamps.

Mines creationTimestamp, lastTransitionTime, and other temporal metadata
to build a timeline of events that led to the current state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import HistoricalEvent

# ── Local models ─────────────────────────────────────────────────────

Severity = Literal["critical", "warning", "info"]


class TimelineEvent(BaseModel):
    """A single event extracted from the cluster timeline."""

    timestamp: datetime
    event_type: str  # "pod_created", "pod_crashed", "node_pressure", etc.
    resource: str
    namespace: str | None = None
    description: str
    severity: Severity = "info"


class Timeline(BaseModel):
    """Full reconstructed timeline from temporal archaeology."""

    events: list[HistoricalEvent] = Field(default_factory=list)
    cluster_age_days: int | None = None
    incident_window_start: datetime | None = None
    incident_window_end: datetime | None = None
    quiet_periods: list[tuple[datetime, datetime]] = Field(default_factory=list)


# ── Engine ───────────────────────────────────────────────────────────


class TemporalArchaeologyEngine:
    """Reconstructs cluster history from metadata timestamps.

    Collects timestamps from pods, events, and node conditions, builds a
    unified timeline, and identifies incident windows and quiet periods.
    """

    # Minimum gap (in minutes) between events to consider a "quiet period".
    QUIET_PERIOD_MINUTES: int = 30

    # Minimum number of Warning events in a window to consider it an incident.
    INCIDENT_CLUSTER_THRESHOLD: int = 3

    # Sliding window size (in minutes) for detecting incident clusters.
    INCIDENT_WINDOW_MINUTES: int = 15

    async def reconstruct(self, index: BundleIndex) -> list[HistoricalEvent]:
        """Build a timeline of historical events from the bundle.

        Collects timestamps from pods, events, and node conditions, sorts
        them chronologically, identifies incident windows and quiet periods.

        Args:
            index: The indexed support bundle to analyse.

        Returns:
            Sorted list of HistoricalEvent objects.
        """
        raw_events: list[HistoricalEvent] = []

        raw_events.extend(self._collect_pod_timestamps(index))
        raw_events.extend(self._collect_event_timestamps(index))
        raw_events.extend(self._collect_node_timestamps(index))

        # Sort chronologically
        raw_events.sort(key=lambda e: e.timestamp)

        logger.info(
            "Temporal archaeology: collected {} timeline events", len(raw_events)
        )
        return raw_events

    async def build_timeline(self, index: BundleIndex) -> Timeline:
        """Build a full Timeline model including incident windows and quiet periods.

        Args:
            index: The indexed support bundle.

        Returns:
            A Timeline with events, cluster age, incident window, and quiet periods.
        """
        events = await self.reconstruct(index)
        cluster_age = self._estimate_cluster_age(index)
        incident_start, incident_end = self._find_incident_window(events, index)
        quiet_periods = self._find_quiet_periods(events)

        # Mark events inside the incident window as triggers
        if incident_start and incident_end:
            for ev in events:
                if incident_start <= ev.timestamp <= incident_end:
                    ev.is_trigger = True

        return Timeline(
            events=events,
            cluster_age_days=cluster_age,
            incident_window_start=incident_start,
            incident_window_end=incident_end,
            quiet_periods=quiet_periods,
        )

    # ── Timestamp collectors ─────────────────────────────────────────

    def _collect_pod_timestamps(self, index: BundleIndex) -> list[HistoricalEvent]:
        """Extract timestamps from pod metadata and container statuses."""
        events: list[HistoricalEvent] = []

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")

            # Pod creation
            creation_ts = self._parse_ts(metadata.get("creationTimestamp"))
            if creation_ts:
                events.append(
                    HistoricalEvent(
                        timestamp=creation_ts,
                        event_type="pod_created",
                        resource_type="Pod",
                        resource_name=pod_name,
                        namespace=namespace,
                        description=f"Pod {pod_name} created in {namespace}",
                    )
                )

            status = pod.get("status", {})

            # Pod startTime
            start_ts = self._parse_ts(status.get("startTime"))
            if start_ts:
                events.append(
                    HistoricalEvent(
                        timestamp=start_ts,
                        event_type="pod_started",
                        resource_type="Pod",
                        resource_name=pod_name,
                        namespace=namespace,
                        description=f"Pod {pod_name} started",
                    )
                )

            # Container statuses
            for cs_list_key in ("containerStatuses", "initContainerStatuses"):
                for cs in status.get(cs_list_key, []) or []:
                    container_name = cs.get("name", "unknown")
                    state = cs.get("state", {})
                    last_state = cs.get("lastState", {})

                    for state_dict, prefix in [(state, "current"), (last_state, "previous")]:
                        running = state_dict.get("running", {})
                        if running:
                            started = self._parse_ts(running.get("startedAt"))
                            if started:
                                events.append(
                                    HistoricalEvent(
                                        timestamp=started,
                                        event_type=f"container_{prefix}_started",
                                        resource_type="Container",
                                        resource_name=f"{pod_name}/{container_name}",
                                        namespace=namespace,
                                        description=(
                                            f"Container {container_name} ({prefix}) started "
                                            f"in pod {pod_name}"
                                        ),
                                    )
                                )

                        terminated = state_dict.get("terminated", {})
                        if terminated:
                            started_at = self._parse_ts(terminated.get("startedAt"))
                            finished_at = self._parse_ts(terminated.get("finishedAt"))
                            exit_code = terminated.get("exitCode")
                            reason = terminated.get("reason", "")

                            if started_at:
                                events.append(
                                    HistoricalEvent(
                                        timestamp=started_at,
                                        event_type=f"container_{prefix}_started",
                                        resource_type="Container",
                                        resource_name=f"{pod_name}/{container_name}",
                                        namespace=namespace,
                                        description=(
                                            f"Container {container_name} ({prefix}) started "
                                            f"in pod {pod_name}"
                                        ),
                                    )
                                )
                            if finished_at:
                                events.append(
                                    HistoricalEvent(
                                        timestamp=finished_at,
                                        event_type=f"container_{prefix}_terminated",
                                        resource_type="Container",
                                        resource_name=f"{pod_name}/{container_name}",
                                        namespace=namespace,
                                        description=(
                                            f"Container {container_name} ({prefix}) terminated "
                                            f"(exit={exit_code}, reason={reason}) "
                                            f"in pod {pod_name}"
                                        ),
                                    )
                                )

        return events

    def _collect_event_timestamps(self, index: BundleIndex) -> list[HistoricalEvent]:
        """Extract timestamps from Kubernetes events."""
        events: list[HistoricalEvent] = []
        raw_events = index.get_events()

        for ev in raw_events:
            metadata = ev.get("metadata", {})
            namespace = metadata.get("namespace", ev.get("namespace", ""))
            reason = ev.get("reason", "unknown")
            message = ev.get("message", "")
            event_type = ev.get("type", "Normal")
            involved = ev.get("involvedObject", {})
            obj_kind = involved.get("kind", "Unknown")
            obj_name = involved.get("name", "unknown")

            first_ts = self._parse_ts(ev.get("firstTimestamp"))
            last_ts = self._parse_ts(ev.get("lastTimestamp"))

            # Use firstTimestamp as the event start point
            if first_ts:
                events.append(
                    HistoricalEvent(
                        timestamp=first_ts,
                        event_type=f"event_{reason.lower()}",
                        resource_type=obj_kind,
                        resource_name=obj_name,
                        namespace=namespace,
                        description=f"[{event_type}] {reason}: {message[:200]}",
                    )
                )

            # If lastTimestamp differs, also record it (shows event recurrence)
            if last_ts and first_ts and last_ts != first_ts:
                count = ev.get("count", 1)
                events.append(
                    HistoricalEvent(
                        timestamp=last_ts,
                        event_type=f"event_{reason.lower()}_last",
                        resource_type=obj_kind,
                        resource_name=obj_name,
                        namespace=namespace,
                        description=(
                            f"[{event_type}] {reason} (last occurrence, "
                            f"count={count}): {message[:200]}"
                        ),
                    )
                )

        return events

    def _collect_node_timestamps(self, index: BundleIndex) -> list[HistoricalEvent]:
        """Extract timestamps from node conditions."""
        events: list[HistoricalEvent] = []

        nodes_dir = index.root / "cluster-resources" / "nodes"
        if not nodes_dir.is_dir():
            # Try nodes.json
            nodes_data = index.read_json("cluster-resources/nodes.json")
            if nodes_data:
                items = (
                    nodes_data
                    if isinstance(nodes_data, list)
                    else nodes_data.get("items", [])
                )
                for node in items:
                    events.extend(self._extract_node_events(node, index))
            return events

        for node_file in sorted(nodes_dir.glob("*.json")):
            rel = str(node_file.relative_to(index.root))
            node_data = index.read_json(rel)
            if node_data is None:
                continue
            if isinstance(node_data, dict):
                if "items" in node_data:
                    for node in node_data["items"]:
                        events.extend(self._extract_node_events(node, index))
                else:
                    events.extend(self._extract_node_events(node_data, index))
            elif isinstance(node_data, list):
                for node in node_data:
                    events.extend(self._extract_node_events(node, index))

        return events

    def _extract_node_events(
        self, node: dict, index: BundleIndex
    ) -> list[HistoricalEvent]:
        """Extract timeline events from a single node JSON."""
        events: list[HistoricalEvent] = []
        metadata = node.get("metadata", {})
        node_name = metadata.get("name", "unknown")

        # Node creation
        creation_ts = self._parse_ts(metadata.get("creationTimestamp"))
        if creation_ts:
            events.append(
                HistoricalEvent(
                    timestamp=creation_ts,
                    event_type="node_created",
                    resource_type="Node",
                    resource_name=node_name,
                    description=f"Node {node_name} created",
                )
            )

        # Node conditions
        for condition in node.get("status", {}).get("conditions", []):
            transition_ts = self._parse_ts(
                condition.get("lastTransitionTime")
            )
            if not transition_ts:
                continue

            cond_type = condition.get("type", "Unknown")
            cond_status = condition.get("status", "Unknown")
            message = condition.get("message", "")

            events.append(
                HistoricalEvent(
                    timestamp=transition_ts,
                    event_type=f"node_condition_{cond_type.lower()}",
                    resource_type="Node",
                    resource_name=node_name,
                    description=(
                        f"Node {node_name} condition {cond_type}={cond_status}: "
                        f"{message[:200]}"
                    ),
                )
            )

        return events

    # ── Analysis helpers ─────────────────────────────────────────────

    def _estimate_cluster_age(self, index: BundleIndex) -> int | None:
        """Estimate cluster age in days from the oldest node creationTimestamp."""
        oldest: datetime | None = None

        nodes_dir = index.root / "cluster-resources" / "nodes"
        node_sources: list[dict] = []

        if nodes_dir.is_dir():
            for node_file in nodes_dir.glob("*.json"):
                rel = str(node_file.relative_to(index.root))
                data = index.read_json(rel)
                if isinstance(data, dict):
                    if "items" in data:
                        node_sources.extend(data["items"])
                    else:
                        node_sources.append(data)
                elif isinstance(data, list):
                    node_sources.extend(data)
        else:
            data = index.read_json("cluster-resources/nodes.json")
            if isinstance(data, dict):
                node_sources = data.get("items", [])
            elif isinstance(data, list):
                node_sources = data

        for node in node_sources:
            ts = self._parse_ts(node.get("metadata", {}).get("creationTimestamp"))
            if ts and (oldest is None or ts < oldest):
                oldest = ts

        if oldest is None:
            return None

        now = datetime.now(UTC)
        return (now - oldest).days

    def _find_incident_window(
        self,
        events: list[HistoricalEvent],
        index: BundleIndex,
    ) -> tuple[datetime | None, datetime | None]:
        """Find the time window where Warning events cluster most densely.

        Uses a sliding window approach to find the densest cluster of
        warning-related events.
        """
        # Collect warning event timestamps
        warning_timestamps: list[datetime] = []
        for ev in events:
            if "warning" in ev.description.lower() or ev.event_type.startswith(
                "event_"
            ):
                # Check if it's a warning-type event
                if "[Warning]" in ev.description:
                    warning_timestamps.append(ev.timestamp)

        if len(warning_timestamps) < self.INCIDENT_CLUSTER_THRESHOLD:
            return None, None

        warning_timestamps.sort()
        window = timedelta(minutes=self.INCIDENT_WINDOW_MINUTES)

        best_count = 0
        best_start: datetime | None = None
        best_end: datetime | None = None

        for i, start_ts in enumerate(warning_timestamps):
            end_ts = start_ts + window
            count = sum(
                1
                for ts in warning_timestamps[i:]
                if ts <= end_ts
            )
            if count > best_count:
                best_count = count
                best_start = start_ts
                # End at the last event within the window
                best_end = max(
                    ts for ts in warning_timestamps[i:] if ts <= end_ts
                )

        if best_count >= self.INCIDENT_CLUSTER_THRESHOLD and best_start and best_end:
            return best_start, best_end

        return None, None

    def _find_quiet_periods(
        self, events: list[HistoricalEvent]
    ) -> list[tuple[datetime, datetime]]:
        """Identify gaps in the timeline where no events occurred.

        A quiet period is any gap longer than QUIET_PERIOD_MINUTES between
        consecutive events.
        """
        if len(events) < 2:
            return []

        threshold = timedelta(minutes=self.QUIET_PERIOD_MINUTES)
        quiet: list[tuple[datetime, datetime]] = []

        for i in range(1, len(events)):
            gap = events[i].timestamp - events[i - 1].timestamp
            if gap >= threshold:
                quiet.append((events[i - 1].timestamp, events[i].timestamp))

        return quiet

    # ── Parsing helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_ts(value: str | None) -> datetime | None:
        """Parse a Kubernetes ISO 8601 timestamp string.

        Handles common K8s formats including those with and without timezone info.

        Args:
            value: Raw timestamp string from K8s JSON, or None.

        Returns:
            Parsed datetime (UTC) or None if parsing fails.
        """
        if not value or not isinstance(value, str):
            return None

        try:
            # Handle "Z" suffix
            cleaned = value.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            logger.debug("Could not parse timestamp: {}", value)
            return None
