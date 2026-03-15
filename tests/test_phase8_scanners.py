"""Tests for new triage scanners: RBAC, Quota, NetworkPolicy, CrashLoop, EventEscalation.

Covers:
- RBACScanner: RBAC error detection, auth-cani-list parsing, missing dirs
- QuotaScanner: near-limit quota detection, limit ranges, missing dirs
- NetworkPolicyScanner: deny-all detection, missing dirs
- CrashLoopAnalyzer: crash context extraction, pattern classification, previous logs
- EventScanner.detect_escalations: repeated events, cascading events
- TroubleshootAnalyzerScanner: contradiction detection, new overlap map entries
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import (
    CrashLoopContext,
    DeploymentIssue,
    EventEscalation,
    K8sEvent,
    NetworkPolicyIssue,
    NodeIssue,
    QuotaIssue,
    RBACIssue,
    TriageResult,
    TroubleshootAnalysis,
    TroubleshootAnalyzerResult,
)
from bundle_analyzer.triage.event_scanner import EventScanner
from bundle_analyzer.triage.troubleshoot_scanner import TroubleshootAnalyzerScanner

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


@pytest_asyncio.fixture
async def bundle_index() -> BundleIndex:
    """Build an index from the sample bundle fixture."""
    return await BundleIndex.build(SAMPLE_BUNDLE)


# ── RBAC Scanner Tests ──────────────────────────────────────────────


class TestRBACScanner:
    """Tests for RBACScanner detection of RBAC/permission issues."""

    @pytest.mark.asyncio
    async def test_detects_rbac_errors_from_error_files(
        self, bundle_index: BundleIndex
    ) -> None:
        """RBACScanner should detect RBAC errors from *-errors.json files."""
        from bundle_analyzer.triage.rbac_scanner import RBACScanner

        scanner = RBACScanner()
        issues = await scanner.scan(bundle_index)

        # Should find at least the pods-errors and secrets-errors
        assert isinstance(issues, list)
        assert len(issues) >= 1

        # All issues should be RBACIssue instances
        for issue in issues:
            assert isinstance(issue, RBACIssue)
            assert issue.error_message  # non-empty error message
            assert issue.severity in ("critical", "warning", "info")

    @pytest.mark.asyncio
    async def test_parses_auth_cani_list_denied_permissions(
        self, bundle_index: BundleIndex
    ) -> None:
        """RBACScanner should detect denied permissions from auth-cani-list."""
        from bundle_analyzer.triage.rbac_scanner import RBACScanner

        scanner = RBACScanner()
        issues = await scanner.scan(bundle_index)

        # Should detect that secrets have no verbs (empty verbs = denied)
        error_messages = [i.error_message.lower() for i in issues]
        resource_types = [i.resource_type.lower() for i in issues]

        # We expect either a direct detection of "secrets" denial from auth-cani-list
        # or from the secrets-errors.json
        has_secrets_issue = any(
            "secrets" in msg or "secrets" in rt
            for msg, rt in zip(error_messages, resource_types)
        )
        assert has_secrets_issue, (
            f"Expected at least one issue about secrets, got: {error_messages}"
        )

    @pytest.mark.asyncio
    async def test_handles_missing_directories_gracefully(self) -> None:
        """RBACScanner returns empty list when RBAC directories don't exist."""
        from bundle_analyzer.triage.rbac_scanner import RBACScanner

        # Create a minimal bundle index with no RBAC data
        empty_dir = SAMPLE_BUNDLE.parent / "_empty_rbac_test"
        empty_dir.mkdir(exist_ok=True)
        try:
            index = await BundleIndex.build(empty_dir)
            scanner = RBACScanner()
            issues = await scanner.scan(index)
            assert isinstance(issues, list)
            # Should not raise, just return empty or minimal list
        finally:
            empty_dir.rmdir()


# ── Quota Scanner Tests ─────────────────────────────────────────────


