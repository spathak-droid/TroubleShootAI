"""Scoring and cross-cutting concern detection.

Computes overall correctness, average confidence, and detects
patterns that span multiple findings.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models import (
    AnalysisResult,
    EvaluationVerdict,
    MissedFailurePoint,
)


def compute_overall(
    verdicts: list[EvaluationVerdict],
    missed: list[MissedFailurePoint],
) -> str:
    """Compute overall correctness from individual verdicts.

    Args:
        verdicts: The assembled verdicts.
        missed: Missed failure points.

    Returns:
        Overall correctness string.
    """
    if not verdicts:
        return "Inconclusive"

    counts = {"Correct": 0, "Partially Correct": 0, "Incorrect": 0, "Inconclusive": 0}
    for v in verdicts:
        counts[v.correctness] = counts.get(v.correctness, 0) + 1

    total = len(verdicts)
    critical_missed = sum(1 for m in missed if m.severity == "critical")

    if counts["Incorrect"] > total * 0.5:
        return "Incorrect"
    if critical_missed > 0:
        return "Partially Correct"
    if counts["Correct"] == total:
        return "Correct"
    if counts["Correct"] + counts["Partially Correct"] == total:
        return "Partially Correct"
    return "Partially Correct"


def avg_confidence(verdicts: list[EvaluationVerdict]) -> float:
    """Weighted average of verdict confidence scores.

    Args:
        verdicts: The assembled verdicts.

    Returns:
        Average confidence (0.0-1.0).
    """
    if not verdicts:
        return 0.0
    return sum(v.confidence_score for v in verdicts) / len(verdicts)


def detect_cross_cutting(
    verdicts: list[dict[str, Any]],
    analysis: AnalysisResult,
) -> list[str]:
    """Detect patterns that span multiple findings.

    Args:
        verdicts: Per-finding accumulator dicts.
        analysis: The full analysis result.

    Returns:
        List of cross-cutting concern descriptions.
    """
    concerns: list[str] = []
    triage = analysis.triage

    # Check for widespread missing resource limits
    no_limits = sum(
        1 for ri in triage.resource_issues
        if "no limits" in ri.issue.lower() or "no requests" in ri.issue.lower()
    )
    if no_limits >= 3:
        concerns.append(
            f"{no_limits} containers have no resource limits/requests — "
            "cluster-wide resource governance issue"
        )

    # Check for multiple pods on same failure pattern
    issue_types: dict[str, int] = {}
    for pod in triage.critical_pods + triage.warning_pods:
        issue_types[pod.issue_type] = issue_types.get(pod.issue_type, 0) + 1
    for itype, count in issue_types.items():
        if count >= 3:
            concerns.append(
                f"{count} pods affected by {itype} — may indicate systemic issue"
            )

    # Check for missing probes across many pods
    no_probes = sum(
        1 for pi in triage.probe_issues
        if "not configured" in pi.issue.lower() or "missing" in pi.issue.lower()
    )
    if no_probes >= 3:
        concerns.append(
            f"{no_probes} containers missing health probes — "
            "reduces cluster self-healing capability"
        )

    # Check for many config issues
    if len(triage.config_issues) >= 5:
        concerns.append(
            f"{len(triage.config_issues)} configuration issues detected — "
            "review ConfigMap/Secret references across namespaces"
        )

    return concerns
