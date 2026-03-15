"""Deterministic RCA rules mapping symptom patterns to root cause hypotheses.

Each rule inspects a TriageResult and returns matching finding groups that
support a particular root cause hypothesis. Rules are evaluated in order
and all matching rules contribute hypotheses to the engine.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from bundle_analyzer.models.triage import (
    ConfigIssue,
    DeploymentIssue,
    NodeIssue,
    PodIssue,
    SchedulingIssue,
    StorageIssue,
)
from bundle_analyzer.models.troubleshoot import TriageResult


# ---------------------------------------------------------------------------
# Forward reference: Hypothesis is defined in hypothesis_engine.py but we
# need a lightweight way to build them from rules without circular imports.
# We return dicts here; HypothesisEngine converts them to Hypothesis objects.
# ---------------------------------------------------------------------------


@dataclass
class RCARule:
    """A single deterministic root-cause analysis rule.

    Attributes:
        name: Human-readable rule identifier.
        match: Callable that inspects a TriageResult and returns a list of
            matching finding groups (each group is a list of findings).
            An empty return means the rule did not fire.
        hypothesis_template: Callable that takes the match groups and returns
            a dict suitable for constructing a Hypothesis.
    """

    name: str
    match: Callable[[TriageResult], list[list[Any]]]
    hypothesis_template: Callable[[list[list[Any]]], dict[str, Any]]


# ---- helper utilities -----------------------------------------------------

def _all_pods(triage: TriageResult) -> list[PodIssue]:
    """Return all pod issues (critical + warning)."""
    return list(triage.critical_pods) + list(triage.warning_pods)


def _gen_id() -> str:
    """Generate a short unique hypothesis id."""
    return uuid.uuid4().hex[:12]


# ===========================================================================
# Rule 1: CrashLoopBackOff + exit code 137 -> OOM Kill
# ===========================================================================

def _match_oom(triage: TriageResult) -> list[list[Any]]:
    """Find pods crash-looping with exit code 137 (OOM killed)."""
    hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "CrashLoopBackOff" and p.exit_code == 137
    ]
    return [hits] if hits else []


def _hyp_oom(groups: list[list[Any]]) -> dict[str, Any]:
    """Build OOM kill hypothesis."""
    pods: list[PodIssue] = groups[0]
    return {
        "id": _gen_id(),
        "title": "Container OOM Killed",
        "description": (
            "One or more containers are being killed by the kernel OOM killer "
            "(exit code 137). This typically means the container's memory limit "
            "is too low for its workload."
        ),
        "category": "resource_exhaustion",
        "supporting_evidence": [
            f"{p.namespace}/{p.pod_name}: CrashLoopBackOff with exit code 137 "
            f"(restarts: {p.restart_count})"
            for p in pods
        ],
        "contradicting_evidence": [],
        "affected_resources": [f"{p.namespace}/{p.pod_name}" for p in pods],
        "suggested_fixes": [
            "Increase memory limits in the container resource spec",
            "Profile the application to find memory leaks",
            "Check if the JVM/runtime heap is configured within the container limit",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 2: CrashLoopBackOff + exit code 1 + "connection refused" -> Dependency
# ===========================================================================

def _match_dependency_refused(triage: TriageResult) -> list[list[Any]]:
    """Find pods crash-looping with connection refused errors."""
    hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "CrashLoopBackOff"
        and p.exit_code == 1
        and "connection refused" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_dependency_refused(groups: list[list[Any]]) -> dict[str, Any]:
    """Build dependency unavailable hypothesis."""
    pods: list[PodIssue] = groups[0]
    return {
        "id": _gen_id(),
        "title": "Dependency Service Unavailable",
        "description": (
            "Containers are crash-looping because a required dependency is "
            "refusing connections. The upstream service may be down, not yet "
            "started, or misconfigured."
        ),
        "category": "dependency_failure",
        "supporting_evidence": [
            f"{p.namespace}/{p.pod_name}: CrashLoopBackOff exit 1 — "
            f"'{p.message}'"
            for p in pods
        ],
        "contradicting_evidence": [],
        "affected_resources": [f"{p.namespace}/{p.pod_name}" for p in pods],
        "suggested_fixes": [
            "Check that the upstream service/database is running and healthy",
            "Verify connection string / service DNS name is correct",
            "Add init containers or readiness gates to wait for dependencies",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 3: Pending + FailedScheduling + "insufficient cpu" -> Node Capacity
# ===========================================================================

def _match_insufficient_cpu(triage: TriageResult) -> list[list[Any]]:
    """Find pods pending due to insufficient CPU."""
    scheduling: list[SchedulingIssue] = getattr(triage, "scheduling_issues", [])
    hits = [
        s for s in scheduling
        if s.issue_type == "insufficient_cpu"
    ]
    # Also check pending pods with scheduling messages
    pod_hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "Pending"
        and "insufficient cpu" in (p.message or "").lower()
    ]
    combined = hits + pod_hits
    return [combined] if combined else []


def _hyp_insufficient_cpu(groups: list[list[Any]]) -> dict[str, Any]:
    """Build node capacity hypothesis."""
    findings = groups[0]
    resources = []
    evidence = []
    for f in findings:
        if isinstance(f, SchedulingIssue):
            resources.append(f"{f.namespace}/{f.pod_name}")
            evidence.append(f"{f.namespace}/{f.pod_name}: {f.message}")
        else:
            resources.append(f"{f.namespace}/{f.pod_name}")
            evidence.append(
                f"{f.namespace}/{f.pod_name}: Pending — {f.message}"
            )
    return {
        "id": _gen_id(),
        "title": "Insufficient CPU Capacity on Nodes",
        "description": (
            "Pods cannot be scheduled because no node has enough available CPU. "
            "The cluster may need horizontal scaling or resource requests may "
            "be too high."
        ),
        "category": "scheduling",
        "supporting_evidence": evidence,
        "contradicting_evidence": [],
        "affected_resources": resources,
        "suggested_fixes": [
            "Add more nodes or enable cluster autoscaler",
            "Reduce CPU requests on less critical workloads",
            "Check for pods with excessively high CPU requests",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 4: Pending + FailedScheduling + "taint" -> Missing Toleration
# ===========================================================================

def _match_taint(triage: TriageResult) -> list[list[Any]]:
    """Find pods unschedulable due to taints."""
    scheduling: list[SchedulingIssue] = getattr(triage, "scheduling_issues", [])
    hits = [
        s for s in scheduling
        if s.issue_type == "taint_not_tolerated"
    ]
    pod_hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "Pending"
        and "taint" in (p.message or "").lower()
    ]
    combined = hits + pod_hits
    return [combined] if combined else []


def _hyp_taint(groups: list[list[Any]]) -> dict[str, Any]:
    """Build missing toleration hypothesis."""
    findings = groups[0]
    resources = []
    evidence = []
    for f in findings:
        name = f"{f.namespace}/{f.pod_name}" if hasattr(f, "pod_name") else str(f)
        resources.append(name)
        msg = f.message if hasattr(f, "message") else str(f)
        evidence.append(f"{name}: taint not tolerated — {msg}")
    return {
        "id": _gen_id(),
        "title": "Missing Node Toleration",
        "description": (
            "Pods cannot be scheduled because they lack tolerations for node "
            "taints. This is common after node pool changes or when deploying "
            "to dedicated/GPU nodes."
        ),
        "category": "scheduling",
        "supporting_evidence": evidence,
        "contradicting_evidence": [],
        "affected_resources": resources,
        "suggested_fixes": [
            "Add the required toleration to the pod spec",
            "Remove or modify the taint on the target nodes",
            "Use nodeSelector or nodeAffinity to target untainted nodes",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 5: ImagePullBackOff + "not found" -> Wrong Image Tag
# ===========================================================================

def _match_image_not_found(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing to pull images because the tag doesn't exist."""
    hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "ImagePullBackOff"
        and "not found" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_image_not_found(groups: list[list[Any]]) -> dict[str, Any]:
    """Build wrong image tag hypothesis."""
    pods: list[PodIssue] = groups[0]
    return {
        "id": _gen_id(),
        "title": "Image Tag Not Found in Registry",
        "description": (
            "One or more pods cannot start because the specified container "
            "image tag does not exist in the registry. This often happens "
            "after a failed CI/CD pipeline or a typo in the image reference."
        ),
        "category": "image_error",
        "supporting_evidence": [
            f"{p.namespace}/{p.pod_name}: ImagePullBackOff — {p.message}"
            for p in pods
        ],
        "contradicting_evidence": [],
        "affected_resources": [f"{p.namespace}/{p.pod_name}" for p in pods],
        "suggested_fixes": [
            "Verify the image tag exists in the container registry",
            "Check CI/CD pipeline — the build/push step may have failed",
            "Roll back to the previous known-good image tag",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 6: ImagePullBackOff + "unauthorized" -> Registry Auth
# ===========================================================================

def _match_registry_auth(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing to pull due to auth errors."""
    hits = [
        p for p in _all_pods(triage)
        if p.issue_type == "ImagePullBackOff"
        and "unauthorized" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_registry_auth(groups: list[list[Any]]) -> dict[str, Any]:
    """Build registry auth hypothesis."""
    pods: list[PodIssue] = groups[0]
    return {
        "id": _gen_id(),
        "title": "Container Registry Authentication Failure",
        "description": (
            "Image pulls are failing with 'unauthorized' errors. The "
            "imagePullSecret may be missing, expired, or misconfigured."
        ),
        "category": "image_error",
        "supporting_evidence": [
            f"{p.namespace}/{p.pod_name}: ImagePullBackOff — {p.message}"
            for p in pods
        ],
        "contradicting_evidence": [],
        "affected_resources": [f"{p.namespace}/{p.pod_name}" for p in pods],
        "suggested_fixes": [
            "Check that imagePullSecrets are configured on the pod/service account",
            "Verify the registry credentials have not expired",
            "Ensure the secret is in the same namespace as the pod",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 7: Pod failing + empty endpoints on referenced service -> Dep Down
# ===========================================================================

def _match_empty_endpoints(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing alongside services with no ready endpoints.

    This cross-references deployment issues (0 ready replicas) with pods
    that have connection errors referencing those services.
    """
    # Build a set of deployments with zero ready replicas
    down_deployments: set[str] = set()
    for dep in triage.deployment_issues:
        if dep.ready_replicas == 0:
            down_deployments.add(f"{dep.namespace}/{dep.name}")

    if not down_deployments:
        return []

    # Find pods that are failing and might depend on those deployments
    failing_pods = [
        p for p in _all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending")
        and p.message
    ]

    if not failing_pods:
        return []

    # Group: [[failing_pods, down_deployment_names]]
    return [[failing_pods, list(down_deployments)]]


def _hyp_empty_endpoints(groups: list[list[Any]]) -> dict[str, Any]:
    """Build dependency down hypothesis."""
    pods = groups[0][0]
    down_deps = groups[0][1]
    return {
        "id": _gen_id(),
        "title": "Dependency Deployment Has Zero Ready Endpoints",
        "description": (
            "One or more deployments have zero ready replicas, meaning any "
            "service pointing to them will have empty endpoints. Pods "
            "depending on these services will fail with connection errors."
        ),
        "category": "dependency_failure",
        "supporting_evidence": [
            f"Deployment {d} has 0 ready replicas" for d in down_deps
        ] + [
            f"{p.namespace}/{p.pod_name}: {p.issue_type} — {p.message}"
            for p in pods[:5]  # cap evidence lines
        ],
        "contradicting_evidence": [],
        "affected_resources": down_deps + [
            f"{p.namespace}/{p.pod_name}" for p in pods
        ],
        "suggested_fixes": [
            "Investigate why the upstream deployment has zero ready pods",
            "Check upstream deployment events and pod logs",
            "Consider adding retry/backoff logic in dependent services",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 8: Multiple pods on same node failing -> Node Issue
# ===========================================================================

def _match_node_issue(triage: TriageResult) -> list[list[Any]]:
    """Find cases where multiple failing pods share a troubled node."""
    if not triage.node_issues:
        return []

    bad_nodes = {n.node_name for n in triage.node_issues}

    # We can't always determine node from PodIssue (field may not exist),
    # but node_issues themselves are strong evidence.
    # Group node issues by node.
    by_node: dict[str, list[NodeIssue]] = defaultdict(list)
    for ni in triage.node_issues:
        by_node[ni.node_name].append(ni)

    groups: list[list[Any]] = []
    for node_name, issues in by_node.items():
        groups.append(issues)

    return groups if groups else []


def _hyp_node_issue(groups: list[list[Any]]) -> dict[str, Any]:
    """Build node-level issue hypothesis."""
    all_issues: list[NodeIssue] = []
    for g in groups:
        all_issues.extend(g)

    node_names = list({ni.node_name for ni in all_issues})
    return {
        "id": _gen_id(),
        "title": "Node-Level Infrastructure Problem",
        "description": (
            "One or more nodes are reporting unhealthy conditions (NotReady, "
            "MemoryPressure, DiskPressure, etc.). All pods on affected nodes "
            "may be impacted."
        ),
        "category": "resource_exhaustion",
        "supporting_evidence": [
            f"Node {ni.node_name}: {ni.condition} — {ni.message}"
            for ni in all_issues
        ],
        "contradicting_evidence": [],
        "affected_resources": node_names,
        "suggested_fixes": [
            "Check node system metrics (memory, disk, CPU)",
            "Drain and cordon affected nodes if possible",
            "Investigate kubelet logs on the affected nodes",
            "Consider replacing the node if hardware failure is suspected",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Rule 9: All pods in deployment failing with same error -> Deployment Issue
# ===========================================================================

def _match_deployment_wide(triage: TriageResult) -> list[list[Any]]:
    """Find deployments where all pods exhibit the same failure."""
    # Group failing pods by likely deployment (namespace + pod name prefix)
    by_prefix: dict[str, list[PodIssue]] = defaultdict(list)
    for pod in _all_pods(triage):
        # Kubernetes pod names: <deployment>-<replicaset-hash>-<pod-hash>
        parts = pod.pod_name.rsplit("-", 2)
        prefix = parts[0] if len(parts) >= 3 else pod.pod_name
        key = f"{pod.namespace}/{prefix}"
        by_prefix[key].append(pod)

    groups: list[list[Any]] = []
    for key, pods in by_prefix.items():
        if len(pods) < 2:
            continue
        # Check that all pods share the same issue type
        issue_types = {p.issue_type for p in pods}
        if len(issue_types) == 1:
            groups.append(pods)

    return groups if groups else []


def _hyp_deployment_wide(groups: list[list[Any]]) -> dict[str, Any]:
    """Build deployment-level issue hypothesis."""
    all_pods: list[PodIssue] = []
    for g in groups:
        all_pods.extend(g)

    # Derive deployment names
    deploy_names: set[str] = set()
    for pod in all_pods:
        parts = pod.pod_name.rsplit("-", 2)
        prefix = parts[0] if len(parts) >= 3 else pod.pod_name
        deploy_names.add(f"{pod.namespace}/{prefix}")

    issue_type = all_pods[0].issue_type if all_pods else "unknown"
    return {
        "id": _gen_id(),
        "title": f"Deployment-Wide Failure ({issue_type})",
        "description": (
            f"All pods in one or more deployments are failing with the same "
            f"error ({issue_type}). This points to a deployment-level root "
            f"cause rather than individual pod issues."
        ),
        "category": "config_error",
        "supporting_evidence": [
            f"{p.namespace}/{p.pod_name}: {p.issue_type} "
            f"(exit_code={p.exit_code}, restarts={p.restart_count})"
            for p in all_pods[:10]
        ],
        "contradicting_evidence": [],
        "affected_resources": list(deploy_names),
        "suggested_fixes": [
            "Check the deployment spec for recent changes (image, env, config)",
            "Review the deployment rollout history",
            "Consider rolling back to the previous revision",
        ],
        "is_validated": True,
    }


# ===========================================================================
# Exported rule list — evaluated in order by HypothesisEngine
# ===========================================================================

RCA_RULES: list[RCARule] = [
    RCARule(name="oom_kill", match=_match_oom, hypothesis_template=_hyp_oom),
    RCARule(
        name="dependency_connection_refused",
        match=_match_dependency_refused,
        hypothesis_template=_hyp_dependency_refused,
    ),
    RCARule(
        name="insufficient_cpu",
        match=_match_insufficient_cpu,
        hypothesis_template=_hyp_insufficient_cpu,
    ),
    RCARule(
        name="taint_not_tolerated",
        match=_match_taint,
        hypothesis_template=_hyp_taint,
    ),
    RCARule(
        name="image_not_found",
        match=_match_image_not_found,
        hypothesis_template=_hyp_image_not_found,
    ),
    RCARule(
        name="registry_auth_failure",
        match=_match_registry_auth,
        hypothesis_template=_hyp_registry_auth,
    ),
    RCARule(
        name="empty_endpoints",
        match=_match_empty_endpoints,
        hypothesis_template=_hyp_empty_endpoints,
    ),
    RCARule(
        name="node_issue",
        match=_match_node_issue,
        hypothesis_template=_hyp_node_issue,
    ),
    RCARule(
        name="deployment_wide_failure",
        match=_match_deployment_wide,
        hypothesis_template=_hyp_deployment_wide,
    ),
]
