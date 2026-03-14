"""End-to-end integration tests for the Bundle Analyzer.

These tests wire together the real index + triage pipeline (no mocks)
against the fixture bundle to verify the full deterministic path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import TriageResult
from bundle_analyzer.triage.engine import TriageEngine

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


@pytest_asyncio.fixture
async def index() -> BundleIndex:
    """Build a BundleIndex from the sample bundle fixture."""
    return await BundleIndex.build(SAMPLE_BUNDLE)


@pytest_asyncio.fixture
async def triage_result(index: BundleIndex) -> TriageResult:
    """Run the full triage engine on the sample bundle."""
    engine = TriageEngine()
    return await engine.run(index)


# ══════════════════════════════════════════════════════════════════════
# End-to-end: index -> triage -> verify
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_e2e_index_to_triage(triage_result: TriageResult) -> None:
    """Full pipeline: build index from fixture, run triage, verify findings exist."""
    assert isinstance(triage_result, TriageResult)

    # Must find at least some issues
    total_findings = (
        len(triage_result.critical_pods)
        + len(triage_result.warning_pods)
        + len(triage_result.node_issues)
        + len(triage_result.deployment_issues)
        + len(triage_result.config_issues)
    )
    assert total_findings >= 5, f"Expected at least 5 findings, got {total_findings}"


@pytest.mark.asyncio
async def test_e2e_triage_result_has_expected_fields(triage_result: TriageResult) -> None:
    """TriageResult should have all expected fields populated."""
    # Required list fields should exist (even if empty for some)
    assert isinstance(triage_result.critical_pods, list)
    assert isinstance(triage_result.warning_pods, list)
    assert isinstance(triage_result.node_issues, list)
    assert isinstance(triage_result.deployment_issues, list)
    assert isinstance(triage_result.config_issues, list)
    assert isinstance(triage_result.drift_issues, list)
    assert isinstance(triage_result.silence_signals, list)
    assert isinstance(triage_result.warning_events, list)
    assert isinstance(triage_result.rbac_errors, list)
    assert isinstance(triage_result.existing_analysis, list)


@pytest.mark.asyncio
async def test_e2e_findings_properly_categorized(triage_result: TriageResult) -> None:
    """Critical vs warning pods should be categorized by issue type."""
    critical_types = {p.issue_type for p in triage_result.critical_pods}
    warning_types = {p.issue_type for p in triage_result.warning_pods}

    # CrashLoopBackOff and OOMKilled must be in critical
    expected_critical = {"CrashLoopBackOff", "OOMKilled"}
    found_critical = critical_types & expected_critical
    assert len(found_critical) >= 1, f"Expected at least one of {expected_critical} in critical, got {critical_types}"

    # ImagePullBackOff and Pending should be in warning (not critical)
    for wt in warning_types:
        assert wt not in {"CrashLoopBackOff", "OOMKilled", "CreateContainerConfigError"}, (
            f"Warning pod has critical type: {wt}"
        )


@pytest.mark.asyncio
async def test_e2e_specific_findings_present(triage_result: TriageResult) -> None:
    """Verify specific known fixture issues are detected."""
    # CrashLoopBackOff pod
    crash_pods = [p for p in triage_result.critical_pods if p.pod_name == "crashloop-pod"]
    assert len(crash_pods) >= 1

    # OOMKilled pod
    oom_pods = [p for p in triage_result.critical_pods if p.pod_name == "oom-pod"]
    assert len(oom_pods) >= 1

    # ImagePullBackOff pod (warning)
    img_pods = [p for p in triage_result.warning_pods if p.pod_name == "imagepull-pod"]
    assert len(img_pods) >= 1

    # Pending pod (warning)
    pending_pods = [p for p in triage_result.warning_pods if p.pod_name == "pending-pod"]
    assert len(pending_pods) >= 1

    # Missing ConfigMap
    config_issues = [c for c in triage_result.config_issues if c.resource_name == "missing-config"]
    assert len(config_issues) >= 1

    # Node MemoryPressure
    mem_nodes = [n for n in triage_result.node_issues if n.condition == "MemoryPressure"]
    assert len(mem_nodes) >= 1

    # Node NotReady
    notready_nodes = [n for n in triage_result.node_issues if n.condition == "NotReady"]
    assert len(notready_nodes) >= 1

    # Deployment replica mismatch
    deploy_issues = [d for d in triage_result.deployment_issues if d.name == "broken-deploy"]
    assert len(deploy_issues) >= 1

    # Warning events
    assert len(triage_result.warning_events) >= 2


@pytest.mark.asyncio
async def test_e2e_pod_issue_fields(triage_result: TriageResult) -> None:
    """PodIssue objects should have required fields properly set."""
    all_pods = triage_result.critical_pods + triage_result.warning_pods
    for pod in all_pods:
        assert pod.namespace, "PodIssue.namespace must be set"
        assert pod.pod_name, "PodIssue.pod_name must be set"
        assert pod.issue_type, "PodIssue.issue_type must be set"


@pytest.mark.asyncio
async def test_e2e_node_issue_fields(triage_result: TriageResult) -> None:
    """NodeIssue objects should have required fields properly set."""
    for node in triage_result.node_issues:
        assert node.node_name, "NodeIssue.node_name must be set"
        assert node.condition, "NodeIssue.condition must be set"


@pytest.mark.asyncio
async def test_e2e_deployment_issue_fields(triage_result: TriageResult) -> None:
    """DeploymentIssue objects should have required fields properly set."""
    for dep in triage_result.deployment_issues:
        assert dep.namespace, "DeploymentIssue.namespace must be set"
        assert dep.name, "DeploymentIssue.name must be set"
        assert dep.desired_replicas > 0
        assert dep.issue, "DeploymentIssue.issue must have a description"


@pytest.mark.asyncio
async def test_e2e_index_metadata(index: BundleIndex) -> None:
    """BundleIndex should populate metadata from fixtures."""
    assert index.metadata is not None
    assert index.metadata.bundle_path.is_dir()
    # Our fixture nodes.json has kubeletVersion
    assert index.metadata.kubernetes_version == "v1.28.0"
