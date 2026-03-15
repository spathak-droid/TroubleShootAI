"""Failure onset detection for change correlation.

Determines when failures first started by examining triage results
and pod container statuses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from bundle_analyzer.triage.change_correlation.utils import parse_k8s_timestamp

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex
    from bundle_analyzer.models import TriageResult


def find_failure_onset(
    triage: TriageResult, index: BundleIndex
) -> datetime | None:
    """Determine the earliest failure timestamp from triage findings.

    Examines crash-looping pods' container statuses and warning events
    to find when things first started going wrong.

    Args:
        triage: Completed triage result.
        index: Bundle index for reading pod data.

    Returns:
        The earliest failure timestamp found, or ``None``.
    """
    candidates: list[datetime] = []

    # From crash-looping pods -- look at container status timestamps
    for pod_issue in triage.critical_pods:
        if pod_issue.issue_type in ("CrashLoopBackOff", "OOMKilled"):
            ts = get_pod_failure_time(index, pod_issue.namespace, pod_issue.pod_name)
            if ts is not None:
                candidates.append(ts)

    # From warning events -- use firstTimestamp
    for event in triage.warning_events:
        if event.first_timestamp is not None:
            candidates.append(event.first_timestamp)

    # From event escalations
    for esc in triage.event_escalations:
        if esc.first_seen is not None:
            candidates.append(esc.first_seen)

    if not candidates:
        return None

    # Ensure all candidates are timezone-aware for comparison
    aware: list[datetime] = []
    for c in candidates:
        if c.tzinfo is None:
            c = c.replace(tzinfo=UTC)
        aware.append(c)

    return min(aware)


def get_pod_failure_time(
    index: BundleIndex, namespace: str, pod_name: str
) -> datetime | None:
    """Extract the failure timestamp from a pod's container statuses.

    Looks for ``lastState.terminated.startedAt`` in the pod's
    container statuses as an indicator of when the crash started.

    Args:
        index: Bundle index.
        namespace: Pod namespace.
        pod_name: Pod name.

    Returns:
        The earliest termination timestamp found, or ``None``.
    """
    for path_pattern in (
        f"cluster-resources/pods/{namespace}/{pod_name}.json",
        f"cluster-resources/pods/{namespace}.json",
    ):
        data = index.read_json(path_pattern)
        if data is None:
            continue

        pods = []
        if isinstance(data, dict):
            if "items" in data:
                pods = data["items"]
            elif data.get("metadata", {}).get("name") == pod_name:
                pods = [data]
        elif isinstance(data, list):
            pods = data

        for pod in pods:
            if pod.get("metadata", {}).get("name") != pod_name:
                continue
            status = pod.get("status", {})
            for cs in status.get("containerStatuses", []):
                last_state = cs.get("lastState", {})
                terminated = last_state.get("terminated", {})
                ts = parse_k8s_timestamp(terminated.get("startedAt"))
                if ts is not None:
                    return ts
                # Fallback to current state terminated
                cur_state = cs.get("state", {})
                cur_terminated = cur_state.get("terminated", {})
                ts = parse_k8s_timestamp(cur_terminated.get("startedAt"))
                if ts is not None:
                    return ts

    return None
