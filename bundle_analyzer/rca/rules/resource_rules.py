"""RCA rules for resource exhaustion, scheduling, and node-level issues.

Rules: oom_kill, insufficient_cpu, taint_not_tolerated, node_issue,
       storage_cascade, quota_scheduling.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models.triage import (
    NodeIssue,
    PodIssue,
    QuotaIssue,
    SchedulingIssue,
    StorageIssue,
)
from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import RCARule, all_pods, build_hypothesis


# ── Rule 1: CrashLoopBackOff + exit code 137 -> OOM Kill ─────────────────

def _match_oom(triage: TriageResult) -> list[list[Any]]:
    """Find pods crash-looping with exit code 137 (OOM killed)."""
    hits = [
        p for p in all_pods(triage)
        if (p.issue_type == "OOMKilled")
        or (p.issue_type == "CrashLoopBackOff" and p.exit_code == 137)
    ]
    return [hits] if hits else []


def _hyp_oom(groups: list[list[Any]]) -> dict[str, Any]:
    pods: list[PodIssue] = groups[0]
    return build_hypothesis(
        title="Container OOM Killed",
        description=(
            "One or more containers are being killed by the kernel OOM killer "
            "(exit code 137). This typically means the container's memory limit "
            "is too low for its workload."
        ),
        category="resource_exhaustion",
        supporting_evidence=[
            f"{p.namespace}/{p.pod_name}: CrashLoopBackOff with exit code 137 "
            f"(restarts: {p.restart_count})"
            for p in pods
        ],
        affected_resources=[f"{p.namespace}/{p.pod_name}" for p in pods],
        suggested_fixes=[
            "Increase memory limits in the container resource spec",
            "Profile the application to find memory leaks",
            "Check if the JVM/runtime heap is configured within the container limit",
        ],
    )


# ── Rule 3: Pending + insufficient cpu -> Node Capacity ──────────────────

def _match_insufficient_cpu(triage: TriageResult) -> list[list[Any]]:
    """Find pods pending due to insufficient CPU."""
    scheduling: list[SchedulingIssue] = triage.scheduling_issues
    hits = [s for s in scheduling if s.issue_type == "insufficient_cpu"]
    pod_hits = [
        p for p in all_pods(triage)
        if p.issue_type == "Pending"
        and "insufficient cpu" in (p.message or "").lower()
    ]
    combined = hits + pod_hits
    return [combined] if combined else []


def _hyp_insufficient_cpu(groups: list[list[Any]]) -> dict[str, Any]:
    findings = groups[0]
    evidence = []
    resources = []
    for f in findings:
        name = f"{f.namespace}/{f.pod_name}"
        resources.append(name)
        if isinstance(f, SchedulingIssue):
            evidence.append(f"{name}: {f.message}")
        else:
            evidence.append(f"{name}: Pending — {f.message}")
    return build_hypothesis(
        title="Insufficient CPU Capacity on Nodes",
        description=(
            "Pods cannot be scheduled because no node has enough available CPU. "
            "The cluster may need horizontal scaling or resource requests may "
            "be too high."
        ),
        category="scheduling",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Add more nodes or enable cluster autoscaler",
            "Reduce CPU requests on less critical workloads",
            "Check for pods with excessively high CPU requests",
        ],
    )


# ── Rule 4: Pending + taint -> Missing Toleration ────────────────────────

def _match_taint(triage: TriageResult) -> list[list[Any]]:
    """Find pods unschedulable due to taints."""
    scheduling: list[SchedulingIssue] = triage.scheduling_issues
    hits = [s for s in scheduling if s.issue_type == "taint_not_tolerated"]
    pod_hits = [
        p for p in all_pods(triage)
        if p.issue_type == "Pending"
        and "taint" in (p.message or "").lower()
    ]
    combined = hits + pod_hits
    return [combined] if combined else []


def _hyp_taint(groups: list[list[Any]]) -> dict[str, Any]:
    findings = groups[0]
    evidence = []
    resources = []
    for f in findings:
        name = f"{f.namespace}/{f.pod_name}" if hasattr(f, "pod_name") else str(f)
        resources.append(name)
        msg = f.message if hasattr(f, "message") else str(f)
        evidence.append(f"{name}: taint not tolerated — {msg}")
    return build_hypothesis(
        title="Missing Node Toleration",
        description=(
            "Pods cannot be scheduled because they lack tolerations for node "
            "taints. This is common after node pool changes or when deploying "
            "to dedicated/GPU nodes."
        ),
        category="scheduling",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Add the required toleration to the pod spec",
            "Remove or modify the taint on the target nodes",
            "Use nodeSelector or nodeAffinity to target untainted nodes",
        ],
    )


# ── Rule 8: Multiple pods on same node failing -> Node Issue ─────────────

def _match_node_issue(triage: TriageResult) -> list[list[Any]]:
    """Find cases where nodes report unhealthy conditions."""
    if not triage.node_issues:
        return []
    return [list(triage.node_issues)]


def _hyp_node_issue(groups: list[list[Any]]) -> dict[str, Any]:
    all_issues: list[NodeIssue] = []
    for g in groups:
        all_issues.extend(g)

    node_names = list({ni.node_name for ni in all_issues})
    return build_hypothesis(
        title="Node-Level Infrastructure Problem",
        description=(
            "One or more nodes are reporting unhealthy conditions (NotReady, "
            "MemoryPressure, DiskPressure, etc.). All pods on affected nodes "
            "may be impacted."
        ),
        category="resource_exhaustion",
        supporting_evidence=[
            f"Node {ni.node_name}: {ni.condition} — {ni.message}"
            for ni in all_issues
        ],
        affected_resources=node_names,
        suggested_fixes=[
            "Check node system metrics (memory, disk, CPU)",
            "Drain and cordon affected nodes if possible",
            "Investigate kubelet logs on the affected nodes",
            "Consider replacing the node if hardware failure is suspected",
        ],
    )


# ── Rule 12: Storage -> Pod cascade ──────────────────────────────────────

def _match_storage_cascade(triage: TriageResult) -> list[list[Any]]:
    """Find storage issues that cause pods to be stuck."""
    storage_issues: list[StorageIssue] = triage.storage_issues
    if not storage_issues:
        return []
    pending_pods = [p for p in all_pods(triage) if p.issue_type in ("Pending", "FailedMount")]
    return [[storage_issues, pending_pods]] if pending_pods or storage_issues else []


def _hyp_storage_cascade(groups: list[list[Any]]) -> dict[str, Any]:
    storage_issues = groups[0][0]
    pending_pods = groups[0][1]
    evidence = [f"Storage: {s.namespace}/{s.resource_name} — {s.issue} ({s.message})" for s in storage_issues]
    evidence += [f"{p.namespace}/{p.pod_name}: {p.issue_type} — {p.message}" for p in pending_pods[:5]]
    resources = [f"{s.namespace}/{s.resource_name}" for s in storage_issues]
    resources += [f"{p.namespace}/{p.pod_name}" for p in pending_pods]
    return build_hypothesis(
        title="Storage Issue Causing Pod Scheduling Failure",
        description=(
            "PVC/PV issues are preventing pods from being scheduled or starting. "
            "Pods waiting for volumes will remain in Pending state."
        ),
        category="dependency_failure",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Check PVC status and storage class provisioner logs",
            "Verify the StorageClass exists and is functioning",
            "Check if the volume has been released and needs manual reclaim",
        ],
    )


# ── Rule 13: Quota -> Scheduling failure ─────────────────────────────────

def _match_quota_scheduling(triage: TriageResult) -> list[list[Any]]:
    """Find quota limits causing scheduling failures."""
    quota_issues: list[QuotaIssue] = triage.quota_issues
    exceeded = [q for q in quota_issues if q.issue_type in ("quota_exceeded", "quota_near_limit")]
    if not exceeded:
        return []
    pending = [p for p in all_pods(triage) if p.issue_type == "Pending"]
    return [[exceeded, pending]]


def _hyp_quota_scheduling(groups: list[list[Any]]) -> dict[str, Any]:
    quota_issues = groups[0][0]
    pending_pods = groups[0][1]
    evidence = [f"Quota: {q.namespace}/{q.resource_name} — {q.issue_type} ({q.message})" for q in quota_issues]
    evidence += [f"{p.namespace}/{p.pod_name}: Pending — {p.message}" for p in pending_pods[:5]]
    resources = [f"{q.namespace}/{q.resource_name}" for q in quota_issues]
    resources += [f"{p.namespace}/{p.pod_name}" for p in pending_pods]
    return build_hypothesis(
        title="Resource Quota Preventing Pod Scheduling",
        description=(
            "Resource quotas are exceeded or near limit, which may prevent new "
            "pods from being scheduled in the affected namespaces."
        ),
        category="scheduling",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Increase resource quotas for the namespace",
            "Reduce resource requests on existing workloads",
            "Delete unused pods/deployments to free up quota",
        ],
    )


# ── Exported rules ────────────────────────────────────────────────────────

OOM_KILL_RULE = RCARule(name="oom_kill", match=_match_oom, hypothesis_template=_hyp_oom)
INSUFFICIENT_CPU_RULE = RCARule(name="insufficient_cpu", match=_match_insufficient_cpu, hypothesis_template=_hyp_insufficient_cpu)
TAINT_RULE = RCARule(name="taint_not_tolerated", match=_match_taint, hypothesis_template=_hyp_taint)
NODE_ISSUE_RULE = RCARule(name="node_issue", match=_match_node_issue, hypothesis_template=_hyp_node_issue)
STORAGE_CASCADE_RULE = RCARule(name="storage_cascade", match=_match_storage_cascade, hypothesis_template=_hyp_storage_cascade)
QUOTA_SCHEDULING_RULE = RCARule(name="quota_scheduling", match=_match_quota_scheduling, hypothesis_template=_hyp_quota_scheduling)
