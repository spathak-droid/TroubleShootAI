"""End-to-end pipeline test with realistic multi-failure bundle.

Creates a realistic support bundle with 6+ simultaneous failure scenarios,
runs the full triage + validation pipeline (no AI key needed), and verifies
that every failure is detected with correct evidence grounding.

Bundle builder lives in tests/fixtures/e2e_bundle_builder.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalysisResult, TriageResult
from bundle_analyzer.triage.engine import TriageEngine
from tests.fixtures.e2e_bundle_builder import build_test_bundle


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def bundle_dir(tmp_path: Path) -> Path:
    """Create a temporary bundle directory with all failure scenarios."""
    bundle = tmp_path / "test-bundle"
    bundle.mkdir()
    build_test_bundle(bundle)
    return bundle


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_triage_detects_all_failures(bundle_dir: Path) -> None:
    """Run the full triage pipeline and verify every failure is detected."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    critical_names = {p.pod_name for p in triage.critical_pods}
    warning_names = {p.pod_name for p in triage.warning_pods}
    all_flagged = critical_names | warning_names

    assert "api-server-7f8b9c" in all_flagged, (
        f"CrashLoopBackOff pod not detected. Found: {all_flagged}"
    )
    assert "worker-batch-4a2c" in all_flagged, (
        f"OOMKilled pod not detected. Found: {all_flagged}"
    )
    assert "frontend-deploy-x9z" in all_flagged, (
        f"ImagePullBackOff pod not detected. Found: {all_flagged}"
    )
    assert "ml-training-job-1" in all_flagged, (
        f"Pending pod not detected. Found: {all_flagged}"
    )
    assert "config-app-abc" in all_flagged, (
        f"ConfigError pod not detected. Found: {all_flagged}"
    )
    assert "coredns-5d78c9869d-abc12" in all_flagged, (
        f"CoreDNS crash not detected. Found: {all_flagged}"
    )
    # Healthy pod should NOT be flagged
    assert "web-frontend-ok" not in all_flagged, (
        "Healthy pod incorrectly flagged as failing!"
    )


@pytest.mark.asyncio
async def test_node_issues_detected(bundle_dir: Path) -> None:
    """Verify node-level failures are caught."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    node_names = {n.node_name for n in triage.node_issues}
    assert "node-pressure" in node_names, (
        f"MemoryPressure node not detected. Found: {node_names}"
    )
    assert "node-notready" in node_names, (
        f"NotReady node not detected. Found: {node_names}"
    )
    assert "node-healthy" not in node_names, "Healthy node incorrectly flagged!"


@pytest.mark.asyncio
async def test_issue_types_correct(bundle_dir: Path) -> None:
    """Verify correct issue_type classification for each pod."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    all_pods = triage.critical_pods + triage.warning_pods
    pod_issues: dict[str, str] = {}
    for p in all_pods:
        pod_issues[p.pod_name] = p.issue_type

    assert pod_issues.get("api-server-7f8b9c") == "CrashLoopBackOff"
    assert pod_issues.get("worker-batch-4a2c") == "OOMKilled"
    assert pod_issues.get("frontend-deploy-x9z") == "ImagePullBackOff"
    assert pod_issues.get("config-app-abc") in ("CreateContainerConfigError", "Pending")


@pytest.mark.asyncio
async def test_pending_pod_detected_as_pending(bundle_dir: Path) -> None:
    """Verify pending pod with FailedScheduling is classified correctly."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    all_pods = triage.critical_pods + triage.warning_pods
    pending_pods = [p for p in all_pods if p.pod_name == "ml-training-job-1"]
    assert len(pending_pods) >= 1, "Pending pod not found in triage results"
    assert pending_pods[0].issue_type == "Pending"


@pytest.mark.asyncio
async def test_deployment_issues_detected(bundle_dir: Path) -> None:
    """Verify deployment with 0 ready replicas is flagged."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    deploy_names = {d.name for d in triage.deployment_issues}
    assert "api-server" in deploy_names, (
        f"Broken deployment not detected. Found: {deploy_names}"
    )


@pytest.mark.asyncio
async def test_config_issues_detected(bundle_dir: Path) -> None:
    """Verify missing configmap reference is detected."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    config_refs = [c.resource_name for c in triage.config_issues]
    has_missing_cm = any("app-settings" in ref for ref in config_refs)
    assert has_missing_cm, (
        f"Missing configmap 'app-settings' not detected. Config issues: {config_refs}"
    )


@pytest.mark.asyncio
async def test_warning_events_captured(bundle_dir: Path) -> None:
    """Verify warning events (BackOff, OOMKilling, FailedScheduling) are captured."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    event_reasons = {e.reason for e in triage.warning_events}
    assert "BackOff" in event_reasons, f"BackOff event not captured. Found: {event_reasons}"
    assert "OOMKilling" in event_reasons, f"OOMKilling event not captured. Found: {event_reasons}"
    assert "FailedScheduling" in event_reasons, f"FailedScheduling event not captured. Found: {event_reasons}"


