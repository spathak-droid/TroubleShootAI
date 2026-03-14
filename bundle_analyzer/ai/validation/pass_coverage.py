"""Pass 2: Coverage analysis.

Finds critical triage signals that no finding addresses — these are
MissedFailurePoints that the AI pipeline overlooked.
"""

from __future__ import annotations

from bundle_analyzer.models import (
    AnalysisResult,
    DependencyLink,
    MissedFailurePoint,
)

from .helpers import normalize_resource_key


def analyze_coverage(analysis: AnalysisResult) -> list[MissedFailurePoint]:
    """Find critical triage signals that no finding addresses.

    Args:
        analysis: The full analysis result.

    Returns:
        List of MissedFailurePoint for uncovered critical signals.
    """
    # Build set of resources covered by findings
    covered: set[str] = set()
    for finding in analysis.findings:
        if finding.resource:
            key = normalize_resource_key(finding.resource)
            covered.add(f"{key[0]}/{key[1]}/{key[2]}")
            covered.add(f"{key[1]}/{key[2]}")

    missed: list[MissedFailurePoint] = []
    triage = analysis.triage

    _check_critical_pods(triage, covered, missed)
    _check_probe_issues(triage, covered, missed)
    _check_config_issues(triage, covered, missed)

    # Deduplicate by resource
    seen: set[str] = set()
    deduped: list[MissedFailurePoint] = []
    for m in missed:
        if m.resource not in seen:
            seen.add(m.resource)
            deduped.append(m)

    return deduped


def _check_critical_pods(
    triage: object,
    covered: set[str],
    missed: list[MissedFailurePoint],
) -> None:
    """Check for critical pods not covered by any finding.

    Args:
        triage: The triage result object.
        covered: Set of covered resource keys.
        missed: List to append missed points to (mutated in place).
    """
    for pod in triage.critical_pods:  # type: ignore[attr-defined]
        pod_key = f"{pod.namespace}/{pod.pod_name}"
        if pod_key not in covered and f"pod/{pod_key}" not in covered:
            missed.append(MissedFailurePoint(
                failure_point=f"{pod.issue_type}: {pod.pod_name}",
                resource=f"Pod/{pod.namespace}/{pod.pod_name}",
                evidence_summary=pod.message,
                severity="critical",
                dependency_chain=[DependencyLink(
                    step_number=1,
                    resource=f"Pod/{pod.namespace}/{pod.pod_name}",
                    observation=f"{pod.issue_type} — restarts={pod.restart_count}, "
                                f"exit_code={pod.exit_code}",
                    evidence_source="triage/pod_scanner",
                    evidence_excerpt=pod.message[:80],
                    leads_to="No AI finding addresses this critical pod",
                    significance="symptom",
                )],
                correlated_signals=[],
                recommended_action=f"Investigate {pod.issue_type} for {pod.pod_name}",
            ))


def _check_probe_issues(
    triage: object,
    covered: set[str],
    missed: list[MissedFailurePoint],
) -> None:
    """Check for critical probe issues not covered by any finding.

    Args:
        triage: The triage result object.
        covered: Set of covered resource keys.
        missed: List to append missed points to (mutated in place).
    """
    for pi in triage.probe_issues:  # type: ignore[attr-defined]
        if pi.severity != "critical":
            continue
        pod_key = f"{pi.namespace}/{pi.pod_name}"
        if pod_key not in covered and f"pod/{pod_key}" not in covered:
            missed.append(MissedFailurePoint(
                failure_point=f"Probe failure: {pi.pod_name}/{pi.container_name}",
                resource=f"Pod/{pi.namespace}/{pi.pod_name}",
                evidence_summary=f"{pi.probe_type} probe: {pi.message}",
                severity="critical",
                dependency_chain=[DependencyLink(
                    step_number=1,
                    resource=f"Pod/{pi.namespace}/{pi.pod_name}",
                    observation=f"{pi.probe_type} probe — {pi.issue}",
                    evidence_source="triage/probe_scanner",
                    evidence_excerpt=pi.message[:80],
                    leads_to="No AI finding addresses this probe failure",
                    significance="root_cause",
                )],
                recommended_action=f"Fix {pi.probe_type} probe configuration",
            ))


def _check_config_issues(
    triage: object,
    covered: set[str],
    missed: list[MissedFailurePoint],
) -> None:
    """Check for missing config references not covered by any finding.

    Args:
        triage: The triage result object.
        covered: Set of covered resource keys.
        missed: List to append missed points to (mutated in place).
    """
    for ci in triage.config_issues:  # type: ignore[attr-defined]
        if "missing" not in ci.issue.lower():
            continue
        config_key = f"{ci.namespace}/{ci.resource_name}"
        if config_key not in covered and f"configmap/{config_key}" not in covered:
            already_covered = False
            ref_by = ci.referenced_by or ""
            for cov_key in covered:
                if ref_by and ref_by.lower() in cov_key.lower():
                    already_covered = True
                    break
            if not already_covered:
                missed.append(MissedFailurePoint(
                    failure_point=f"Missing {ci.resource_type}: {ci.resource_name}",
                    resource=f"{ci.resource_type}/{ci.namespace}/{ci.resource_name}",
                    evidence_summary=f"{ci.issue} — referenced by {ci.referenced_by}",
                    severity="warning",
                    dependency_chain=[DependencyLink(
                        step_number=1,
                        resource=f"{ci.resource_type}/{ci.namespace}/{ci.resource_name}",
                        observation=ci.issue,
                        evidence_source="triage/config_scanner",
                        evidence_excerpt=f"referenced_by: {ci.referenced_by}",
                        leads_to="Pod may fail to start due to missing config",
                        significance="contributing",
                    )],
                    recommended_action=f"Create missing {ci.resource_type} '{ci.resource_name}' "
                                      f"in namespace '{ci.namespace}'",
                ))
