"""Crash loop permanence prediction functions.

Predicts whether crash loops are transient or permanent based on
restart count thresholds and backoff cap analysis.
"""

from __future__ import annotations

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure, TriageResult


def predict_crashloop_permanent(
    index: BundleIndex, triage: TriageResult
) -> list[PredictedFailure]:
    """Predict whether crash loops are transient or permanent.

    A crash loop with restartCount >= 10 where the backoff has reached
    the 5-minute cap is very likely permanent and needs human intervention.

    Args:
        index: The indexed support bundle.
        triage: The triage result from Phase 1 scanners.

    Returns:
        List of PredictedFailure objects for permanent crash loops.
    """
    predictions: list[PredictedFailure] = []

    for pod_issue in triage.critical_pods + triage.warning_pods:
        if pod_issue.issue_type != "CrashLoopBackOff":
            continue

        is_permanent = pod_issue.restart_count >= 10
        confidence = 0.9 if pod_issue.restart_count >= 20 else 0.75

        if is_permanent:
            predictions.append(
                PredictedFailure(
                    resource=(
                        f"pod/{pod_issue.namespace}/{pod_issue.pod_name}"
                    ),
                    failure_type="CRASHLOOP_PERMANENT",
                    estimated_eta_seconds=None,  # already happening
                    confidence=confidence,
                    evidence=[
                        f"restartCount={pod_issue.restart_count} "
                        f"(>=10 with 5min backoff cap = permanent)",
                        f"Exit code: {pod_issue.exit_code}",
                        f"Message: {pod_issue.message[:200]}"
                        if pod_issue.message
                        else "No error message",
                    ],
                    prevention=(
                        f"This crash loop will not self-resolve. "
                        f"Fix the underlying issue (exit code {pod_issue.exit_code}) "
                        f"and redeploy. "
                        f"Check: kubectl logs {pod_issue.pod_name} "
                        f"-n {pod_issue.namespace} --previous"
                    ),
                )
            )

    return predictions


def predict_crashloop_permanent_single(
    pod_json: dict,
) -> PredictedFailure | None:
    """Predict crash loop permanence for a single pod.

    Args:
        pod_json: Pod JSON with status containing restartCount.

    Returns:
        PredictedFailure if crash loop appears permanent, or None.
    """
    metadata = pod_json.get("metadata", {})
    pod_name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "unknown")
    status = pod_json.get("status", {})

    for cs in status.get("containerStatuses", []) or []:
        restart_count = cs.get("restartCount", 0)
        waiting = cs.get("state", {}).get("waiting", {})
        reason = waiting.get("reason", "")

        if reason == "CrashLoopBackOff" and restart_count >= 10:
            return PredictedFailure(
                resource=f"pod/{namespace}/{pod_name}/{cs.get('name', 'unknown')}",
                failure_type="CRASHLOOP_PERMANENT",
                estimated_eta_seconds=None,
                confidence=0.9 if restart_count >= 20 else 0.75,
                evidence=[
                    f"restartCount={restart_count}, backoff at 5min cap",
                ],
                prevention=(
                    f"Fix underlying issue and redeploy. "
                    f"kubectl logs {pod_name} -n {namespace} --previous"
                ),
            )
    return None
