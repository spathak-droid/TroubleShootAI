"""Unit tests for the 12 new RCA advanced rules.

Each rule gets a positive test (match fires), negative test (match doesn't fire),
and a hypothesis output test (correct title, category, non-empty evidence).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from bundle_analyzer.models.log_intelligence import (
    CrashLoopContext,
    LogIntelligence,
    PodLogIntelligence,
)
from bundle_analyzer.models.triage import (
    DeploymentIssue,
    DNSIssue,
    DriftIssue,
    EventEscalation,
    K8sEvent,
    NetworkPolicyIssue,
    PodIssue,
    ProbeIssue,
    ResourceIssue,
    SilenceSignal,
)
from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.admission_rules import (
    FINALIZER_STUCK_RULE,
    PDB_DEADLOCK_RULE,
    WEBHOOK_ADMISSION_FAILURE_RULE,
)
from bundle_analyzer.rca.rules.connection_rules import (
    BROKEN_DEPENDENCY_RULE,
    CHANGE_CORRELATED_FAILURE_RULE,
    CONNECTION_POOL_EXHAUSTION_RULE,
    DNS_NETPOL_LOCKOUT_RULE,
    RESOURCE_OVERCOMMIT_RULE,
)
from bundle_analyzer.rca.rules.probe_event_rules import (
    CRASH_PATTERN_RULE,
    EVENT_ESCALATION_RULE,
    READINESS_PROBE_FLAPPING_RULE,
    SILENCE_SIGNAL_RULE,
)


def _empty_triage(**overrides: Any) -> TriageResult:
    """Build a minimal TriageResult with optional field overrides."""
    return TriageResult(**overrides)


def _make_event(
    namespace: str = "default",
    reason: str = "Warning",
    message: str = "",
    involved_object_name: str = "test-pod",
    involved_object_kind: str = "Pod",
    count: int = 1,
) -> K8sEvent:
    return K8sEvent(
        namespace=namespace,
        name=f"event-{reason.lower()}",
        reason=reason,
        message=message,
        type="Warning",
        involved_object_kind=involved_object_kind,
        involved_object_name=involved_object_name,
        count=count,
    )


def _make_deployment(
    namespace: str = "default",
    name: str = "test-deploy",
    desired: int = 3,
    ready: int = 0,
) -> DeploymentIssue:
    return DeploymentIssue(
        namespace=namespace,
        name=name,
        desired_replicas=desired,
        ready_replicas=ready,
        issue=f"{ready}/{desired} replicas ready",
    )


def _make_pod(
    namespace: str = "default",
    pod_name: str = "test-pod",
    issue_type: str = "CrashLoopBackOff",
    message: str = "",
    exit_code: int | None = None,
) -> PodIssue:
    return PodIssue(
        namespace=namespace,
        pod_name=pod_name,
        issue_type=issue_type,
        message=message,
        exit_code=exit_code,
    )


def _make_pod_log_intel(
    namespace: str = "default",
    pod_name: str = "test-pod",
    has_connection_errors: bool = False,
    has_dns_failures: bool = False,
) -> PodLogIntelligence:
    container = LogIntelligence(
        namespace=namespace,
        pod_name=pod_name,
        container_name="main",
        has_connection_errors=has_connection_errors,
        has_dns_failures=has_dns_failures,
    )
    return PodLogIntelligence(
        namespace=namespace,
        pod_name=pod_name,
        containers=[container],
    )


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK ADMISSION FAILURE
# ═══════════════════════════════════════════════════════════════════════════


class TestWebhookAdmissionFailure:
    def test_match_positive(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(message="failed calling webhook validate.example.com: connection refused"),
            ],
            deployment_issues=[_make_deployment(ready=0)],
        )
        groups = WEBHOOK_ADMISSION_FAILURE_RULE.match(triage)
        assert groups, "Should fire when webhook events + zero-ready deployments"

    def test_match_negative_no_webhook_events(self) -> None:
        triage = _empty_triage(
            warning_events=[_make_event(message="normal event nothing here")],
            deployment_issues=[_make_deployment(ready=0)],
        )
        groups = WEBHOOK_ADMISSION_FAILURE_RULE.match(triage)
        assert not groups, "Should not fire without webhook-related events"

    def test_match_negative_no_zero_ready(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(message="failed calling webhook"),
            ],
            deployment_issues=[_make_deployment(ready=3)],
        )
        groups = WEBHOOK_ADMISSION_FAILURE_RULE.match(triage)
        assert not groups, "Should not fire when all deployments are healthy"

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(message="admission webhook denied the request"),
            ],
            deployment_issues=[_make_deployment(ready=0)],
        )
        groups = WEBHOOK_ADMISSION_FAILURE_RULE.match(triage)
        hyp = WEBHOOK_ADMISSION_FAILURE_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Admission Webhook Blocking Resource Creation"
        assert hyp["category"] == "admission_control"
        assert hyp["supporting_evidence"]

    def test_match_varied_message_formats(self) -> None:
        """Webhook errors appear differently across K8s versions."""
        for msg in [
            "failed calling webhook",
            "admission webhook denied",
            "Internal error occurred: failed calling admission webhook",
            "denied the request: webhook validation failed",
        ]:
            triage = _empty_triage(
                warning_events=[_make_event(message=msg)],
                deployment_issues=[_make_deployment(ready=0)],
            )
            groups = WEBHOOK_ADMISSION_FAILURE_RULE.match(triage)
            assert groups, f"Should match message: {msg}"


# ═══════════════════════════════════════════════════════════════════════════
# PDB DEADLOCK
# ═══════════════════════════════════════════════════════════════════════════


class TestPDBDeadlock:
    def test_match_positive_event_message(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(message="Cannot evict pod due to disruption budget"),
            ],
        )
        groups = PDB_DEADLOCK_RULE.match(triage)
        assert groups

    def test_match_positive_event_reason(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(reason="TooManyRequests", message="eviction blocked"),
            ],
        )
        groups = PDB_DEADLOCK_RULE.match(triage)
        assert groups

    def test_match_negative(self) -> None:
        triage = _empty_triage(
            warning_events=[_make_event(message="normal pod scaling event")],
        )
        groups = PDB_DEADLOCK_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(
                    reason="EvictionBlocked",
                    message="cannot evict pod due to PodDisruptionBudget",
                ),
            ],
        )
        groups = PDB_DEADLOCK_RULE.match(triage)
        hyp = PDB_DEADLOCK_RULE.hypothesis_template(groups)
        assert hyp["title"] == "PodDisruptionBudget Blocking Eviction or Drain"
        assert hyp["category"] == "scheduling"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# FINALIZER STUCK
# ═══════════════════════════════════════════════════════════════════════════


class TestFinalizerStuck:
    def test_match_positive_event(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(message="object has finalizer kubernetes.io/pv-protection, cannot delete"),
            ],
        )
        groups = FINALIZER_STUCK_RULE.match(triage)
        assert groups

    def test_match_positive_terminating_pod(self) -> None:
        triage = _empty_triage(
            critical_pods=[_make_pod(issue_type="Terminating")],
        )
        groups = FINALIZER_STUCK_RULE.match(triage)
        assert groups

    def test_match_positive_drift(self) -> None:
        triage = _empty_triage(
            drift_issues=[
                DriftIssue(
                    resource_type="Namespace",
                    namespace="stuck-ns",
                    name="stuck-ns",
                    field="status.phase",
                    spec_value="Active",
                    status_value="Terminating",
                    description="Namespace stuck in Terminating state with deletionTimestamp set",
                ),
            ],
        )
        groups = FINALIZER_STUCK_RULE.match(triage)
        assert groups

    def test_match_negative(self) -> None:
        triage = _empty_triage()
        groups = FINALIZER_STUCK_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            warning_events=[
                _make_event(reason="FailedDelete", message="unable to delete"),
            ],
        )
        groups = FINALIZER_STUCK_RULE.match(triage)
        hyp = FINALIZER_STUCK_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Resource Stuck in Terminating Due to Stale Finalizer"
        assert hyp["category"] == "config_error"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# READINESS PROBE FLAPPING
# ═══════════════════════════════════════════════════════════════════════════


class TestReadinessProbeFlapping:
    def test_match_positive(self) -> None:
        triage = _empty_triage(
            probe_issues=[
                ProbeIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    probe_type="readiness",
                    issue="bad_path",
                    message="readiness probe failed",
                ),
            ],
            deployment_issues=[_make_deployment(desired=3, ready=1)],
        )
        groups = READINESS_PROBE_FLAPPING_RULE.match(triage)
        assert groups

    def test_match_positive_with_events(self) -> None:
        triage = _empty_triage(
            probe_issues=[
                ProbeIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    probe_type="readiness",
                    issue="bad_path",
                    message="readiness probe failed",
                ),
            ],
            warning_events=[
                _make_event(reason="Unhealthy", message="Readiness probe failed: HTTP 503"),
            ],
        )
        groups = READINESS_PROBE_FLAPPING_RULE.match(triage)
        assert groups

    def test_match_negative_no_probes(self) -> None:
        triage = _empty_triage(
            deployment_issues=[_make_deployment(desired=3, ready=1)],
        )
        groups = READINESS_PROBE_FLAPPING_RULE.match(triage)
        assert not groups

    def test_match_negative_liveness_only(self) -> None:
        triage = _empty_triage(
            probe_issues=[
                ProbeIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    probe_type="liveness",
                    issue="bad_path",
                    message="liveness probe",
                ),
            ],
            deployment_issues=[_make_deployment(desired=3, ready=1)],
        )
        groups = READINESS_PROBE_FLAPPING_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            probe_issues=[
                ProbeIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    probe_type="readiness",
                    issue="bad_path",
                    message="readiness probe failed",
                ),
            ],
            deployment_issues=[_make_deployment(desired=3, ready=1)],
        )
        groups = READINESS_PROBE_FLAPPING_RULE.match(triage)
        hyp = READINESS_PROBE_FLAPPING_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Readiness Probe Failures Causing Endpoint Flapping"
        assert hyp["category"] == "probe_failure"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# CRASH PATTERN
# ═══════════════════════════════════════════════════════════════════════════


class TestCrashPattern:
    def test_match_positive_panic_single(self) -> None:
        """Single panic is always significant."""
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="panic",
                    exit_code=2,
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        assert groups

    def test_match_positive_multiple_same_pattern(self) -> None:
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="config_error",
                ),
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-2",
                    container_name="main",
                    crash_pattern="config_error",
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        assert groups

    def test_match_skips_unknown(self) -> None:
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="unknown",
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        assert not groups

    def test_match_skips_empty_pattern(self) -> None:
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="",
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        assert not groups

    def test_match_single_non_always_significant(self) -> None:
        """Single config_error should not fire (needs 2+)."""
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="config_error",
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        assert not groups

    def test_hypothesis_output_panic(self) -> None:
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="panic",
                    exit_code=2,
                    last_log_lines=["panic: runtime error: index out of range"],
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        hyp = CRASH_PATTERN_RULE.hypothesis_template(groups)
        assert "Panic" in hyp["title"]
        assert hyp["category"] == "application_error"
        assert hyp["supporting_evidence"]

    def test_hypothesis_output_dependency_timeout(self) -> None:
        triage = _empty_triage(
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="dependency_timeout",
                ),
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-2",
                    container_name="main",
                    crash_pattern="dependency_timeout",
                ),
            ],
        )
        groups = CRASH_PATTERN_RULE.match(triage)
        hyp = CRASH_PATTERN_RULE.hypothesis_template(groups)
        assert hyp["category"] == "dependency_failure"


# ═══════════════════════════════════════════════════════════════════════════
# EVENT ESCALATION
# ═══════════════════════════════════════════════════════════════════════════


class TestEventEscalation:
    def _make_escalation(
        self,
        escalation_type: str = "cascading",
        total_count: int = 10,
        namespace: str = "default",
        name: str = "app-1",
    ) -> EventEscalation:
        return EventEscalation(
            namespace=namespace,
            involved_object_kind="Pod",
            involved_object_name=name,
            event_reasons=["BackOff", "Failed", "Unhealthy"],
            total_count=total_count,
            escalation_type=escalation_type,
            message="escalating failure",
        )

    def test_match_positive_cascading(self) -> None:
        triage = _empty_triage(
            event_escalations=[self._make_escalation(escalation_type="cascading")],
        )
        groups = EVENT_ESCALATION_RULE.match(triage)
        assert groups

    def test_match_positive_high_count(self) -> None:
        triage = _empty_triage(
            event_escalations=[self._make_escalation(escalation_type="sustained", total_count=100)],
        )
        groups = EVENT_ESCALATION_RULE.match(triage)
        assert groups

    def test_match_negative_low_count_repeated(self) -> None:
        triage = _empty_triage(
            event_escalations=[self._make_escalation(escalation_type="repeated", total_count=5)],
        )
        groups = EVENT_ESCALATION_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            event_escalations=[self._make_escalation()],
        )
        groups = EVENT_ESCALATION_RULE.match(triage)
        hyp = EVENT_ESCALATION_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Escalating Event Pattern Indicating Worsening Failure"
        assert hyp["category"] == "escalation"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# SILENCE SIGNAL
# ═══════════════════════════════════════════════════════════════════════════


class TestSilenceSignal:
    def test_match_positive(self) -> None:
        triage = _empty_triage(
            silence_signals=[
                SilenceSignal(
                    namespace="default",
                    pod_name="crash-pod",
                    signal_type="EMPTY_LOG_RUNNING_POD",
                    severity="critical",
                    note="Pod running but logs are empty",
                ),
            ],
            critical_pods=[_make_pod(pod_name="crash-pod", issue_type="CrashLoopBackOff")],
        )
        groups = SILENCE_SIGNAL_RULE.match(triage)
        assert groups

    def test_match_negative_no_failure(self) -> None:
        """Silence without failure should NOT fire."""
        triage = _empty_triage(
            silence_signals=[
                SilenceSignal(
                    namespace="default",
                    pod_name="healthy-pod",
                    signal_type="EMPTY_LOG_RUNNING_POD",
                    severity="critical",
                    note="Empty logs",
                ),
            ],
        )
        groups = SILENCE_SIGNAL_RULE.match(triage)
        assert not groups, "Should not fire when silence exists but no pod failure"

    def test_match_negative_warning_severity(self) -> None:
        """Warning-severity silence should not fire."""
        triage = _empty_triage(
            silence_signals=[
                SilenceSignal(
                    namespace="default",
                    pod_name="crash-pod",
                    signal_type="EMPTY_LOG_RUNNING_POD",
                    severity="warning",
                    note="Not critical",
                ),
            ],
            critical_pods=[_make_pod(pod_name="crash-pod")],
        )
        groups = SILENCE_SIGNAL_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            silence_signals=[
                SilenceSignal(
                    namespace="default",
                    pod_name="crash-pod",
                    signal_type="LOG_FILE_MISSING",
                    severity="critical",
                    note="Log file not found",
                ),
            ],
            critical_pods=[_make_pod(pod_name="crash-pod")],
        )
        groups = SILENCE_SIGNAL_RULE.match(triage)
        hyp = SILENCE_SIGNAL_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Missing Log Data May Be Hiding Root Cause"
        assert hyp["category"] == "observability_gap"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# CONNECTION POOL EXHAUSTION
# ═══════════════════════════════════════════════════════════════════════════


class TestConnectionPoolExhaustion:
    def test_match_positive(self) -> None:
        triage = _empty_triage(
            log_intelligence={
                "default/app-1": _make_pod_log_intel(has_connection_errors=True),
            },
            deployment_issues=[_make_deployment(desired=5, ready=2)],
        )
        groups = CONNECTION_POOL_EXHAUSTION_RULE.match(triage)
        assert groups

    def test_match_positive_with_crash(self) -> None:
        triage = _empty_triage(
            log_intelligence={
                "default/app-1": _make_pod_log_intel(has_connection_errors=True),
            },
            crash_contexts=[
                CrashLoopContext(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    crash_pattern="dependency_timeout",
                ),
            ],
        )
        groups = CONNECTION_POOL_EXHAUSTION_RULE.match(triage)
        assert groups

    def test_match_negative_no_conn_errors(self) -> None:
        triage = _empty_triage(
            log_intelligence={
                "default/app-1": _make_pod_log_intel(has_connection_errors=False),
            },
            deployment_issues=[_make_deployment(desired=5, ready=2)],
        )
        groups = CONNECTION_POOL_EXHAUSTION_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            log_intelligence={
                "default/app-1": _make_pod_log_intel(has_connection_errors=True),
            },
            deployment_issues=[_make_deployment(desired=5, ready=2)],
        )
        groups = CONNECTION_POOL_EXHAUSTION_RULE.match(triage)
        hyp = CONNECTION_POOL_EXHAUSTION_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Database Connection Pool Exhaustion"
        assert hyp["category"] == "dependency_failure"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# BROKEN DEPENDENCY
# ═══════════════════════════════════════════════════════════════════════════


class TestBrokenDependency:
    def test_match_positive(self) -> None:
        dep_map = MagicMock()
        dep_map.broken_dependencies = [
            MagicMock(source="default/app-1", target="default/db-svc", discovery_method="env", health_detail="connection refused"),
        ]
        triage = _empty_triage(dependency_map=dep_map)
        groups = BROKEN_DEPENDENCY_RULE.match(triage)
        assert groups

    def test_match_negative_no_map(self) -> None:
        triage = _empty_triage(dependency_map=None)
        groups = BROKEN_DEPENDENCY_RULE.match(triage)
        assert not groups

    def test_match_negative_no_broken(self) -> None:
        dep_map = MagicMock()
        dep_map.broken_dependencies = []
        triage = _empty_triage(dependency_map=dep_map)
        groups = BROKEN_DEPENDENCY_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        dep_map = MagicMock()
        dep_map.broken_dependencies = [
            MagicMock(source="default/app-1", target="default/db-svc", discovery_method="env", health_detail="refused"),
        ]
        triage = _empty_triage(dependency_map=dep_map)
        groups = BROKEN_DEPENDENCY_RULE.match(triage)
        hyp = BROKEN_DEPENDENCY_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Broken Service Dependency Detected"
        assert hyp["category"] == "dependency_failure"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE CORRELATED FAILURE
# ═══════════════════════════════════════════════════════════════════════════


class TestChangeCorrelatedFailure:
    def test_match_positive(self) -> None:
        report = MagicMock()
        report.correlations = [
            MagicMock(
                correlation_strength="strong",
                change_type="image_update",
                resource="default/app",
                time_delta="2m",
                failure_description="CrashLoopBackOff",
            ),
        ]
        triage = _empty_triage(change_report=report)
        groups = CHANGE_CORRELATED_FAILURE_RULE.match(triage)
        assert groups

    def test_match_negative_weak_correlation(self) -> None:
        report = MagicMock()
        report.correlations = [
            MagicMock(correlation_strength="weak"),
        ]
        triage = _empty_triage(change_report=report)
        groups = CHANGE_CORRELATED_FAILURE_RULE.match(triage)
        assert not groups

    def test_match_negative_no_report(self) -> None:
        triage = _empty_triage(change_report=None)
        groups = CHANGE_CORRELATED_FAILURE_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        report = MagicMock()
        report.correlations = [
            MagicMock(
                correlation_strength="strong",
                change_type="image_update",
                resource="default/app",
                time_delta="2m",
                failure_description="CrashLoopBackOff",
            ),
        ]
        triage = _empty_triage(change_report=report)
        groups = CHANGE_CORRELATED_FAILURE_RULE.match(triage)
        hyp = CHANGE_CORRELATED_FAILURE_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Recent Change Correlated with Failures"
        assert hyp["category"] == "change_management"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# RESOURCE OVERCOMMIT
# ═══════════════════════════════════════════════════════════════════════════


class TestResourceOvercommit:
    def test_match_positive(self) -> None:
        triage = _empty_triage(
            resource_issues=[
                ResourceIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    issue="overcommitted_node",
                    message="Node overcommitted",
                    resource_type="memory",
                ),
            ],
        )
        groups = RESOURCE_OVERCOMMIT_RULE.match(triage)
        assert groups

    def test_match_negative_no_overcommit(self) -> None:
        triage = _empty_triage(
            resource_issues=[
                ResourceIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    issue="no_limits",
                    message="No limits set",
                    resource_type="memory",
                ),
            ],
        )
        groups = RESOURCE_OVERCOMMIT_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = _empty_triage(
            resource_issues=[
                ResourceIssue(
                    namespace="default",
                    pod_name="app-1",
                    container_name="main",
                    issue="exceeds_node",
                    message="Exceeds node capacity",
                    resource_type="cpu",
                ),
            ],
        )
        groups = RESOURCE_OVERCOMMIT_RULE.match(triage)
        hyp = RESOURCE_OVERCOMMIT_RULE.hypothesis_template(groups)
        assert hyp["title"] == "Node Resource Overcommitment"
        assert hyp["category"] == "resource_exhaustion"
        assert hyp["supporting_evidence"]


# ═══════════════════════════════════════════════════════════════════════════
# DNS + NETPOL LOCKOUT (3-way correlation)
# ═══════════════════════════════════════════════════════════════════════════


class TestDnsNetpolLockout:
    def _full_triage(self) -> TriageResult:
        """Build triage with all 3 signals."""
        return _empty_triage(
            network_policy_issues=[
                NetworkPolicyIssue(
                    namespace="secure-ns",
                    policy_name="deny-all",
                    issue_type="deny_all_egress",
                    message="Deny all egress",
                ),
            ],
            dns_issues=[
                DNSIssue(
                    namespace="secure-ns",
                    resource_name="app-pod",
                    issue_type="dns_resolution_error",
                    message="DNS lookup failed",
                ),
            ],
            log_intelligence={
                "secure-ns/app-pod": _make_pod_log_intel(
                    namespace="secure-ns",
                    pod_name="app-pod",
                    has_dns_failures=True,
                ),
            },
        )

    def test_match_positive_all_3_signals(self) -> None:
        triage = self._full_triage()
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        assert groups

    def test_match_negative_missing_netpol(self) -> None:
        triage = _empty_triage(
            dns_issues=[
                DNSIssue(
                    namespace="secure-ns",
                    resource_name="app",
                    issue_type="dns_resolution_error",
                    message="DNS failed",
                ),
            ],
            log_intelligence={
                "secure-ns/app": _make_pod_log_intel(
                    namespace="secure-ns", has_dns_failures=True,
                ),
            },
        )
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        assert not groups, "Should not fire without deny-all egress policy"

    def test_match_negative_missing_dns(self) -> None:
        triage = _empty_triage(
            network_policy_issues=[
                NetworkPolicyIssue(
                    namespace="secure-ns",
                    policy_name="deny-all",
                    issue_type="deny_all_egress",
                    message="Deny all",
                ),
            ],
            log_intelligence={
                "secure-ns/app": _make_pod_log_intel(
                    namespace="secure-ns", has_dns_failures=True,
                ),
            },
        )
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        assert not groups, "Should not fire without DNS issues"

    def test_match_negative_missing_log_intel(self) -> None:
        triage = _empty_triage(
            network_policy_issues=[
                NetworkPolicyIssue(
                    namespace="secure-ns",
                    policy_name="deny-all",
                    issue_type="deny_all_egress",
                    message="Deny all",
                ),
            ],
            dns_issues=[
                DNSIssue(
                    namespace="secure-ns",
                    resource_name="app",
                    issue_type="dns_resolution_error",
                    message="DNS failed",
                ),
            ],
        )
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        assert not groups, "Should not fire without log intelligence confirmation"

    def test_match_negative_wrong_namespace(self) -> None:
        """Signals in different namespaces should not correlate."""
        triage = _empty_triage(
            network_policy_issues=[
                NetworkPolicyIssue(
                    namespace="ns-a",
                    policy_name="deny-all",
                    issue_type="deny_all_egress",
                    message="Deny all",
                ),
            ],
            dns_issues=[
                DNSIssue(
                    namespace="ns-b",
                    resource_name="app",
                    issue_type="dns_resolution_error",
                    message="DNS failed",
                ),
            ],
            log_intelligence={
                "ns-c/app": _make_pod_log_intel(
                    namespace="ns-c", has_dns_failures=True,
                ),
            },
        )
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        assert not groups

    def test_hypothesis_output(self) -> None:
        triage = self._full_triage()
        groups = DNS_NETPOL_LOCKOUT_RULE.match(triage)
        hyp = DNS_NETPOL_LOCKOUT_RULE.hypothesis_template(groups)
        assert hyp["title"] == "NetworkPolicy Blocking DNS Resolution"
        assert hyp["category"] == "dns"
        assert hyp["supporting_evidence"]
        assert len(hyp["supporting_evidence"]) >= 3  # All 3 signal types represented