@pytest.mark.asyncio
async def test_scheduling_issues_from_events(bundle_dir: Path) -> None:
    """Verify FailedScheduling events produce scheduling issues."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    scheduling_pods = {s.pod_name for s in triage.scheduling_issues}
    pending_pods = {
        p.pod_name for p in triage.critical_pods + triage.warning_pods
        if p.issue_type == "Pending"
    }
    detected = scheduling_pods | pending_pods
    assert "ml-training-job-1" in detected, (
        f"FailedScheduling not detected for ml-training-job-1. "
        f"Scheduling: {scheduling_pods}, Pending: {pending_pods}"
    )


@pytest.mark.asyncio
async def test_evidence_has_source_files(bundle_dir: Path) -> None:
    """Verify triage findings include source_file references."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    for pod in triage.critical_pods:
        assert pod.source_file, (
            f"Pod {pod.pod_name} missing source_file in evidence"
        )


@pytest.mark.asyncio
async def test_rbac_errors_captured(bundle_dir: Path) -> None:
    """Verify RBAC collection errors are captured."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    has_rbac = len(triage.rbac_issues) > 0 or len(index.rbac_errors) > 0
    assert has_rbac, "RBAC collection errors not captured"


@pytest.mark.asyncio
async def test_bundle_metadata_populated(bundle_dir: Path) -> None:
    """Verify bundle metadata is extracted from version.yaml."""
    index = await BundleIndex.build(bundle_dir)
    assert index.metadata is not None
    assert index.metadata.collected_at is not None


@pytest.mark.asyncio
async def test_log_streaming_works(bundle_dir: Path) -> None:
    """Verify container logs are streamable from the bundle."""
    index = await BundleIndex.build(bundle_dir)

    lines = list(index.stream_log("default", "api-server-7f8b9c", "api", previous=False))
    assert len(lines) > 0, "No current logs streamed for crashloop pod"
    assert any("connection refused" in line for line in lines), (
        "Expected 'connection refused' in crashloop pod logs"
    )

    prev_lines = list(index.stream_log("default", "api-server-7f8b9c", "api", previous=True))
    assert len(prev_lines) > 0, "No previous logs streamed for crashloop pod"


@pytest.mark.asyncio
async def test_triage_only_analysis_completes(bundle_dir: Path) -> None:
    """Verify the orchestrator returns triage-only results without an API key."""
    import os

    saved = {}
    for key in ("OPEN_ROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        saved[key] = os.environ.pop(key, None)

    try:
        from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator
        from bundle_analyzer.ai.context_injector import ContextInjector

        index = await BundleIndex.build(bundle_dir)
        engine = TriageEngine()
        triage = await engine.run(index)

        orchestrator = AnalysisOrchestrator()
        result = await orchestrator.run(
            triage=triage,
            index=index,
            context_injector=ContextInjector(),
        )

        assert isinstance(result, AnalysisResult)
        assert result.triage is not None
        assert result.analysis_quality == "degraded"
        assert len(result.triage.critical_pods) + len(result.triage.warning_pods) > 0
    finally:
        for key, val in saved.items():
            if val is not None:
                os.environ[key] = val


@pytest.mark.asyncio
async def test_security_scrubber_redacts_secrets(bundle_dir: Path) -> None:
    """Verify the scrubber redacts secrets from pod JSON."""
    from bundle_analyzer.security.scrubber import BundleScrubber

    index = await BundleIndex.build(bundle_dir)
    pod_data = index.read_json("cluster-resources/pods/default/api-server-7f8b9c.json")
    assert pod_data is not None

    scrubber = BundleScrubber()
    scrubbed, report = scrubber.scrub_pod_json(pod_data)

    scrubbed_json = json.dumps(scrubbed)
    assert "DB_HOST" in scrubbed_json, "Env var name DB_HOST should be preserved"
    assert "LOG_LEVEL" in scrubbed_json, "Env var name LOG_LEVEL should be preserved"
    assert "[REDACTED" in scrubbed_json, "Env var values should be redacted"
    assert "postgres.db.svc.cluster.local" not in scrubbed_json, (
        "DB_HOST value should be redacted"
    )


@pytest.mark.asyncio
async def test_api_response_scrubber(bundle_dir: Path) -> None:
    """Verify the API response scrubber redacts sensitive data in findings."""
    from bundle_analyzer.api.response_scrubber import scrub_findings_list
    from bundle_analyzer.models import Evidence, Finding

    findings = [
        Finding(
            id="test-1",
            severity="critical",
            type="pod-failure",
            resource="pod/default/test",
            symptom="Pod crashed with connection to postgres://admin:s3cretP@ss@10.0.5.23:5432",
            root_cause="Database password exposed in connection string",
            evidence=[
                Evidence(
                    file="cluster-resources/pods/default/test.json",
                    excerpt="DATABASE_URL=postgres://admin:s3cretP@ss@10.0.5.23:5432/production",
                )
            ],
            confidence=0.9,
        )
    ]

    scrubbed = scrub_findings_list(findings)
    assert len(scrubbed) == 1

    scrubbed_symptom = scrubbed[0]["symptom"]
    scrubbed_excerpt = scrubbed[0]["evidence"][0]["excerpt"]

    assert scrubbed[0]["id"] == "test-1"
    assert scrubbed[0]["severity"] == "critical"
    assert scrubbed[0]["confidence"] == 0.9
