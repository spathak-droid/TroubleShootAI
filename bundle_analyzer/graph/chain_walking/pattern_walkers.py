"""Pattern walker functions for specific pod issue types.

Each function implements a deterministic reasoning pattern for a specific
Kubernetes failure mode (CrashLoopBackOff, Pending, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bundle_analyzer.models import CausalStep, PodIssue, TriageResult

from .data_access import (
    check_config_issues,
    check_liveness_probe,
    check_node_memory_pressure,
    extract_exit_code,
    get_log_patterns,
    get_restart_policy,
    has_memory_limits,
)

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def walk_crash_loop(
    issue: PodIssue,
    pod_json: dict | None,
    steps: list[CausalStep],
    related: list[str],
    evidence_file: str,
    index: BundleIndex,
    triage: TriageResult,
) -> tuple[str | None, float, bool]:
    """Walk CrashLoopBackOff / OOMKilled pattern.

    Examines exit codes, memory limits, node pressure, liveness probes,
    and log patterns to determine root cause.

    Args:
        issue: The pod issue from triage.
        pod_json: Raw pod JSON dict, or None.
        steps: Mutable list of CausalStep to append to.
        related: Mutable list of related resource keys to append to.
        evidence_file: Path to the evidence file.
        index: The bundle index for reading logs.
        triage: The triage results for checking node issues and config issues.

    Returns:
        Tuple of (root_cause, confidence, needs_ai).
    """
    resource_key = f"Pod/{issue.namespace}/{issue.pod_name}"
    root_cause: str | None = None
    confidence = 0.0
    needs_ai = False

    exit_code = issue.exit_code
    container_name = issue.container_name or ""

    # Try to get exit code from pod JSON if not on the issue
    if exit_code is None and pod_json:
        exit_code = extract_exit_code(pod_json, container_name)

    if exit_code == 137:
        steps.append(CausalStep(
            resource=resource_key,
            observation="Container was OOMKilled (exit code 137)",
            evidence_file=evidence_file,
            evidence_excerpt="exitCode: 137, reason: OOMKilled",
        ))
        # Check memory limits
        has_limits = has_memory_limits(pod_json, container_name)
        if not has_limits:
            steps.append(CausalStep(
                resource=resource_key,
                observation="Container has no memory limits set",
                evidence_file=evidence_file,
                evidence_excerpt="resources.limits.memory: not set",
            ))
            root_cause = f"Pod {issue.pod_name} OOMKilled — no memory limits configured"
            confidence = 0.9
        else:
            # Check node memory pressure
            node_pressure = check_node_memory_pressure(pod_json, triage.node_issues)
            if node_pressure:
                node_name = node_pressure
                steps.append(CausalStep(
                    resource=f"Node/{node_name}",
                    observation="Node is under MemoryPressure",
                    evidence_file="cluster-resources/nodes.json",
                    evidence_excerpt=f"node {node_name}: MemoryPressure=True",
                ))
                related.append(f"Node/{node_name}")
                root_cause = f"Node {node_name} memory pressure caused OOM of pod {issue.pod_name}"
                confidence = 0.8
            else:
                root_cause = f"Pod {issue.pod_name} OOMKilled — memory limit may be too low"
                confidence = 0.7

    elif exit_code == 1:
        steps.append(CausalStep(
            resource=resource_key,
            observation="Container exited with error code 1 (application error)",
            evidence_file=evidence_file,
            evidence_excerpt="exitCode: 1",
        ))
        # Check log patterns
        log_matches = get_log_patterns(
            index, issue.namespace, issue.pod_name, container_name,
        )
        if log_matches:
            for match in log_matches:
                steps.append(CausalStep(
                    resource=resource_key,
                    observation=f"Log pattern detected: {match}",
                    evidence_file=issue.log_path or f"{issue.namespace}/{issue.pod_name}/{container_name}.log",
                    evidence_excerpt=match,
                ))

            if any("file_not_found" in m for m in log_matches):
                root_cause = f"Pod {issue.pod_name} crashing: missing file or config mount"
                confidence = 0.75
            elif any("connection_refused" in m for m in log_matches):
                root_cause = f"Pod {issue.pod_name} crashing: dependency service unreachable"
                confidence = 0.7
            elif any("permission_denied" in m for m in log_matches):
                root_cause = f"Pod {issue.pod_name} crashing: permission/RBAC denied"
                confidence = 0.7
            elif any("out_of_memory" in m for m in log_matches):
                root_cause = f"Pod {issue.pod_name} crashing: application-level OOM"
                confidence = 0.75
            elif any("timeout" in m for m in log_matches):
                root_cause = f"Pod {issue.pod_name} crashing: timeout/deadline exceeded"
                confidence = 0.6
            else:
                root_cause = f"Pod {issue.pod_name} crashing: {log_matches[0]}"
                confidence = 0.55
        else:
            root_cause = f"Pod {issue.pod_name} application error (exit code 1)"
            confidence = 0.3
            needs_ai = True

    elif exit_code == 0:
        steps.append(CausalStep(
            resource=resource_key,
            observation="Container exited cleanly (exit code 0) but is being restarted",
            evidence_file=evidence_file,
            evidence_excerpt="exitCode: 0, reason: Completed",
        ))
        # Check liveness probe
        probe_info = check_liveness_probe(pod_json, container_name)
        if probe_info:
            steps.append(CausalStep(
                resource=resource_key,
                observation=f"Liveness probe configured: {probe_info}",
                evidence_file=evidence_file,
                evidence_excerpt=probe_info,
            ))
            root_cause = f"Pod {issue.pod_name} killed by liveness probe (exits cleanly, gets restarted)"
            confidence = 0.8
        else:
            # Check restartPolicy
            restart_policy = get_restart_policy(pod_json)
            if restart_policy == "Always":
                steps.append(CausalStep(
                    resource=resource_key,
                    observation="restartPolicy is Always — container exits cleanly but gets restarted",
                    evidence_file=evidence_file,
                    evidence_excerpt="restartPolicy: Always",
                ))
                root_cause = (
                    f"Pod {issue.pod_name} container exits cleanly but restartPolicy=Always "
                    "causes restart loop"
                )
                confidence = 0.7
            else:
                root_cause = f"Pod {issue.pod_name} exiting cleanly with restarts"
                confidence = 0.4
                needs_ai = True
    else:
        # Unknown exit code
        exit_desc = f"exit code {exit_code}" if exit_code is not None else "unknown exit code"
        steps.append(CausalStep(
            resource=resource_key,
            observation=f"Container terminated with {exit_desc}",
            evidence_file=evidence_file,
            evidence_excerpt=f"exitCode: {exit_code}",
        ))
        root_cause = f"Pod {issue.pod_name} crashing with {exit_desc}"
        confidence = 0.3
        needs_ai = True

    # Check for missing ConfigMaps/Secrets (Pattern 5)
    config_issues = check_config_issues(triage, issue.namespace, issue.pod_name)
    if config_issues:
        for ci in config_issues:
            steps.append(CausalStep(
                resource=resource_key,
                observation=f"Missing {ci.resource_type} '{ci.resource_name}'",
                evidence_file=evidence_file,
                evidence_excerpt=f"referenced_by: {ci.referenced_by}, issue: {ci.issue}",
            ))
            related.append(f"{ci.resource_type}/{ci.namespace}/{ci.resource_name}")
        if root_cause is None or confidence < 0.6:
            root_cause = (
                f"Missing {config_issues[0].resource_type} "
                f"'{config_issues[0].resource_name}' causes pod failure"
            )
            confidence = max(confidence, 0.8)

    return root_cause, confidence, needs_ai


def walk_pending(
    issue: PodIssue,
    pod_json: dict | None,
    steps: list[CausalStep],
    related: list[str],
    evidence_file: str,
    triage: TriageResult,
) -> tuple[str | None, float]:
    """Walk Pending pod pattern.

    Checks scheduling conditions, resource requests, unschedulable nodes,
    node selectors, and taints/tolerations.

    Args:
        issue: The pod issue from triage.
        pod_json: Raw pod JSON dict, or None.
        steps: Mutable list of CausalStep to append to.
        related: Mutable list of related resource keys to append to.
        evidence_file: Path to the evidence file.
        triage: The triage results for checking node issues.

    Returns:
        Tuple of (root_cause, confidence).
    """
    resource_key = f"Pod/{issue.namespace}/{issue.pod_name}"

    # Check conditions for scheduling failure message
    if pod_json:
        conditions = pod_json.get("status", {}).get("conditions", [])
        for cond in conditions:
            if cond.get("type") == "PodScheduled" and cond.get("status") == "False":
                msg = cond.get("message", "")
                steps.append(CausalStep(
                    resource=resource_key,
                    observation=f"Scheduling failed: {msg}",
                    evidence_file=evidence_file,
                    evidence_excerpt=f"PodScheduled: False, message: {msg}",
                ))
                if "Insufficient" in msg:
                    return f"Pod {issue.pod_name} pending: insufficient cluster resources — {msg}", 0.85
                if "node(s) were unschedulable" in msg.lower():
                    return f"Pod {issue.pod_name} pending: all nodes unschedulable", 0.85
                if "didn't match" in msg.lower() or "selector" in msg.lower():
                    return f"Pod {issue.pod_name} pending: node selector/affinity mismatch", 0.8
                if "taint" in msg.lower() or "toleration" in msg.lower():
                    return f"Pod {issue.pod_name} pending: untolerated taint", 0.8
                return f"Pod {issue.pod_name} pending: {msg}", 0.7

    # Check for unschedulable nodes
    for ni in triage.node_issues:
        if ni.condition == "Unschedulable":
            steps.append(CausalStep(
                resource=f"Node/{ni.node_name}",
                observation="Node is unschedulable (cordoned)",
                evidence_file="cluster-resources/nodes.json",
                evidence_excerpt=f"node {ni.node_name}: Unschedulable",
            ))
            related.append(f"Node/{ni.node_name}")

    if issue.message:
        return f"Pod {issue.pod_name} pending: {issue.message}", 0.6
    return f"Pod {issue.pod_name} pending (reason unknown)", 0.3
