"""RCA rules for probe failures, crash patterns, event escalations, and silence signals.

Rules: readiness_probe_flapping, crash_pattern, event_escalation, silence_signal.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models.log_intelligence import CrashLoopContext
from bundle_analyzer.models.triage import EventEscalation, ProbeIssue, SilenceSignal
from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import RCARule, all_pods, build_hypothesis


# ── Rule: Readiness Probe Flapping ───────────────────────────────────────


def _match_readiness_flapping(triage: TriageResult) -> list[list[Any]]:
    """Find readiness probe failures causing endpoint flapping."""
    readiness_probes = [
        p for p in triage.probe_issues
        if p.probe_type == "readiness"
    ]

    partial_ready = [
        d for d in triage.deployment_issues
        if 0 < d.ready_replicas < d.desired_replicas
    ]

    readiness_events = [
        e for e in triage.warning_events
        if e.reason == "Unhealthy" and "readiness" in e.message.lower()
    ]

    readiness_escalations = [
        esc for esc in triage.event_escalations
        if "Unhealthy" in esc.event_reasons
    ]

    if not readiness_probes:
        return []

    if not partial_ready and not readiness_events and not readiness_escalations:
        return []

    return [[readiness_probes, partial_ready, readiness_events, readiness_escalations]]


def _hyp_readiness_flapping(groups: list[list[Any]]) -> dict[str, Any]:
    probes: list[ProbeIssue] = groups[0][0]
    partial: list = groups[0][1]
    events: list = groups[0][2]
    escalations: list = groups[0][3]

    evidence = [
        f"Probe issue: {p.namespace}/{p.pod_name}/{p.container_name} "
        f"— {p.probe_type} {p.issue} — {p.message[:100]}"
        for p in probes[:5]
    ]
    evidence += [
        f"Deployment {d.namespace}/{d.name}: {d.ready_replicas}/{d.desired_replicas} ready (partial)"
        for d in partial[:3]
    ]
    evidence += [
        f"Event: {e.namespace}/{e.involved_object_name} — {e.message[:100]}"
        for e in events[:3]
    ]
    evidence += [
        f"Escalation: {esc.namespace}/{esc.involved_object_name} — {esc.message[:80]}"
        for esc in escalations[:2]
    ]

    resources = [f"{p.namespace}/{p.pod_name}" for p in probes]
    resources += [f"{d.namespace}/{d.name}" for d in partial]

    return build_hypothesis(
        title="Readiness Probe Failures Causing Endpoint Flapping",
        description=(
            "Readiness probe failures are causing pods to be repeatedly removed "
            "from and added back to service endpoints. This creates intermittent "
            "connectivity issues for clients of the service."
        ),
        category="probe_failure",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Fix the readiness probe endpoint to return healthy status",
            "Increase failureThreshold to tolerate transient failures",
            "Add a startup probe to avoid premature readiness checks",
            "Check if the application needs more time to warm up",
        ],
    )


# ── Rule: Crash Pattern ─────────────────────────────────────────────────

_ALWAYS_SIGNIFICANT = {"panic", "segfault"}
_CATEGORY_MAP = {
    "panic": "application_error",
    "segfault": "application_error",
    "config_error": "config_error",
    "dependency_timeout": "dependency_failure",
    "oom": "resource_exhaustion",
}
_FIX_MAP = {
    "panic": [
        "Check the stack trace in container logs for the panic source",
        "Look for nil pointer dereferences or index out of range errors",
        "Review recent code changes that may have introduced the panic",
    ],
    "segfault": [
        "Check for memory corruption or buffer overflow issues",
        "Verify native library compatibility with the container base image",
        "Run the application with address sanitizer for detailed diagnostics",
    ],
    "config_error": [
        "Verify environment variables and ConfigMap values are correct",
        "Check that configuration file paths are properly mounted",
        "Validate configuration file syntax and required fields",
    ],
    "dependency_timeout": [
        "Check upstream service health and connectivity",
        "Increase connection timeout settings if appropriate",
        "Add circuit breaker or retry logic to handle transient failures",
    ],
    "oom": [
        "Increase container memory limits",
        "Profile application memory usage to find leaks",
        "Check for unbounded caches or data structures",
    ],
}


def _match_crash_pattern(triage: TriageResult) -> list[list[Any]]:
    """Group crash contexts by pattern and return significant groups."""
    if not triage.crash_contexts:
        return []

    by_pattern: dict[str, list[CrashLoopContext]] = {}
    for ctx in triage.crash_contexts:
        pattern = ctx.crash_pattern
        if not pattern or pattern == "unknown":
            continue
        by_pattern.setdefault(pattern, []).append(ctx)

    results: list[list[Any]] = []
    for pattern, contexts in by_pattern.items():
        if len(contexts) >= 2 or pattern in _ALWAYS_SIGNIFICANT:
            results.append([pattern, contexts])

    return results


def _hyp_crash_pattern(groups: list[list[Any]]) -> dict[str, Any]:
    # May have multiple groups (patterns); use the first/most significant
    pattern: str = groups[0][0]
    contexts: list[CrashLoopContext] = groups[0][1]

    title = f"Application {pattern.replace('_', ' ').title()} Causing Crash Loops"
    category = _CATEGORY_MAP.get(pattern, "application_error")
    fixes = _FIX_MAP.get(pattern, [
        "Check container logs for the crash cause",
        "Review recent deployment changes",
    ])

    evidence = []
    for ctx in contexts[:5]:
        line = f"{ctx.namespace}/{ctx.pod_name}/{ctx.container_name}: "
        line += f"pattern={ctx.crash_pattern}"
        if ctx.exit_code is not None:
            line += f" exit_code={ctx.exit_code}"
        if ctx.last_log_lines:
            last = ctx.last_log_lines[-1][:80]
            line += f" last_log='{last}'"
        evidence.append(line)

    resources = [f"{ctx.namespace}/{ctx.pod_name}" for ctx in contexts]

    return build_hypothesis(
        title=title,
        description=(
            f"Multiple containers are crash-looping with a '{pattern}' pattern. "
            f"This indicates a systematic {category.replace('_', ' ')} issue "
            f"affecting {len(contexts)} container(s)."
        ),
        category=category,
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=fixes,
    )


# ── Rule: Event Escalation ──────────────────────────────────────────────


def _match_event_escalation(triage: TriageResult) -> list[list[Any]]:
    """Find cascading or high-count event escalations."""
    if not triage.event_escalations:
        return []

    significant: list[EventEscalation] = [
        esc for esc in triage.event_escalations
        if esc.escalation_type == "cascading" or esc.total_count > 50
    ]

    if not significant:
        return []

    # Cross-reference with failing pods
    failing_pods = {
        f"{p.namespace}/{p.pod_name}"
        for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending", "Evicted")
    }

    correlated = [
        esc for esc in significant
        if f"{esc.namespace}/{esc.involved_object_name}" in failing_pods
    ]

    # Fire if cascading escalations OR correlated with failures
    hits = correlated if correlated else significant
    return [[hits]]


def _hyp_event_escalation(groups: list[list[Any]]) -> dict[str, Any]:
    escalations: list[EventEscalation] = groups[0][0]

    evidence = []
    for esc in escalations[:5]:
        line = (
            f"{esc.namespace}/{esc.involved_object_name}: "
            f"type={esc.escalation_type} count={esc.total_count} "
            f"reasons={','.join(esc.event_reasons[:3])}"
        )
        if esc.first_seen and esc.last_seen:
            line += f" span={esc.first_seen.isoformat()}->{esc.last_seen.isoformat()}"
        evidence.append(line)

    resources = [f"{esc.namespace}/{esc.involved_object_name}" for esc in escalations]

    return build_hypothesis(
        title="Escalating Event Pattern Indicating Worsening Failure",
        description=(
            "A pattern of escalating Kubernetes events indicates an ongoing or "
            "worsening failure. Cascading events suggest the problem is spreading "
            "to dependent resources."
        ),
        category="escalation",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Address the root event reason — fix the first failure in the chain",
            "Check pod restart policies and backoff behavior",
            "Look for cascading dependencies that amplify the failure",
        ],
    )


# ── Rule: Silence Signal ────────────────────────────────────────────────


def _match_silence_signals(triage: TriageResult) -> list[list[Any]]:
    """Find critical silence signals co-occurring with pod failures."""
    if not triage.silence_signals:
        return []

    critical_silences: list[SilenceSignal] = [
        s for s in triage.silence_signals
        if s.signal_type in ("EMPTY_LOG_RUNNING_POD", "LOG_FILE_MISSING")
        and s.severity == "critical"
    ]

    if not critical_silences:
        return []

    # Cross-reference with failing pods — only fire when silence + failure
    failing_pods = {
        (p.namespace, p.pod_name)
        for p in all_pods(triage)
        if p.issue_type in ("CrashLoopBackOff", "Pending", "Evicted", "OOMKilled")
    }

    correlated = [
        s for s in critical_silences
        if (s.namespace, s.pod_name) in failing_pods
    ]

    if not correlated:
        return []

    return [[correlated]]


def _hyp_silence_signals(groups: list[list[Any]]) -> dict[str, Any]:
    silences: list[SilenceSignal] = groups[0][0]

    evidence = [
        f"{s.namespace}/{s.pod_name}: {s.signal_type} — {s.note[:100]}"
        for s in silences[:5]
    ]

    resources = [f"{s.namespace}/{s.pod_name}" for s in silences]

    return build_hypothesis(
        title="Missing Log Data May Be Hiding Root Cause",
        description=(
            "Critical log data is missing from pods that are also failing. "
            "Without logs, the true root cause may be invisible. The absence "
            "of data is itself a diagnostic signal."
        ),
        category="observability_gap",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Check container logging configuration and log driver settings",
            "Verify log volume mounts are correctly configured",
            "Check if the container lifespan is too short to write logs",
            "Look for stdout/stderr redirection issues in the container entrypoint",
        ],
    )


# ── Exported rules ──────────────────────────────────────────────────────

READINESS_PROBE_FLAPPING_RULE = RCARule(
    name="readiness_probe_flapping",
    match=_match_readiness_flapping,
    hypothesis_template=_hyp_readiness_flapping,
)
CRASH_PATTERN_RULE = RCARule(
    name="crash_pattern",
    match=_match_crash_pattern,
    hypothesis_template=_hyp_crash_pattern,
)
EVENT_ESCALATION_RULE = RCARule(
    name="event_escalation",
    match=_match_event_escalation,
    hypothesis_template=_hyp_event_escalation,
)
SILENCE_SIGNAL_RULE = RCARule(
    name="silence_signal",
    match=_match_silence_signals,
    hypothesis_template=_hyp_silence_signals,
)