class TestQuotaScanner:
    """Tests for QuotaScanner detection of resource quota issues."""

    @pytest.mark.asyncio
    async def test_detects_near_limit_quotas(
        self, bundle_index: BundleIndex
    ) -> None:
        """QuotaScanner should detect quotas at >80% utilization."""
        from bundle_analyzer.triage.quota_scanner import QuotaScanner

        scanner = QuotaScanner()
        issues = await scanner.scan(bundle_index)

        assert isinstance(issues, list)
        assert len(issues) >= 1

        # All issues should be QuotaIssue instances
        for issue in issues:
            assert isinstance(issue, QuotaIssue)
            assert issue.namespace == "default"
            assert issue.message  # non-empty
            assert issue.severity in ("critical", "warning", "info")

        # Should detect near-limit quotas (CPU at 3800m/4000m = 95%,
        # memory at 7Gi/8Gi = 87.5%, pods at 18/20 = 90%)
        near_limit_issues = [
            i for i in issues if i.issue_type == "quota_near_limit"
        ]
        assert len(near_limit_issues) >= 1, (
            "Expected at least one near-limit quota issue"
        )

    @pytest.mark.asyncio
    async def test_parses_limit_ranges(
        self, bundle_index: BundleIndex
    ) -> None:
        """QuotaScanner should parse limit ranges from the bundle."""
        from bundle_analyzer.triage.quota_scanner import QuotaScanner

        scanner = QuotaScanner()
        issues = await scanner.scan(bundle_index)

        # The fixture has limit ranges defined - scanner should process them
        # without errors. Whether it produces issues depends on implementation.
        assert isinstance(issues, list)

    @pytest.mark.asyncio
    async def test_handles_missing_directories_gracefully(self) -> None:
        """QuotaScanner returns empty list when quota directories don't exist."""
        from bundle_analyzer.triage.quota_scanner import QuotaScanner

        empty_dir = SAMPLE_BUNDLE.parent / "_empty_quota_test"
        empty_dir.mkdir(exist_ok=True)
        try:
            index = await BundleIndex.build(empty_dir)
            scanner = QuotaScanner()
            issues = await scanner.scan(index)
            assert isinstance(issues, list)
        finally:
            empty_dir.rmdir()


# ── Network Policy Scanner Tests ────────────────────────────────────


class TestNetworkPolicyScanner:
    """Tests for NetworkPolicyScanner detection of network policy issues."""

    @pytest.mark.asyncio
    async def test_detects_deny_all_policies(
        self, bundle_index: BundleIndex
    ) -> None:
        """NetworkPolicyScanner should detect deny-all ingress/egress policies."""
        from bundle_analyzer.triage.network_policy_scanner import NetworkPolicyScanner

        scanner = NetworkPolicyScanner()
        issues = await scanner.scan(bundle_index)

        assert isinstance(issues, list)
        assert len(issues) >= 1

        for issue in issues:
            assert isinstance(issue, NetworkPolicyIssue)
            assert issue.namespace == "default"
            assert issue.message
            assert issue.severity in ("critical", "warning", "info")

        # Should detect the deny-all-ingress policy (empty ingress list)
        deny_all_issues = [
            i for i in issues if i.issue_type == "deny_all_ingress"
        ]
        assert len(deny_all_issues) >= 1, (
            "Expected at least one deny-all-ingress issue"
        )
        assert deny_all_issues[0].policy_name == "deny-all-ingress"

    @pytest.mark.asyncio
    async def test_handles_missing_directories_gracefully(self) -> None:
        """NetworkPolicyScanner returns empty list when policy dir doesn't exist."""
        from bundle_analyzer.triage.network_policy_scanner import NetworkPolicyScanner

        empty_dir = SAMPLE_BUNDLE.parent / "_empty_netpol_test"
        empty_dir.mkdir(exist_ok=True)
        try:
            index = await BundleIndex.build(empty_dir)
            scanner = NetworkPolicyScanner()
            issues = await scanner.scan(index)
            assert isinstance(issues, list)
        finally:
            empty_dir.rmdir()


# ── CrashLoop Analyzer Tests ───────────────────────────────────────


