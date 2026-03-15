"""RCA rules for image errors and deployment-wide failures.

Rules: image_not_found, registry_auth_failure, deployment_wide_failure.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from bundle_analyzer.models.triage import PodIssue
from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import RCARule, all_pods, build_hypothesis


# ── Rule 5: ImagePullBackOff + not found -> Wrong Image Tag ──────────────

def _match_image_not_found(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing to pull images because the tag doesn't exist."""
    hits = [
        p for p in all_pods(triage)
        if p.issue_type == "ImagePullBackOff"
        and "not found" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_image_not_found(groups: list[list[Any]]) -> dict[str, Any]:
    pods: list[PodIssue] = groups[0]
    return build_hypothesis(
        title="Image Tag Not Found in Registry",
        description=(
            "One or more pods cannot start because the specified container "
            "image tag does not exist in the registry. This often happens "
            "after a failed CI/CD pipeline or a typo in the image reference."
        ),
        category="image_error",
        supporting_evidence=[
            f"{p.namespace}/{p.pod_name}: ImagePullBackOff — {p.message}"
            for p in pods
        ],
        affected_resources=[f"{p.namespace}/{p.pod_name}" for p in pods],
        suggested_fixes=[
            "Verify the image tag exists in the container registry",
            "Check CI/CD pipeline — the build/push step may have failed",
            "Roll back to the previous known-good image tag",
        ],
    )


# ── Rule 6: ImagePullBackOff + unauthorized -> Registry Auth ─────────────

def _match_registry_auth(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing to pull due to auth errors."""
    hits = [
        p for p in all_pods(triage)
        if p.issue_type == "ImagePullBackOff"
        and "unauthorized" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_registry_auth(groups: list[list[Any]]) -> dict[str, Any]:
    pods: list[PodIssue] = groups[0]
    return build_hypothesis(
        title="Container Registry Authentication Failure",
        description=(
            "Image pulls are failing with 'unauthorized' errors. The "
            "imagePullSecret may be missing, expired, or misconfigured."
        ),
        category="image_error",
        supporting_evidence=[
            f"{p.namespace}/{p.pod_name}: ImagePullBackOff — {p.message}"
            for p in pods
        ],
        affected_resources=[f"{p.namespace}/{p.pod_name}" for p in pods],
        suggested_fixes=[
            "Check that imagePullSecrets are configured on the pod/service account",
            "Verify the registry credentials have not expired",
            "Ensure the secret is in the same namespace as the pod",
        ],
    )


# ── Rule 9: All pods in deployment failing with same error ───────────────

def _match_deployment_wide(triage: TriageResult) -> list[list[Any]]:
    """Find deployments where all pods exhibit the same failure."""
    by_prefix: dict[str, list[PodIssue]] = defaultdict(list)
    for pod in all_pods(triage):
        parts = pod.pod_name.rsplit("-", 2)
        prefix = parts[0] if len(parts) >= 3 else pod.pod_name
        key = f"{pod.namespace}/{prefix}"
        by_prefix[key].append(pod)

    groups: list[list[Any]] = []
    for _key, pods in by_prefix.items():
        if len(pods) < 2:
            continue
        issue_types = {p.issue_type for p in pods}
        if len(issue_types) == 1:
            groups.append(pods)

    return groups if groups else []


def _hyp_deployment_wide(groups: list[list[Any]]) -> dict[str, Any]:
    all_pods_list: list[PodIssue] = []
    for g in groups:
        all_pods_list.extend(g)

    deploy_names: set[str] = set()
    for pod in all_pods_list:
        parts = pod.pod_name.rsplit("-", 2)
        prefix = parts[0] if len(parts) >= 3 else pod.pod_name
        deploy_names.add(f"{pod.namespace}/{prefix}")

    issue_type = all_pods_list[0].issue_type if all_pods_list else "unknown"
    return build_hypothesis(
        title=f"Deployment-Wide Failure ({issue_type})",
        description=(
            f"All pods in one or more deployments are failing with the same "
            f"error ({issue_type}). This points to a deployment-level root "
            f"cause rather than individual pod issues."
        ),
        category="config_error",
        confidence=0.8,
        supporting_evidence=[
            f"{p.namespace}/{p.pod_name}: {p.issue_type} "
            f"(exit_code={p.exit_code}, restarts={p.restart_count})"
            for p in all_pods_list[:10]
        ],
        affected_resources=list(deploy_names),
        suggested_fixes=[
            "Check the deployment spec for recent changes (image, env, config)",
            "Review the deployment rollout history",
            "Consider rolling back to the previous revision",
        ],
    )


# ── Exported rules ────────────────────────────────────────────────────────

DEPLOYMENT_RULES: list[RCARule] = [
    RCARule(name="image_not_found", match=_match_image_not_found, hypothesis_template=_hyp_image_not_found),
    RCARule(name="registry_auth_failure", match=_match_registry_auth, hypothesis_template=_hyp_registry_auth),
    RCARule(name="deployment_wide_failure", match=_match_deployment_wide, hypothesis_template=_hyp_deployment_wide),
]
