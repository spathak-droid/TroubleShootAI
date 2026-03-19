"""RCA rules for connection pool exhaustion, broken dependencies, change correlation,
resource overcommitment, and DNS+NetworkPolicy lockout.

Rules: connection_pool_exhaustion, broken_dependency, change_correlated_failure,
       resource_overcommit, dns_netpol_lockout.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import (
    RCARule,
    all_pods,
    build_hypothesis,
    log_intel_pods,
)


# ── Rule: Connection Pool Exhaustion ─────────────────────────────────────

_POOL_EVENT_KEYWORDS = {"too many connections", "connection pool", "max_connections"}


def _match_connection_pool(triage: TriageResult) -> list[list[Any]]:
    """Find connection pool exhaustion from log intelligence and crash contexts."""
    # Check log_intelligence for connection errors
    conn_error_pods: list[tuple[str, Any]] = []
    for key, pod_intel in triage.log_intelligence.items():
        containers = getattr(pod_intel, "containers", [])
        for container in containers:
            if getattr(container, "has_connection_errors", False):
                conn_error_pods.append((key, pod_intel))
                break

    # Check crash contexts for dependency_timeout
    dep_timeout_crashes = [
        ctx for ctx in triage.crash_contexts
        if ctx.crash_pattern == "dependency_timeout"
    ]

    # Check events for pool-related messages
    pool_events = [
        e for e in triage.warning_events
        if any(kw in e.message.lower() for kw in _POOL_EVENT_KEYWORDS)
    ]

    # Check for high replica counts (amplifies connection pool issues)
    high_replica_deps = [
        d for d in triage.deployment_issues
        if d.desired_replicas >= 4
    ]

    # Check dependency_map for broken dependencies with connection issues
    broken_deps: list[Any] = []
    if triage.dependency_map is not None:
        broken_deps = getattr(triage.dependency_map, "broken_dependencies", []) or []

    if not conn_error_pods:
        return []

    if not high_replica_deps and not dep_timeout_crashes and not pool_events:
        return []

    return [[conn_error_pods, dep_timeout_crashes, pool_events, high_replica_deps, broken_deps]]


def _hyp_connection_pool(groups: list[list[Any]]) -> dict[str, Any]:
    conn_pods = groups[0][0]
    crashes = groups[0][1]
    events = groups[0][2]
    high_replicas = groups[0][3]
    broken_deps = groups[0][4]

    evidence = [
        f"Log intelligence: {key} has connection errors"
        for key, _ in conn_pods[:5]
    ]
    evidence += [
        f"Crash: {ctx.namespace}/{ctx.pod_name} — pattern={ctx.crash_pattern}"
        for ctx in crashes[:3]
    ]
    evidence += [
        f"Event: {e.namespace}/{e.involved_object_name} — {e.message[:100]}"
        for e in events[:3]
    ]
    evidence += [
        f"High replicas: {d.namespace}/{d.name} desired={d.desired_replicas}"
        for d in high_replicas[:3]
    ]

    resources = [key for key, _ in conn_pods]
    resources += [f"{d.namespace}/{d.name}" for d in high_replicas]

    return build_hypothesis(
        title="Database Connection Pool Exhaustion",
        description=(
            "Application pods show connection errors that indicate database "
            "connection pool exhaustion. High replica counts multiply the "
            "number of connections, potentially exceeding the database's "
            "max_connections limit."
        ),
        category="dependency_failure",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Reduce DB_POOL_SIZE per replica to stay under max_connections",
            "Deploy a connection pooler like PgBouncer or ProxySQL",
            "Increase the database's max_connections setting",
            "Consider reducing replica count if connection pressure is the bottleneck",
        ],
    )


# ── Rule: Broken Dependency ─────────────────────────────────────────────


def _match_broken_dependency(triage: TriageResult) -> list[list[Any]]:
    """Find broken service dependencies from dependency_map."""
    if triage.dependency_map is None:
        return []

    broken = getattr(triage.dependency_map, "broken_dependencies", None) or []
    if not broken:
        return []

    # Cross-reference with failing pods
    failing = {
        f"{p.namespace}/{p.pod_name}"
        for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending", "Evicted")
    }

    # Cross-reference with log_intelligence connection errors
    conn_error_keys: set[str] = set()
    for key, pod_intel in triage.log_intelligence.items():
        containers = getattr(pod_intel, "containers", [])
        for container in containers:
            if getattr(container, "has_connection_errors", False):
                conn_error_keys.add(key)
                break

    return [[broken, failing, conn_error_keys]]


def _hyp_broken_dependency(groups: list[list[Any]]) -> dict[str, Any]:
    broken = groups[0][0]
    failing = groups[0][1]
    conn_keys = groups[0][2]

    evidence = []
    resources = []
    for dep in broken[:5]:
        source = getattr(dep, "source", str(dep))
        target = getattr(dep, "target", "unknown")
        method = getattr(dep, "discovery_method", "unknown")
        health = getattr(dep, "health_detail", "")
        evidence.append(
            f"Broken dependency: {source} → {target} "
            f"(discovery={method}) {health[:80]}"
        )
        resources.append(str(source))

    if conn_keys:
        evidence.append(f"Pods with connection errors: {', '.join(list(conn_keys)[:5])}")

    return build_hypothesis(
        title="Broken Service Dependency Detected",
        description=(
            "The dependency scanner detected broken service dependencies. "
            "Source pods cannot reach their target services, causing failures "
            "that may cascade through the dependency chain."
        ),
        category="dependency_failure",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Check that the target service exists and has ready endpoints",
            "Verify DNS resolution for the target service name",
            "Check NetworkPolicies that may block traffic between services",
            "Review service port and selector configuration",
        ],
    )


# ── Rule: Change Correlated Failure ──────────────────────────────────────


def _match_change_correlation(triage: TriageResult) -> list[list[Any]]:
    """Find strong correlations between recent changes and failures."""
    if triage.change_report is None:
        return []

    correlations = getattr(triage.change_report, "correlations", None) or []
    strong = [
        c for c in correlations
        if getattr(c, "correlation_strength", "") == "strong"
    ]

    if not strong:
        return []

    return [[strong]]


def _hyp_change_correlation(groups: list[list[Any]]) -> dict[str, Any]:
    correlations = groups[0]

    evidence = []
    resources = []
    for corr in correlations[:5]:
        change_type = getattr(corr, "change_type", "unknown")
        resource = getattr(corr, "resource", "unknown")
        time_delta = getattr(corr, "time_delta", "unknown")
        failure = getattr(corr, "failure_description", "")
        evidence.append(
            f"Change: {change_type} on {resource} "
            f"(delta={time_delta}) correlated with: {failure[:80]}"
        )
        resources.append(str(resource))

    return build_hypothesis(
        title="Recent Change Correlated with Failures",
        description=(
            "The change correlator detected a strong correlation between "
            "recent configuration or deployment changes and the observed "
            "failures. The timing suggests the change may be the root cause."
        ),
        category="change_management",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Roll back the recent change to verify it's the cause",
            "Review the diff of the correlated change for obvious issues",
            "Check if the change was tested in a staging environment first",
        ],
    )


# ── Rule: Resource Overcommit ────────────────────────────────────────────


def _match_resource_overcommit(triage: TriageResult) -> list[list[Any]]:
    """Find node resource overcommitment issues."""
    if not triage.resource_issues:
        return []

    overcommit = [
        r for r in triage.resource_issues
        if r.issue in ("overcommitted_node", "exceeds_node")
    ]

    if not overcommit:
        return []

    # Cross-reference with OOM or evicted pods for stronger signal
    oom_evicted = [
        p for p in all_pods(triage)
        if p.issue_type in ("OOMKilled", "Evicted")
    ]

    return [[overcommit, oom_evicted]]


def _hyp_resource_overcommit(groups: list[list[Any]]) -> dict[str, Any]:
    overcommit = groups[0][0]
    oom_evicted = groups[0][1]

    evidence = [
        f"{r.namespace}/{r.pod_name}/{r.container_name}: "
        f"{r.issue} ({r.resource_type}) — {r.message[:100]}"
        for r in overcommit[:5]
    ]
    evidence += [
        f"Pod {p.namespace}/{p.pod_name}: {p.issue_type}"
        for p in oom_evicted[:3]
    ]

    resources = [f"{r.namespace}/{r.pod_name}" for r in overcommit]
    resources += [f"{p.namespace}/{p.pod_name}" for p in oom_evicted]

    return build_hypothesis(
        title="Node Resource Overcommitment",
        description=(
            "Node resources are overcommitted — the sum of pod resource "
            "requests exceeds node capacity. This leads to OOM kills, "
            "evictions, and scheduling failures under load."
        ),
        category="resource_exhaustion",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Set appropriate resource requests and limits on all containers",
            "Use LimitRanges to enforce default resource constraints",
            "Rebalance workloads across nodes or add more nodes",
            "Consider using pod priority and preemption for critical workloads",
        ],
    )


# ── Rule: DNS + NetworkPolicy Lockout ────────────────────────────────────


def _match_dns_netpol_lockout(triage: TriageResult) -> list[list[Any]]:
    """Find DNS blocked by NetworkPolicy — requires 3-way correlation."""
    # Signal 1: deny_all_egress network policies
    deny_egress = [
        np for np in triage.network_policy_issues
        if np.issue_type == "deny_all_egress"
    ]
    if not deny_egress:
        return []

    # Get namespaces with deny-all egress
    deny_namespaces = {np.namespace for np in deny_egress}

    # Signal 2: DNS issues in same namespace
    dns_in_ns = [
        d for d in triage.dns_issues
        if d.namespace in deny_namespaces
    ]
    if not dns_in_ns:
        return []

    # Signal 3: log_intelligence confirms DNS failures in same namespace
    log_dns_failures: list[tuple[str, Any]] = []
    for ns in deny_namespaces:
        for key, pod_intel in log_intel_pods(triage, ns):
            containers = getattr(pod_intel, "containers", [])
            for container in containers:
                if getattr(container, "has_dns_failures", False):
                    log_dns_failures.append((key, pod_intel))
                    break

    if not log_dns_failures:
        return []

    # All 3 signals present — high confidence
    return [[deny_egress, dns_in_ns, log_dns_failures]]


def _hyp_dns_netpol_lockout(groups: list[list[Any]]) -> dict[str, Any]:
    deny_policies = groups[0][0]
    dns_issues = groups[0][1]
    log_failures = groups[0][2]

    evidence = [
        f"NetworkPolicy: {np.namespace}/{np.policy_name} — {np.issue_type}"
        for np in deny_policies
    ]
    evidence += [
        f"DNS issue: {d.namespace}/{d.resource_name} — {d.message[:100]}"
        for d in dns_issues[:3]
    ]
    evidence += [
        f"Log confirmed DNS failure: {key}"
        for key, _ in log_failures[:3]
    ]

    resources = [f"{np.namespace}/{np.policy_name}" for np in deny_policies]
    resources += [key for key, _ in log_failures]

    return build_hypothesis(
        title="NetworkPolicy Blocking DNS Resolution",
        description=(
            "A deny-all egress NetworkPolicy is blocking DNS resolution by "
            "preventing pods from reaching CoreDNS on port 53. This causes "
            "all service discovery to fail, leading to connection errors."
        ),
        category="dns",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Add an egress rule allowing DNS traffic to kube-system on port 53 (TCP and UDP)",
            "Example: allow egress to kube-dns pods on port 53 in the NetworkPolicy",
            "Consider using a more granular egress policy instead of deny-all",
        ],
    )


# ── Exported rules ──────────────────────────────────────────────────────

CONNECTION_POOL_EXHAUSTION_RULE = RCARule(
    name="connection_pool_exhaustion",
    match=_match_connection_pool,
    hypothesis_template=_hyp_connection_pool,
)
BROKEN_DEPENDENCY_RULE = RCARule(
    name="broken_dependency",
    match=_match_broken_dependency,
    hypothesis_template=_hyp_broken_dependency,
)
CHANGE_CORRELATED_FAILURE_RULE = RCARule(
    name="change_correlated_failure",
    match=_match_change_correlation,
    hypothesis_template=_hyp_change_correlation,
)
RESOURCE_OVERCOMMIT_RULE = RCARule(
    name="resource_overcommit",
    match=_match_resource_overcommit,
    hypothesis_template=_hyp_resource_overcommit,
)
DNS_NETPOL_LOCKOUT_RULE = RCARule(
    name="dns_netpol_lockout",
    match=_match_dns_netpol_lockout,
    hypothesis_template=_hyp_dns_netpol_lockout,
)