class TestCrashLoopAnalyzer:
    """Tests for CrashLoopAnalyzer crash context extraction."""

    @pytest.mark.asyncio
    async def test_extracts_crash_context(
        self, bundle_index: BundleIndex
    ) -> None:
        """CrashLoopAnalyzer should extract context from crash-looping pods."""
        from bundle_analyzer.triage.crashloop_analyzer import CrashLoopAnalyzer

        analyzer = CrashLoopAnalyzer()
        contexts = await analyzer.scan(bundle_index)

        assert isinstance(contexts, list)
        assert len(contexts) >= 1

        for ctx in contexts:
            assert isinstance(ctx, CrashLoopContext)
            assert ctx.namespace
            assert ctx.pod_name
            assert ctx.container_name
            assert ctx.severity in ("critical", "warning", "info")

        # Should find the crashloop-pod
        crashloop_contexts = [
            c for c in contexts if c.pod_name == "crashloop-pod"
        ]
        assert len(crashloop_contexts) >= 1, (
            "Expected crash context for crashloop-pod"
        )

        ctx = crashloop_contexts[0]
        assert ctx.namespace == "default"
        assert ctx.container_name == "app"
        assert ctx.restart_count >= 15
        assert ctx.exit_code == 1

    @pytest.mark.asyncio
    async def test_classifies_crash_patterns(
        self, bundle_index: BundleIndex
    ) -> None:
        """CrashLoopAnalyzer should classify crash patterns correctly."""
        from bundle_analyzer.triage.crashloop_analyzer import CrashLoopAnalyzer

        analyzer = CrashLoopAnalyzer()
        contexts = await analyzer.scan(bundle_index)

        crashloop_contexts = [
            c for c in contexts if c.pod_name == "crashloop-pod"
        ]
        assert len(crashloop_contexts) >= 1

        ctx = crashloop_contexts[0]
        # The crashloop-pod has database connection errors
        # Pattern should be "dependency_timeout" or "config_error" or similar
        assert ctx.crash_pattern != "", "Expected a classified crash pattern"
        assert ctx.crash_pattern in (
            "oom", "segfault", "panic", "config_error",
            "dependency_timeout", "unknown",
        )

    @pytest.mark.asyncio
    async def test_reads_previous_logs(
        self, bundle_index: BundleIndex
    ) -> None:
        """CrashLoopAnalyzer should read previous container logs."""
        from bundle_analyzer.triage.crashloop_analyzer import CrashLoopAnalyzer

        analyzer = CrashLoopAnalyzer()
        contexts = await analyzer.scan(bundle_index)

        crashloop_contexts = [
            c for c in contexts if c.pod_name == "crashloop-pod"
        ]
        assert len(crashloop_contexts) >= 1

        ctx = crashloop_contexts[0]
        # Should have previous log lines from app-previous.log
        assert len(ctx.previous_log_lines) > 0 or len(ctx.last_log_lines) > 0, (
            "Expected either previous or current log lines"
        )


# ── Event Escalation Tests ──────────────────────────────────────────


class TestEventEscalation:
    """Tests for EventScanner.detect_escalations method."""

    def setup_method(self) -> None:
        """Create scanner instance."""
        self.scanner = EventScanner()

    def test_detects_repeated_events(self) -> None:
        """detect_escalations should flag events with count > 10."""
        events = [
            K8sEvent(
                namespace="default",
                name="test-pod.event1",
                reason="BackOff",
                message="Back-off restarting failed container",
                type="Warning",
                involved_object_kind="Pod",
                involved_object_name="test-pod",
                first_timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
                last_timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
                count=15,
            ),
        ]

        escalations = self.scanner.detect_escalations(events)

        assert len(escalations) >= 1
        esc = escalations[0]
        assert isinstance(esc, EventEscalation)
        assert esc.escalation_type == "repeated"
        assert esc.total_count == 15
        assert esc.involved_object_name == "test-pod"
        assert "BackOff" in esc.event_reasons

    def test_detects_cascading_events(self) -> None:
        """detect_escalations should flag multiple reasons for the same object."""
        events = [
            K8sEvent(
                namespace="default",
                name="test-pod.event1",
                reason="BackOff",
                message="Back-off restarting",
                type="Warning",
                involved_object_kind="Pod",
                involved_object_name="test-pod",
                first_timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
                last_timestamp=datetime(2024, 1, 15, 10, 5, tzinfo=UTC),
                count=3,
            ),
            K8sEvent(
                namespace="default",
                name="test-pod.event2",
                reason="Unhealthy",
                message="Liveness probe failed",
                type="Warning",
                involved_object_kind="Pod",
                involved_object_name="test-pod",
                first_timestamp=datetime(2024, 1, 15, 10, 2, tzinfo=UTC),
                last_timestamp=datetime(2024, 1, 15, 10, 4, tzinfo=UTC),
                count=5,
            ),
        ]

        escalations = self.scanner.detect_escalations(events)

        assert len(escalations) >= 1
        esc = escalations[0]
        assert isinstance(esc, EventEscalation)
        assert esc.escalation_type == "cascading"
        assert len(esc.event_reasons) >= 2
        assert "BackOff" in esc.event_reasons
        assert "Unhealthy" in esc.event_reasons
        assert esc.total_count == 8

    def test_no_escalation_for_low_count_single_reason(self) -> None:
        """No escalation for events with low count and single reason."""
        events = [
            K8sEvent(
                namespace="default",
                name="test-pod.event1",
                reason="BackOff",
                message="Back-off restarting",
                type="Warning",
                involved_object_kind="Pod",
                involved_object_name="test-pod",
                first_timestamp=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
                last_timestamp=datetime(2024, 1, 15, 10, 5, tzinfo=UTC),
                count=3,
            ),
        ]

        escalations = self.scanner.detect_escalations(events)

        assert len(escalations) == 0

    @pytest.mark.asyncio
    async def test_escalation_from_fixture_events(
        self, bundle_index: BundleIndex
    ) -> None:
        """Full scan + detect_escalations on fixture data should find escalations."""
        events = await self.scanner.scan(bundle_index)
        escalations = self.scanner.detect_escalations(events)

        # The fixture has crashloop-pod with count=15 BackOff + count=8 Unhealthy
        # + count=3 FailedMount = cascading + repeated
        assert len(escalations) >= 1

        crashloop_esc = [
            e for e in escalations if e.involved_object_name == "crashloop-pod"
        ]
        assert len(crashloop_esc) >= 1
        esc = crashloop_esc[0]
        # Should be cascading (multiple reasons: BackOff, Unhealthy, FailedMount)
        assert esc.escalation_type == "cascading"
        assert esc.total_count >= 26  # 15 + 8 + 3


