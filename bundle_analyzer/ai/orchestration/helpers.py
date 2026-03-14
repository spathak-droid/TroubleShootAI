"""Helper functions for the analysis orchestrator.

Stateless utility functions extracted from AnalysisOrchestrator
for finding resources, building reports, and converting values.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import (
    AnalystOutput,
    HistoricalEvent,
    TriageResult,
    UncertaintyGap,
)


def find_pod_json(namespace: str, pod_name: str, index: BundleIndex) -> dict | None:
    """Find a specific pod's JSON data from the bundle.

    Args:
        namespace: Pod namespace.
        pod_name: Pod name.
        index: Bundle index for reading resources.

    Returns:
        Pod JSON dict or None if not found.
    """
    for pod in index.get_all_pods():
        meta = pod.get("metadata", {})
        if meta.get("namespace") == namespace and meta.get("name") == pod_name:
            return pod
    return None


def find_node_json(node_name: str, index: BundleIndex) -> dict | None:
    """Find a specific node's JSON data from the bundle.

    Args:
        node_name: Node name to look up.
        index: Bundle index for reading resources.

    Returns:
        Node JSON dict or None if not found.
    """
    nodes_data = index.read_json("cluster-resources/nodes.json")
    if not nodes_data:
        return None
    items = nodes_data if isinstance(nodes_data, list) else (nodes_data.get("items") or [])
    for node in items:
        if node.get("metadata", {}).get("name") == node_name:
            return node
    return None


def empty_analyst_output(analyst_type: str, reason: str) -> AnalystOutput:
    """Create an empty analyst output with an uncertainty note.

    Args:
        analyst_type: Name of the analyst (e.g. "pod", "node").
        reason: Why the output is empty.

    Returns:
        An AnalystOutput with no findings.
    """
    return AnalystOutput(
        analyst=analyst_type,
        findings=[],
        root_cause=None,
        confidence=0.0,
        evidence=[],
        remediation=[],
        uncertainty=[reason],
    )


def confidence_to_float(confidence: str) -> float:
    """Convert a text confidence level to a float score.

    Args:
        confidence: "high", "medium", or "low".

    Returns:
        Float between 0.0 and 1.0.
    """
    mapping = {"high": 0.85, "medium": 0.55, "low": 0.25}
    return mapping.get(confidence.lower(), 0.25)


def build_uncertainty_report(
    analyst_outputs: list[AnalystOutput],
    synthesis: dict[str, Any],
    triage: TriageResult,
) -> list[UncertaintyGap]:
    """Build explicit uncertainty gaps from all analysis stages.

    Args:
        analyst_outputs: Individual analyst outputs with uncertainty lists.
        synthesis: Synthesis result with uncertainty_report.
        triage: Triage data for RBAC/silence signals.

    Returns:
        List of uncertainty gap objects.
    """
    gaps: list[UncertaintyGap] = []

    # From analyst uncertainty lists
    for output in analyst_outputs:
        for gap_text in output.uncertainty:
            gaps.append(UncertaintyGap(
                question=gap_text,
                reason=f"Reported by {output.analyst} analyst",
                impact="MEDIUM",
            ))

    # From synthesis uncertainty report
    uncertainty_report = synthesis.get("uncertainty_report", {})
    for item in uncertainty_report.get("what_i_cant_determine", []):
        gaps.append(UncertaintyGap(
            question=item,
            reason="Identified during synthesis cross-correlation",
            impact="HIGH",
        ))

    # From RBAC errors (data collection gaps)
    for rbac_error in triage.rbac_errors[:5]:
        gaps.append(UncertaintyGap(
            question="Data may be incomplete due to collection error",
            reason=rbac_error[:200],
            collect_command="kubectl auth can-i --list",
            impact="HIGH",
        ))

    # From silence signals (missing data)
    for signal in triage.silence_signals:
        gaps.append(UncertaintyGap(
            question=f"Missing data for {signal.namespace}/{signal.pod_name}",
            reason=f"{signal.signal_type}: {signal.note}" if signal.note else signal.signal_type,
            collect_command=f"kubectl logs {signal.pod_name} -n {signal.namespace} --previous",
            impact="MEDIUM" if signal.severity == "warning" else "HIGH",
        ))

    return gaps


def build_cluster_summary(triage: TriageResult, index: BundleIndex) -> str:
    """Build a short prose summary of the cluster state.

    Args:
        triage: Triage results with issue counts.
        index: Bundle index with metadata.

    Returns:
        Human-readable cluster summary paragraph.
    """
    parts: list[str] = []

    if index.metadata.kubernetes_version:
        parts.append(f"Kubernetes {index.metadata.kubernetes_version}")
    parts.append(f"{len(index.namespaces)} namespaces")

    issues: list[str] = []
    if triage.critical_pods:
        issues.append(f"{len(triage.critical_pods)} critical pod(s)")
    if triage.node_issues:
        issues.append(f"{len(triage.node_issues)} node issue(s)")
    if triage.deployment_issues:
        issues.append(f"{len(triage.deployment_issues)} deployment issue(s)")
    if triage.config_issues:
        issues.append(f"{len(triage.config_issues)} config issue(s)")

    # Troubleshoot.sh analysis summary
    ts = triage.troubleshoot_analysis
    if ts.has_results:
        issues.append(
            f"{ts.fail_count} troubleshoot.sh fail(s), "
            f"{ts.warn_count} warn(s), {ts.pass_count} pass(es)"
        )

    if issues:
        parts.append("with " + ", ".join(issues))
    else:
        parts.append("no critical issues detected")

    return "Cluster: " + ", ".join(parts) + "."


def timeline_from_triage(triage: TriageResult) -> list[HistoricalEvent]:
    """Build a minimal timeline from triage warning events.

    Args:
        triage: Triage results with warning events.

    Returns:
        Sorted list of historical events.
    """
    events: list[HistoricalEvent] = []
    for ev in triage.warning_events:
        ts = ev.last_timestamp or ev.first_timestamp
        if ts is None:
            continue
        events.append(HistoricalEvent(
            timestamp=ts,
            event_type=ev.reason,
            resource_type=ev.involved_object_kind,
            resource_name=ev.involved_object_name,
            namespace=ev.namespace,
            description=ev.message,
            is_trigger=False,
        ))
    events.sort(key=lambda e: e.timestamp)
    return events


async def report_progress(
    callback: Optional[Callable[..., Any]],
    stage: str,
    pct: float,
    message: str,
) -> None:
    """Report progress via the callback if provided.

    Args:
        callback: Progress callback function.
        stage: Current stage name.
        pct: Progress percentage (0.0-1.0).
        message: Human-readable progress message.
    """
    if callback is not None:
        try:
            result = callback(stage, pct, message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.debug("Progress callback failed: {}", exc)
