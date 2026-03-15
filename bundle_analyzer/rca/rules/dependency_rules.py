"""RCA rules for dependency failures, connectivity, and configuration issues.

Rules: dependency_connection_refused, empty_endpoints, dns_cascade,
       tls_blocking, network_isolation, config_drift_restart.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models.triage import ConfigIssue, PodIssue
from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import RCARule, all_pods, build_hypothesis


# ── Rule 2: CrashLoopBackOff + connection refused -> Dependency ───────────

def _match_dependency_refused(triage: TriageResult) -> list[list[Any]]:
    """Find pods crash-looping with connection refused errors."""
    hits = [
        p for p in all_pods(triage)
        if p.issue_type == "CrashLoopBackOff"
        and p.exit_code == 1
        and "connection refused" in (p.message or "").lower()
    ]
    return [hits] if hits else []


def _hyp_dependency_refused(groups: list[list[Any]]) -> dict[str, Any]:
    pods: list[PodIssue] = groups[0]
    return build_hypothesis(
        title="Dependency Service Unavailable",
        description=(
            "Containers are crash-looping because a required dependency is "
            "refusing connections. The upstream service may be down, not yet "
            "started, or misconfigured."
        ),
        category="dependency_failure",
        supporting_evidence=[
            f"{p.namespace}/{p.pod_name}: CrashLoopBackOff exit 1 — "
            f"'{p.message}'"
            for p in pods
        ],
        affected_resources=[f"{p.namespace}/{p.pod_name}" for p in pods],
        suggested_fixes=[
            "Check that the upstream service/database is running and healthy",
            "Verify connection string / service DNS name is correct",
            "Add init containers or readiness gates to wait for dependencies",
        ],
    )


# ── Rule 7: Pod failing + empty endpoints -> Dep Down ────────────────────

def _match_empty_endpoints(triage: TriageResult) -> list[list[Any]]:
    """Find pods failing alongside services with no ready endpoints."""
    down_deployments: set[str] = set()
    for dep in triage.deployment_issues:
        if dep.ready_replicas == 0:
            down_deployments.add(f"{dep.namespace}/{dep.name}")

    if not down_deployments:
        return []

    failing_pods = [
        p for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending")
        and p.message
    ]

    if not failing_pods:
        return []

    return [[failing_pods, list(down_deployments)]]


def _hyp_empty_endpoints(groups: list[list[Any]]) -> dict[str, Any]:
    pods = groups[0][0]
    down_deps = groups[0][1]
    return build_hypothesis(
        title="Dependency Deployment Has Zero Ready Endpoints",
        description=(
            "One or more deployments have zero ready replicas, meaning any "
            "service pointing to them will have empty endpoints. Pods "
            "depending on these services will fail with connection errors."
        ),
        category="dependency_failure",
        supporting_evidence=[
            f"Deployment {d} has 0 ready replicas" for d in down_deps
        ] + [
            f"{p.namespace}/{p.pod_name}: {p.issue_type} — {p.message}"
            for p in pods[:5]
        ],
        affected_resources=down_deps + [f"{p.namespace}/{p.pod_name}" for p in pods],
        suggested_fixes=[
            "Investigate why the upstream deployment has zero ready pods",
            "Check upstream deployment events and pod logs",
            "Consider adding retry/backoff logic in dependent services",
        ],
    )


# ── Rule 10: DNS cascade ─────────────────────────────────────────────────

def _match_dns_cascade(triage: TriageResult) -> list[list[Any]]:
    """Find DNS failures that could cascade to app pods."""
    from bundle_analyzer.models.triage import DNSIssue
    dns_issues: list[DNSIssue] = getattr(triage, "dns_issues", [])
    if not dns_issues:
        return []
    failing_pods = [
        p for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending")
        and any(kw in (p.message or "").lower() for kw in ("dns", "resolve", "lookup", "connection"))
    ]
    if not failing_pods:
        return [[dns_issues, []]]
    return [[dns_issues, failing_pods]]


def _hyp_dns_cascade(groups: list[list[Any]]) -> dict[str, Any]:
    dns_issues = groups[0][0]
    failing_pods = groups[0][1]
    evidence = [f"DNS issue: {d.resource_name} — {d.message}" for d in dns_issues]
    evidence += [f"{p.namespace}/{p.pod_name}: {p.issue_type} — {p.message}" for p in failing_pods[:5]]
    resources = [f"{d.namespace}/{d.resource_name}" for d in dns_issues]
    resources += [f"{p.namespace}/{p.pod_name}" for p in failing_pods]
    return build_hypothesis(
        title="DNS Resolution Failure Cascade",
        description=(
            "CoreDNS or DNS resolution is failing, which may cascade to "
            "application pods that depend on service discovery."
        ),
        category="dns",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Check CoreDNS pod health and logs",
            "Verify kube-dns service endpoints are populated",
            "Check for DNS policy or NetworkPolicy blocking DNS traffic on port 53",
        ],
    )


# ── Rule 11: TLS blocking ────────────────────────────────────────────────

def _match_tls_blocking(triage: TriageResult) -> list[list[Any]]:
    """Find TLS cert issues that could block connections."""
    from bundle_analyzer.models.triage import TLSIssue
    tls_issues: list[TLSIssue] = getattr(triage, "tls_issues", [])
    if not tls_issues:
        return []
    return [[tls_issues]]


def _hyp_tls_blocking(groups: list[list[Any]]) -> dict[str, Any]:
    tls_issues = groups[0]
    return build_hypothesis(
        title="TLS Certificate Issue Blocking Connections",
        description=(
            "Expired, invalid, or unknown-authority certificates are detected, "
            "which can block HTTPS connections and cause cascading failures."
        ),
        category="tls",
        supporting_evidence=[
            f"{t.namespace}/{t.resource_name}: {t.issue_type} — {t.message}"
            for t in tls_issues
        ],
        affected_resources=[f"{t.namespace}/{t.resource_name}" for t in tls_issues],
        suggested_fixes=[
            "Renew expired certificates",
            "Check cert-manager status and issuer configuration",
            "Verify CA trust chain is properly configured",
        ],
    )


# ── Rule 14: Network policy isolation ─────────────────────────────────────

def _match_network_isolation(triage: TriageResult) -> list[list[Any]]:
    """Find network policies that may be isolating pods."""
    from bundle_analyzer.models.triage import NetworkPolicyIssue
    np_issues: list[NetworkPolicyIssue] = getattr(triage, "network_policy_issues", [])
    deny_all = [np for np in np_issues if np.issue_type in ("deny_all_ingress", "deny_all_egress")]
    if not deny_all:
        return []
    connection_errors = [
        p for p in all_pods(triage)
        if p.issue_type == "CrashLoopBackOff"
        and any(kw in (p.message or "").lower() for kw in ("connection refused", "timeout", "unreachable"))
    ]
    return [[deny_all, connection_errors]]


def _hyp_network_isolation(groups: list[list[Any]]) -> dict[str, Any]:
    np_issues = groups[0][0]
    conn_pods = groups[0][1]
    evidence = [f"NetworkPolicy: {n.namespace}/{n.policy_name} — {n.issue_type}" for n in np_issues]
    evidence += [f"{p.namespace}/{p.pod_name}: {p.message}" for p in conn_pods[:5]]
    resources = [f"{n.namespace}/{n.policy_name}" for n in np_issues]
    resources += [f"{p.namespace}/{p.pod_name}" for p in conn_pods]
    return build_hypothesis(
        title="Network Policy May Be Isolating Pods",
        description=(
            "Deny-all network policies detected that may be blocking legitimate "
            "traffic and causing connection failures."
        ),
        category="dependency_failure",
        supporting_evidence=evidence,
        affected_resources=resources,
        suggested_fixes=[
            "Review deny-all network policies and add appropriate allow rules",
            "Check if pods need ingress/egress rules for their dependencies",
            "Verify DNS traffic (port 53) is allowed through network policies",
        ],
    )


# ── Rule 15: Config drift -> restart loop ─────────────────────────────────

def _match_config_drift_restart(triage: TriageResult) -> list[list[Any]]:
    """Find config issues coinciding with crash loops."""
    config_issues: list[ConfigIssue] = getattr(triage, "config_issues", [])
    if not config_issues:
        return []
    config_pods = {c.referenced_by for c in config_issues}
    crashing = [
        p for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "CreateContainerConfigError")
        and p.pod_name in config_pods
    ]
    if not crashing:
        return []
    return [[config_issues, crashing]]


def _hyp_config_drift_restart(groups: list[list[Any]]) -> dict[str, Any]:
    config_issues = groups[0][0]
    crashing_pods = groups[0][1]
    evidence = [
        f"Missing {c.resource_type}: {c.namespace}/{c.resource_name} "
        f"(referenced by {c.referenced_by})"
        for c in config_issues
    ]
    evidence += [
        f"{p.namespace}/{p.pod_name}: {p.issue_type} — {p.message}"
        for p in crashing_pods[:5]
    ]
    resources = [f"{c.namespace}/{c.referenced_by}" for c in config_issues]
    resources += [f"{p.namespace}/{p.pod_name}" for p in crashing_pods]
    return build_hypothesis(
        title="Missing Configuration Causing Container Failures",
        description=(
            "Pods are crash-looping or failing to start because referenced "
            "ConfigMaps or Secrets are missing. This often happens after "
            "config drift or incomplete deployments."
        ),
        category="config_error",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Create or restore the missing ConfigMap/Secret",
            "Check if the resource was accidentally deleted or not deployed",
            "Verify deployment manifests include all required config resources",
        ],
    )


# ── Exported rules ────────────────────────────────────────────────────────

DEPENDENCY_RULES: list[RCARule] = [
    RCARule(name="dependency_connection_refused", match=_match_dependency_refused, hypothesis_template=_hyp_dependency_refused),
    RCARule(name="empty_endpoints", match=_match_empty_endpoints, hypothesis_template=_hyp_empty_endpoints),
    RCARule(name="dns_cascade", match=_match_dns_cascade, hypothesis_template=_hyp_dns_cascade),
    RCARule(name="tls_blocking", match=_match_tls_blocking, hypothesis_template=_hyp_tls_blocking),
    RCARule(name="network_isolation", match=_match_network_isolation, hypothesis_template=_hyp_network_isolation),
    RCARule(name="config_drift_restart", match=_match_config_drift_restart, hypothesis_template=_hyp_config_drift_restart),
]