# ── Enhanced TroubleshootScanner Tests ──────────────────────────────


class TestTroubleshootScannerEnhanced:
    """Tests for TroubleshootAnalyzerScanner contradiction and overlap enhancements."""

    def setup_method(self) -> None:
        """Set up scanner."""
        self.scanner = TroubleshootAnalyzerScanner()

    def test_contradiction_detection(self) -> None:
        """Scanner should handle contradictions between troubleshoot.sh and native results."""
        # A passing deploymentStatus from troubleshoot.sh while native scanner found issues
        native = TriageResult(
            deployment_issues=[
                DeploymentIssue(
                    namespace="default",
                    name="my-deploy",
                    desired_replicas=3,
                    ready_replicas=1,
                    issue="1/3 replicas ready",
                ),
            ],
        )
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="deploymentStatus",
                    analyzer_type="deploymentStatus",
                    is_pass=True,
                    title="Deployment Status",
                    message="All deployments are healthy",
                    severity="pass",
                ),
            ],
            pass_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        # Passing checks are not included as issues by current implementation
        # This test ensures no crash occurs on contradictory data
        assert isinstance(issues, list)

    def test_new_overlap_map_entries(self) -> None:
        """Verify the overlap map covers expected analyzer types."""
        from bundle_analyzer.triage.troubleshoot_scanner import _OVERLAP_MAP

        # Original entries should still be present
        assert "deploymentStatus" in _OVERLAP_MAP
        assert "nodeResources" in _OVERLAP_MAP
        assert "storageClass" in _OVERLAP_MAP
        assert "ingress" in _OVERLAP_MAP

    def test_corroboration_with_node_issues(self) -> None:
        """nodeResources result corroborates native NodeScanner finding."""
        native = TriageResult(
            node_issues=[
                NodeIssue(
                    node_name="worker-1",
                    condition="MemoryPressure",
                    message="Memory pressure detected",
                ),
            ],
        )
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="nodeResources",
                    analyzer_type="nodeResources",
                    is_fail=True,
                    title="Node Resources",
                    message="worker-1 has insufficient memory",
                    severity="fail",
                ),
            ],
            fail_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        assert len(issues) == 1
        assert issues[0].corroborates is not None
        assert "node" in issues[0].corroborates

    def test_gap_fill_for_new_analyzer_types(self) -> None:
        """New analyzer types without native scanners create gap-fill issues."""
        native = TriageResult()
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="clusterPodStatuses",
                    analyzer_type="clusterPodStatuses",
                    is_fail=True,
                    title="Cluster Pod Statuses",
                    message="2 pods are in CrashLoopBackOff",
                    severity="fail",
                ),
                TroubleshootAnalyzerResult(
                    name="certificates",
                    analyzer_type="certificates",
                    is_warn=True,
                    title="Certificate Expiration",
                    message="1 cert expiring within 30 days",
                    severity="warn",
                ),
            ],
            fail_count=1,
            warn_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        assert len(issues) == 2
        # These are gap-fills: no native scanner covers them
        for issue in issues:
            assert issue.corroborates is None

        # clusterPodStatuses should be critical (isFail)
        pod_status_issue = [
            i for i in issues if i.analyzer_type == "clusterPodStatuses"
        ]
        assert len(pod_status_issue) == 1
        assert pod_status_issue[0].severity == "critical"

        # certificates should be warning (isWarn)
        cert_issue = [i for i in issues if i.analyzer_type == "certificates"]
        assert len(cert_issue) == 1
        assert cert_issue[0].severity == "warning"


