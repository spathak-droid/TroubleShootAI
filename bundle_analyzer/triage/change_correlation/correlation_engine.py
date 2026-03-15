"""Correlation engine -- matches detected changes with triage failures.

Provides functions to correlate changes with failures, assess correlation
strength, find best-matching failures, and generate human-readable explanations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from bundle_analyzer.triage.change_correlation.models import (
    ChangeCorrelation,
    ChangeEvent,
)
from bundle_analyzer.triage.change_correlation.utils import (
    STRENGTH_ORDER,
    format_delta,
)

if TYPE_CHECKING:
    from bundle_analyzer.models import TriageResult


def correlate_changes(
    changes: list[ChangeEvent],
    triage: TriageResult,
    failure_onset: datetime,
) -> list[ChangeCorrelation]:
    """Correlate detected changes with triage failures.

    For each change, calculates the time delta to the failure onset,
    assigns a correlation strength, and generates an explanation.

    Args:
        changes: All detected changes in the lookback window.
        triage: Completed triage result with failure details.
        failure_onset: The earliest failure timestamp.

    Returns:
        Sorted list of correlations (strongest first, then by time delta).
    """
    if not changes:
        return []

    # Build failure descriptions from triage
    failures = build_failure_descriptions(triage)
    if not failures:
        return []

    correlations: list[ChangeCorrelation] = []

    for change in changes:
        change_ts = change.timestamp
        if change_ts.tzinfo is None:
            change_ts = change_ts.replace(tzinfo=UTC)

        onset = failure_onset
        if onset.tzinfo is None:
            onset = onset.replace(tzinfo=UTC)

        delta = (onset - change_ts).total_seconds()
        if delta < 0:
            # Change happened after the failure -- skip
            continue

        # Determine strength based on time delta and namespace overlap
        strength = assess_strength(delta, change, failures)

        # Find the best-matching failure
        best_failure = best_matching_failure(change, failures)

        # Generate explanation
        explanation = generate_explanation(change, best_failure, delta)

        # Determine severity
        severity: Literal["critical", "warning", "info"] = "warning"
        if strength == "strong":
            severity = "critical"
        elif strength == "weak":
            severity = "info"

        correlations.append(
            ChangeCorrelation(
                change=change,
                failure_description=best_failure,
                time_delta_seconds=delta,
                correlation_strength=strength,
                explanation=explanation,
                severity=severity,
            )
        )

    # Sort: strongest first, then smallest time delta
    correlations.sort(
        key=lambda c: (
            STRENGTH_ORDER.get(c.correlation_strength, 99),
            c.time_delta_seconds,
        )
    )

    return correlations


def build_failure_descriptions(
    triage: TriageResult,
) -> list[tuple[str, str, str]]:
    """Build (namespace, resource, description) tuples from triage.

    Args:
        triage: Completed triage result.

    Returns:
        List of tuples: (namespace, resource_name, failure_description).
    """
    failures: list[tuple[str, str, str]] = []

    for pod in triage.critical_pods:
        failures.append((
            pod.namespace,
            pod.pod_name,
            f"Pod '{pod.pod_name}' in namespace '{pod.namespace}' "
            f"is {pod.issue_type}"
            + (f" (restarts: {pod.restart_count})" if pod.restart_count else ""),
        ))

    for dep in triage.deployment_issues:
        failures.append((
            dep.namespace,
            dep.name,
            f"Deployment '{dep.name}' has {dep.issue}"
            + (" (stuck rollout)" if dep.stuck_rollout else ""),
        ))

    for node in triage.node_issues:
        failures.append((
            "",
            node.node_name,
            f"Node '{node.node_name}' has condition {node.condition}",
        ))

    for event in triage.warning_events[:20]:  # cap to avoid excessive output
        failures.append((
            event.namespace,
            event.involved_object_name,
            f"Warning event on {event.involved_object_kind}/"
            f"{event.involved_object_name}: {event.reason}",
        ))

    return failures


def assess_strength(
    delta_seconds: float,
    change: ChangeEvent,
    failures: list[tuple[str, str, str]],
) -> Literal["strong", "moderate", "weak"]:
    """Assess correlation strength based on time delta and namespace.

    - ``strong``: delta < 5 minutes AND same namespace as a failure
    - ``moderate``: delta < 30 minutes
    - ``weak``: delta < 60 minutes

    Args:
        delta_seconds: Seconds between the change and failure onset.
        change: The change event.
        failures: List of (namespace, resource, description) tuples.

    Returns:
        Correlation strength classification.
    """
    same_namespace = any(
        ns == change.namespace for ns, _, _ in failures if ns
    )

    if delta_seconds < 300 and same_namespace:
        return "strong"
    if delta_seconds < 1800:
        return "moderate"
    return "weak"


def best_matching_failure(
    change: ChangeEvent,
    failures: list[tuple[str, str, str]],
) -> str:
    """Find the failure description most likely related to this change.

    Prefers failures in the same namespace. Falls back to the first
    failure if none share a namespace.

    Args:
        change: The change event.
        failures: List of (namespace, resource, description) tuples.

    Returns:
        The best-matching failure description string.
    """
    # Prefer same-namespace failures
    for ns, _resource, desc in failures:
        if ns and ns == change.namespace:
            return desc

    # Fall back to first failure
    return failures[0][2] if failures else "Unknown failure"


def generate_explanation(
    change: ChangeEvent, failure: str, delta_seconds: float
) -> str:
    """Generate a human-readable explanation of the correlation.

    Args:
        change: The change event.
        failure: Description of the correlated failure.
        delta_seconds: Seconds between the change and failure.

    Returns:
        A plain-English explanation string.
    """
    delta_str = format_delta(delta_seconds)

    type_explanations = {
        "Deployment": (
            f"Deployment '{change.resource_name}' was "
            f"{change.change_type} {delta_str} before failure. "
            f"This may have introduced a breaking change."
        ),
        "ConfigMap": (
            f"ConfigMap '{change.resource_name}' was modified "
            f"{delta_str} before pods in"
            + (f" namespace '{change.namespace}'" if change.namespace else " the cluster")
            + " started failing. Configuration changes are a common root cause."
        ),
        "Secret": (
            f"Secret '{change.resource_name}' was changed "
            f"{delta_str} before failure. "
            f"Credential or certificate changes can break authentication."
        ),
        "Node": (
            f"Node '{change.resource_name}' "
            f"{'was added to the cluster' if change.change_type == 'created' else 'had a condition change'} "
            f"{delta_str} before failure. "
            f"Infrastructure changes can affect workload scheduling."
        ),
        "ReplicaSet": (
            f"ReplicaSet '{change.resource_name}' was "
            f"{change.change_type} {delta_str} before failure, "
            f"indicating a deployment change."
        ),
    }

    explanation = type_explanations.get(
        change.resource_type,
        (
            f"{change.resource_type} '{change.resource_name}' was "
            f"{change.change_type} {delta_str} before failure."
        ),
    )

    return explanation
