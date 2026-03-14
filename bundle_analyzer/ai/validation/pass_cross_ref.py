"""Pass 4: Signal cross-referencing.

Finds triage signals that corroborate or relate to each finding,
building a picture of correlated evidence from multiple scanners.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models import AnalysisResult, CorrelatedSignal, Finding

from .helpers import normalize_resource_key


def cross_reference_signals(
    verdicts: list[dict[str, Any]],
    analysis: AnalysisResult,
) -> None:
    """Find triage signals that corroborate or relate to each finding.

    Args:
        verdicts: Per-finding accumulator dicts (mutated in place).
        analysis: The full analysis result.
    """
    triage = analysis.triage

    for v in verdicts:
        finding: Finding = v["finding"]
        if not finding.resource:
            continue

        kind, ns, name = normalize_resource_key(finding.resource)

        # Pod-level signals
        if kind == "pod":
            _match_pod_signals(v, triage, ns, name)

        # Events for this resource
        for evt in triage.warning_events:
            if evt.involved_object_name == name and (
                not ns or evt.namespace == ns
            ):
                v["signals"].append(CorrelatedSignal(
                    scanner_type="event",
                    signal=f"{evt.reason}: {evt.message[:80]}",
                    relates_to=f"count={evt.count}",
                    severity="warning",
                ))

        # Node issues (if we can determine which node)
        for node in triage.node_issues:
            if kind == "node" and node.node_name == name:
                v["signals"].append(CorrelatedSignal(
                    scanner_type="node",
                    signal=f"{node.condition}",
                    relates_to=node.message[:100],
                    severity="critical" if node.condition in ("NotReady", "MemoryPressure") else "warning",
                ))


def _match_pod_signals(
    v: dict[str, Any],
    triage: object,
    ns: str,
    name: str,
) -> None:
    """Match pod-level triage signals to a finding.

    Args:
        v: Verdict accumulator dict (mutated in place).
        triage: The triage result object.
        ns: Pod namespace.
        name: Pod name.
    """
    # Probe issues
    for pi in triage.probe_issues:  # type: ignore[attr-defined]
        if pi.namespace == ns and pi.pod_name == name:
            v["signals"].append(CorrelatedSignal(
                scanner_type="probe",
                signal=f"{pi.probe_type} probe: {pi.issue}",
                relates_to=pi.message[:100],
                severity=pi.severity,
            ))

    # Resource issues
    for ri in triage.resource_issues:  # type: ignore[attr-defined]
        if ri.namespace == ns and ri.pod_name == name:
            v["signals"].append(CorrelatedSignal(
                scanner_type="resource",
                signal=f"{ri.resource_type}: {ri.issue}",
                relates_to=ri.message[:100],
                severity=ri.severity,
            ))

    # Silence signals
    for ss in triage.silence_signals:  # type: ignore[attr-defined]
        if ss.namespace == ns and ss.pod_name == name:
            v["signals"].append(CorrelatedSignal(
                scanner_type="silence",
                signal=f"{ss.signal_type}",
                relates_to=ss.note[:100] if ss.note else "",
                severity=ss.severity,
            ))

    # Config issues referencing this pod
    for ci in triage.config_issues:  # type: ignore[attr-defined]
        if ci.namespace == ns and name in (ci.referenced_by or ""):
            v["signals"].append(CorrelatedSignal(
                scanner_type="config",
                signal=f"{ci.issue}: {ci.resource_name}",
                relates_to=f"Referenced by {ci.referenced_by}",
                severity="warning",
            ))