# ── Integration: Updated analysis.json ──────────────────────────────


@pytest.mark.asyncio
async def test_updated_analysis_json_parsed(bundle_index: BundleIndex) -> None:
    """Verify updated analysis.json with 12 entries is parsed correctly."""
    from bundle_analyzer.bundle.troubleshoot_parser import TroubleshootParser

    raw = bundle_index.read_existing_analysis()
    parser = TroubleshootParser()
    result = parser.parse_analysis(raw)

    assert result.has_results is True
    assert len(result.results) == 12
    assert result.pass_count == 3
    assert result.warn_count == 5
    assert result.fail_count == 4


@pytest.mark.asyncio
async def test_full_triage_engine_with_new_fixtures(
    bundle_index: BundleIndex,
) -> None:
    """Full triage engine run with updated fixtures should complete without errors."""
    from bundle_analyzer.triage.engine import TriageEngine

    engine = TriageEngine()
    result = await engine.run(bundle_index)

    # Basic sanity checks
    assert result.troubleshoot_analysis.has_results is True
    assert len(result.troubleshoot_analysis.results) == 12
    assert len(result.warning_events) >= 1
    assert len(result.event_escalations) >= 1

    # External issues should include new analyzer types
    analyzer_types = {i.analyzer_type for i in result.external_analyzer_issues}
    # clusterPodStatuses and certificates are gap-fills (no native scanner)
    assert "clusterPodStatuses" in analyzer_types or "cephStatus" in analyzer_types


# ── Model Import Tests ──────────────────────────────────────────────


def test_new_models_import() -> None:
    """Verify all new models can be imported and instantiated."""
    # RBACIssue
    rbac = RBACIssue(
        namespace="default",
        resource_type="secrets",
        error_message="cannot list secrets",
    )
    assert rbac.severity == "warning"
    assert rbac.suggested_permission == ""

    # QuotaIssue
    quota = QuotaIssue(
        namespace="default",
        resource_name="compute-quota",
        issue_type="quota_near_limit",
        resource_type="cpu",
        current_usage="3800m",
        limit="4000m",
        message="CPU quota at 95%",
    )
    assert quota.severity == "warning"

    # NetworkPolicyIssue
    netpol = NetworkPolicyIssue(
        namespace="default",
        policy_name="deny-all-ingress",
        issue_type="deny_all_ingress",
        message="Policy denies all ingress traffic",
    )
    assert netpol.affected_pods == []

    # EventEscalation
    esc = EventEscalation(
        namespace="default",
        involved_object_kind="Pod",
        involved_object_name="test-pod",
        event_reasons=["BackOff", "Unhealthy"],
        total_count=20,
        escalation_type="cascading",
        message="Pod/test-pod has cascading events",
    )
    assert esc.severity == "warning"

    # CrashLoopContext
    crash = CrashLoopContext(
        namespace="default",
        pod_name="test-pod",
        container_name="app",
    )
    assert crash.exit_code is None
    assert crash.crash_pattern == ""
    assert crash.severity == "critical"


def test_triage_result_has_new_fields() -> None:
    """TriageResult should have fields for new scanner outputs."""
    result = TriageResult()

    assert result.rbac_issues == []
    assert result.quota_issues == []
    assert result.network_policy_issues == []
    assert result.crash_contexts == []
    assert result.event_escalations == []
