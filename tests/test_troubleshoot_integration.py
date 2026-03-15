"""Tests for troubleshoot.sh analyzer and preflight integration.

Covers:
- TroubleshootParser (parse well-formed, empty, malformed)
- TroubleshootAnalyzerScanner (dedup, gap-fill)
- TriageEngine full run with analysis.json
- Synthesis prompt formatting
- Edge cases (no analysis.json, empty results)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.bundle.troubleshoot_parser import TroubleshootParser
from bundle_analyzer.models import (
    DeploymentIssue,
    ExternalAnalyzerIssue,
    NodeIssue,
    PreflightReport,
    StorageIssue,
    TriageResult,
    TroubleshootAnalysis,
    TroubleshootAnalyzerResult,
)
from bundle_analyzer.triage.troubleshoot_scanner import TroubleshootAnalyzerScanner

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


# ── Parser Tests ─────────────────────────────────────────────────────


class TestTroubleshootParser:
    """Tests for TroubleshootParser."""

    def setup_method(self) -> None:
        """Create parser instance."""
        self.parser = TroubleshootParser()

    def test_parse_well_formed_analysis(self) -> None:
        """Parse a well-formed analysis.json with mixed results."""
        raw = json.loads((SAMPLE_BUNDLE / "analysis.json").read_text())
        result = self.parser.parse_analysis(raw)

        assert isinstance(result, TroubleshootAnalysis)
        assert result.has_results is True
        assert len(result.results) == 12
        assert result.pass_count == 3  # clusterVersion, containerRuntime, distribution
        assert result.warn_count == 5  # deploymentStatus, imagePullSecret, event, certificates, DNS textAnalyze
        assert result.fail_count == 4  # nodeResources, cephStatus, textAnalyze(OOM), clusterPodStatuses

    def test_parse_empty_analysis(self) -> None:
        """Parse empty analysis returns empty TroubleshootAnalysis."""
        result = self.parser.parse_analysis([])

        assert result.has_results is False
        assert len(result.results) == 0
        assert result.pass_count == 0
        assert result.warn_count == 0
        assert result.fail_count == 0

    def test_parse_malformed_entries_skipped(self) -> None:
        """Malformed entries are skipped gracefully."""
        raw = [
            "not a dict",
            42,
            {"name": "valid", "isPass": True, "title": "ok", "message": "ok"},
        ]
        result = self.parser.parse_analysis(raw)

        assert result.has_results is True
        assert len(result.results) == 1
        assert result.pass_count == 1

    def test_parse_single_result_fields(self) -> None:
        """Verify all fields are parsed correctly for a single result."""
        raw = {
            "name": "cephStatus",
            "isFail": True,
            "title": "Ceph Health",
            "message": "Ceph is degraded",
            "URI": "https://docs.ceph.com/health",
            "strict": True,
        }
        result = self.parser.parse_single_result(raw)

        assert result.name == "cephStatus"
        assert result.is_fail is True
        assert result.is_pass is False
        assert result.is_warn is False
        assert result.title == "Ceph Health"
        assert result.message == "Ceph is degraded"
        assert result.uri == "https://docs.ceph.com/health"
        assert result.severity == "fail"
        assert result.strict is True
        assert result.analyzer_type == "cephStatus"

    def test_parse_alternative_field_names(self) -> None:
        """Handle alternative field naming conventions."""
        raw = {
            "check_name": "my-check",
            "is_fail": True,
            "title": "Failed",
            "message": "Something failed",
            "uri": "https://example.com",
        }
        result = self.parser.parse_single_result(raw)

        assert result.name == "my-check"
        assert result.check_name == "my-check"
        assert result.is_fail is True
        assert result.uri == "https://example.com"

    def test_infer_severity_from_outcome_field(self) -> None:
        """When bool flags are absent, infer from outcome/severity field."""
        raw = {
            "name": "custom-check",
            "severity": "warning",
            "title": "Warning",
            "message": "Something warned",
        }
        result = self.parser.parse_single_result(raw)

        assert result.is_warn is True
        assert result.is_fail is False
        assert result.is_pass is False
        assert result.severity == "warn"

    def test_infer_analyzer_type_from_name(self) -> None:
        """Analyzer type is inferred from the name field."""
        cases = [
            ("clusterVersion", "clusterVersion"),
            ("Node Resources check", "nodeResources"),
            ("deployment-status", "deploymentStatus"),
            ("container-runtime", "containerRuntime"),
            ("unknown-thing", "unknown-thing"),
        ]
        for name, expected_type in cases:
            raw = {"name": name, "isPass": True, "title": "", "message": ""}
            result = self.parser.parse_single_result(raw)
            assert result.analyzer_type == expected_type, f"Failed for name={name}"

    def test_parse_preflight(self) -> None:
        """Parse preflight.json into typed PreflightReport."""
        raw = json.loads((SAMPLE_BUNDLE / "preflight.json").read_text())
        result = self.parser.parse_preflight(raw)

        assert isinstance(result, PreflightReport)
        assert len(result.results) == 5
        assert result.pass_count == 3
        assert result.warn_count == 1
        assert result.fail_count == 1

    def test_parse_empty_preflight(self) -> None:
        """Empty preflight returns empty report."""
        result = self.parser.parse_preflight([])

        assert len(result.results) == 0
        assert result.pass_count == 0


# ── Scanner Tests ────────────────────────────────────────────────────


class TestTroubleshootAnalyzerScanner:
    """Tests for TroubleshootAnalyzerScanner dedup and gap-fill logic."""

    def setup_method(self) -> None:
        """Set up scanner and sample native results."""
        self.scanner = TroubleshootAnalyzerScanner()

    def _make_native_results(self) -> TriageResult:
        """Create native results with some issues for dedup testing."""
        return TriageResult(
            deployment_issues=[
                DeploymentIssue(
                    namespace="default",
                    name="break-crashloop",
                    desired_replicas=3,
                    ready_replicas=1,
                    issue="1/3 replicas ready",
                ),
            ],
            node_issues=[
                NodeIssue(
                    node_name="worker-1",
                    condition="MemoryPressure",
                    message="Memory pressure detected",
                ),
            ],
            storage_issues=[
                StorageIssue(
                    namespace="default",
                    resource_name="data-pvc",
                    resource_type="PVC",
                    issue="pending",
                    message="PVC pending",
                ),
            ],
        )

    def test_corroboration_deployment(self) -> None:
        """deploymentStatus result corroborates native DeploymentScanner finding."""
        native = self._make_native_results()
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="deploymentStatus",
                    analyzer_type="deploymentStatus",
                    is_warn=True,
                    title="Deployment Status",
                    message="break-crashloop deployment has only 1 ready replica",
                    severity="warn",
                ),
            ],
            warn_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        assert len(issues) == 1
        assert issues[0].corroborates is not None
        assert "break-crashloop" in issues[0].corroborates

    def test_gap_fill_ceph(self) -> None:
        """cephStatus result creates a gap-fill issue (no native scanner)."""
        native = self._make_native_results()
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="cephStatus",
                    analyzer_type="cephStatus",
                    is_fail=True,
                    title="Ceph Health",
                    message="Ceph cluster is in HEALTH_WARN state",
                    severity="fail",
                ),
            ],
            fail_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        assert len(issues) == 1
        assert issues[0].corroborates is None
        assert issues[0].analyzer_type == "cephStatus"
        assert issues[0].severity == "critical"

    def test_passing_checks_not_included(self) -> None:
        """Passing checks do not produce ExternalAnalyzerIssue."""
        native = self._make_native_results()
        analysis = TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="clusterVersion",
                    analyzer_type="clusterVersion",
                    is_pass=True,
                    title="Cluster Version",
                    message="OK",
                    severity="pass",
                ),
            ],
            pass_count=1,
            has_results=True,
        )

        issues = self.scanner._build_external_issues(analysis, native)

        assert len(issues) == 0

    def test_severity_mapping(self) -> None:
        """Verify severity mapping: is_fail → critical, is_warn → warning."""
        fail_result = TroubleshootAnalyzerResult(
            name="test", is_fail=True, severity="fail",
            analyzer_type="test", title="", message="",
        )
        warn_result = TroubleshootAnalyzerResult(
            name="test", is_warn=True, severity="warn",
            analyzer_type="test", title="", message="",
        )

        assert self.scanner._map_severity(fail_result) == "critical"
        assert self.scanner._map_severity(warn_result) == "warning"


# ── Integration Tests ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def index() -> BundleIndex:
    """Build an index from the sample bundle fixture."""
    return await BundleIndex.build(SAMPLE_BUNDLE)


@pytest.mark.asyncio
async def test_triage_engine_includes_troubleshoot(index: BundleIndex) -> None:
    """Full triage engine run populates troubleshoot_analysis."""
    from bundle_analyzer.triage.engine import TriageEngine

    engine = TriageEngine()
    result = await engine.run(index)

    # analysis.json exists in our fixture, so troubleshoot_analysis should be populated
    assert result.troubleshoot_analysis.has_results is True
    assert len(result.troubleshoot_analysis.results) > 0
    assert result.troubleshoot_analysis.fail_count >= 1

    # External issues should exist (cephStatus is gap-fill)
    ceph_issues = [
        i for i in result.external_analyzer_issues
        if i.analyzer_type == "cephStatus"
    ]
    assert len(ceph_issues) >= 1


@pytest.mark.asyncio
async def test_triage_engine_includes_preflight(index: BundleIndex) -> None:
    """Full triage engine run populates preflight_report when preflight.json exists."""
    from bundle_analyzer.triage.engine import TriageEngine

    engine = TriageEngine()
    result = await engine.run(index)

    # preflight.json exists in our fixture
    assert result.preflight_report is not None
    assert len(result.preflight_report.results) > 0
    assert result.preflight_report.fail_count >= 1


# ── Synthesis Prompt Tests ───────────────────────────────────────────


def test_synthesis_prompt_includes_troubleshoot() -> None:
    """Synthesis prompt includes troubleshoot.sh results when present."""
    from bundle_analyzer.ai.prompts.synthesis import build_synthesis_user_prompt

    triage = TriageResult(
        troubleshoot_analysis=TroubleshootAnalysis(
            results=[
                TroubleshootAnalyzerResult(
                    name="cephStatus",
                    analyzer_type="cephStatus",
                    is_fail=True,
                    title="Ceph Health",
                    message="Degraded",
                    severity="fail",
                ),
                TroubleshootAnalyzerResult(
                    name="clusterVersion",
                    analyzer_type="clusterVersion",
                    is_pass=True,
                    title="Version",
                    message="OK",
                    severity="pass",
                ),
            ],
            pass_count=1,
            fail_count=1,
            has_results=True,
        ),
        external_analyzer_issues=[
            ExternalAnalyzerIssue(
                analyzer_type="cephStatus",
                name="cephStatus",
                title="Ceph Health",
                message="Degraded",
                severity="critical",
            ),
        ],
    )

    prompt = build_synthesis_user_prompt([], triage)

    assert "Troubleshoot.sh Analyzer Results" in prompt
    assert "[FAIL] Ceph Health: Degraded" in prompt
    assert "1 checks passed" in prompt
    assert "External Analyzer Issues" in prompt
    assert "cephStatus" in prompt


def test_synthesis_prompt_omits_when_empty() -> None:
    """Synthesis prompt omits troubleshoot sections when no results."""
    from bundle_analyzer.ai.prompts.synthesis import build_synthesis_user_prompt

    triage = TriageResult()

    prompt = build_synthesis_user_prompt([], triage)

    assert "Troubleshoot.sh Analyzer Results" not in prompt
    assert "External Analyzer Issues" not in prompt
    assert "Preflight Check Results" not in prompt


def test_synthesis_prompt_includes_preflight() -> None:
    """Synthesis prompt includes preflight results when present."""
    from bundle_analyzer.ai.prompts.synthesis import build_synthesis_user_prompt
    from bundle_analyzer.models import PreflightCheckResult, PreflightReport

    triage = TriageResult(
        preflight_report=PreflightReport(
            results=[
                PreflightCheckResult(
                    name="memory",
                    is_warn=True,
                    title="Node Memory",
                    message="Insufficient memory",
                    severity="warn",
                ),
                PreflightCheckResult(
                    name="version",
                    is_pass=True,
                    title="K8s Version",
                    message="OK",
                    severity="pass",
                ),
            ],
            pass_count=1,
            warn_count=1,
        ),
    )

    prompt = build_synthesis_user_prompt([], triage)

    assert "Preflight Check Results" in prompt
    assert "[WARN] Node Memory: Insufficient memory" in prompt
    # Passing results are not included in prompt (token efficiency)
    assert "K8s Version" not in prompt


# ── Edge Cases ───────────────────────────────────────────────────────


def test_models_import() -> None:
    """Verify all new models can be imported."""
    from bundle_analyzer.models import (
        PreflightReport,
        TroubleshootAnalysis,
    )

    # Verify defaults
    analysis = TroubleshootAnalysis()
    assert analysis.has_results is False
    assert analysis.results == []

    report = PreflightReport()
    assert report.results == []
    assert report.collected_at is None


def test_triage_result_backward_compat() -> None:
    """TriageResult still works with only the original fields."""
    result = TriageResult()

    # Original fields still default correctly
    assert result.existing_analysis == []
    assert result.critical_pods == []

    # New fields default to empty
    assert result.troubleshoot_analysis.has_results is False
    assert result.preflight_report is None
    assert result.external_analyzer_issues == []


def test_analysis_result_has_preflight() -> None:
    """AnalysisResult includes preflight_report field."""
    from bundle_analyzer.models import AnalysisResult, BundleMetadata

    result = AnalysisResult(
        bundle_metadata=BundleMetadata(bundle_path=Path(".")),
        triage=TriageResult(),
        findings=[],
        root_cause=None,
        confidence=0.0,
        timeline=[],
        predictions=[],
        uncertainty=[],
        cluster_summary="test",
        analysis_duration_seconds=0.0,
    )

    assert result.preflight_report is None
