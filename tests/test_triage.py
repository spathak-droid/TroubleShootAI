"""Tests for the triage engine and individual scanners."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.triage.config_scanner import ConfigScanner
from bundle_analyzer.triage.deployment_scanner import DeploymentScanner
from bundle_analyzer.triage.engine import TriageEngine
from bundle_analyzer.triage.event_scanner import EventScanner
from bundle_analyzer.triage.node_scanner import NodeScanner
from bundle_analyzer.triage.pod_scanner import PodScanner
from bundle_analyzer.triage.silence_scanner import SilenceScanner

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


@pytest_asyncio.fixture
async def index() -> BundleIndex:
    """Build a BundleIndex from the sample bundle fixture."""
    return await BundleIndex.build(SAMPLE_BUNDLE)


# ══════════════════════════════════════════════════════════════════════
# PodScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pod_scanner_crashloop(index: BundleIndex) -> None:
    """PodScanner should detect CrashLoopBackOff pods."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    crashloop_issues = [i for i in issues if i.issue_type == "CrashLoopBackOff"]
    assert len(crashloop_issues) >= 1
    names = [i.pod_name for i in crashloop_issues]
    assert "crashloop-pod" in names


@pytest.mark.asyncio
async def test_pod_scanner_oomkilled(index: BundleIndex) -> None:
    """PodScanner should detect OOMKilled pods."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    oom_issues = [i for i in issues if i.issue_type == "OOMKilled"]
    assert len(oom_issues) >= 1
    names = [i.pod_name for i in oom_issues]
    assert "oom-pod" in names


@pytest.mark.asyncio
async def test_pod_scanner_imagepullbackoff(index: BundleIndex) -> None:
    """PodScanner should detect ImagePullBackOff pods."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    img_issues = [i for i in issues if i.issue_type == "ImagePullBackOff"]
    assert len(img_issues) >= 1
    names = [i.pod_name for i in img_issues]
    assert "imagepull-pod" in names


@pytest.mark.asyncio
async def test_pod_scanner_pending(index: BundleIndex) -> None:
    """PodScanner should detect Pending pods that have been stuck."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    pending_issues = [i for i in issues if i.issue_type == "Pending"]
    assert len(pending_issues) >= 1
    names = [i.pod_name for i in pending_issues]
    assert "pending-pod" in names


@pytest.mark.asyncio
async def test_pod_scanner_high_restart_count(index: BundleIndex) -> None:
    """PodScanner should detect pods with high restart count even if currently healthy."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    high_restart = [i for i in issues if i.pod_name == "highrestart-pod"]
    assert len(high_restart) >= 1
    assert high_restart[0].restart_count == 10


@pytest.mark.asyncio
async def test_pod_scanner_no_false_positives_healthy(index: BundleIndex) -> None:
    """PodScanner should NOT flag healthy-pod or sample-pod."""
    scanner = PodScanner()
    issues = await scanner.scan(index)
    flagged_names = {i.pod_name for i in issues}
    assert "healthy-pod" not in flagged_names
    assert "sample-pod" not in flagged_names


@pytest.mark.asyncio
async def test_pod_scanner_returns_list(index: BundleIndex) -> None:
    """PodScanner.scan should always return a list."""
    scanner = PodScanner()
    result = await scanner.scan(index)
    assert isinstance(result, list)


# ══════════════════════════════════════════════════════════════════════
# NodeScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_node_scanner_memory_pressure(index: BundleIndex) -> None:
    """NodeScanner should detect MemoryPressure condition."""
    scanner = NodeScanner()
    issues = await scanner.scan(index)
    mem_issues = [i for i in issues if i.condition == "MemoryPressure"]
    assert len(mem_issues) >= 1
    assert mem_issues[0].node_name == "ip-10-0-2-88.ec2.internal"
    assert "memory pressure" in mem_issues[0].message.lower()


@pytest.mark.asyncio
async def test_node_scanner_not_ready(index: BundleIndex) -> None:
    """NodeScanner should detect NotReady condition."""
    scanner = NodeScanner()
    issues = await scanner.scan(index)
    not_ready = [i for i in issues if i.condition == "NotReady"]
    assert len(not_ready) >= 1
    assert not_ready[0].node_name == "ip-10-0-3-12.ec2.internal"


@pytest.mark.asyncio
async def test_node_scanner_no_false_positive_healthy(index: BundleIndex) -> None:
    """NodeScanner should NOT flag kind-worker which is healthy."""
    scanner = NodeScanner()
    issues = await scanner.scan(index)
    flagged_nodes = {i.node_name for i in issues}
    assert "ip-10-0-1-45.ec2.internal" not in flagged_nodes


# ══════════════════════════════════════════════════════════════════════
# DeploymentScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deployment_scanner_replica_mismatch(index: BundleIndex) -> None:
    """DeploymentScanner should detect replica mismatches."""
    scanner = DeploymentScanner()
    issues = await scanner.scan(index)
    mismatch = [i for i in issues if i.name == "broken-deploy"]
    assert len(mismatch) >= 1
    assert mismatch[0].desired_replicas == 3
    assert mismatch[0].ready_replicas == 1


@pytest.mark.asyncio
async def test_deployment_scanner_no_false_positive_healthy(index: BundleIndex) -> None:
    """DeploymentScanner should NOT flag healthy-deploy."""
    scanner = DeploymentScanner()
    issues = await scanner.scan(index)
    flagged_names = {i.name for i in issues}
    assert "healthy-deploy" not in flagged_names


# ══════════════════════════════════════════════════════════════════════
# EventScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_event_scanner_warning_events(index: BundleIndex) -> None:
    """EventScanner should return Warning events."""
    scanner = EventScanner()
    events = await scanner.scan(index)
    assert len(events) >= 2  # BackOff + Failed events
    event_types = {e.type for e in events}
    assert event_types == {"Warning"}  # Only warnings returned


@pytest.mark.asyncio
async def test_event_scanner_sorted_by_time(index: BundleIndex) -> None:
    """EventScanner should return events sorted most-recent first."""
    scanner = EventScanner()
    events = await scanner.scan(index)
    if len(events) >= 2:
        # Check descending order
        for i in range(len(events) - 1):
            ts_a = events[i].last_timestamp
            ts_b = events[i + 1].last_timestamp
            if ts_a is not None and ts_b is not None:
                assert ts_a >= ts_b


@pytest.mark.asyncio
async def test_event_scanner_no_normal_events(index: BundleIndex) -> None:
    """EventScanner should NOT include Normal events."""
    scanner = EventScanner()
    events = await scanner.scan(index)
    normal_events = [e for e in events if e.type == "Normal"]
    assert len(normal_events) == 0


# ══════════════════════════════════════════════════════════════════════
# ConfigScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_config_scanner_missing_configmap(index: BundleIndex) -> None:
    """ConfigScanner should detect missing ConfigMap references."""
    scanner = ConfigScanner()
    issues = await scanner.scan(index)
    missing_cms = [
        i for i in issues
        if i.resource_type == "ConfigMap" and i.issue == "missing"
    ]
    assert len(missing_cms) >= 1
    missing_names = [i.resource_name for i in missing_cms]
    assert "missing-config" in missing_names


@pytest.mark.asyncio
async def test_config_scanner_returns_list(index: BundleIndex) -> None:
    """ConfigScanner.scan should always return a list."""
    scanner = ConfigScanner()
    result = await scanner.scan(index)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_config_scanner_also_missing_volume_configmap(index: BundleIndex) -> None:
    """ConfigScanner should detect missing ConfigMap referenced by volume."""
    scanner = ConfigScanner()
    issues = await scanner.scan(index)
    missing_names = [i.resource_name for i in issues if i.resource_type == "ConfigMap"]
    assert "also-missing-config" in missing_names


# ══════════════════════════════════════════════════════════════════════
# SilenceScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_silence_scanner_returns_list(index: BundleIndex) -> None:
    """SilenceScanner.scan should always return a list."""
    scanner = SilenceScanner()
    result = await scanner.scan(index)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_silence_scanner_missing_log_for_running_pod(index: BundleIndex) -> None:
    """SilenceScanner should detect running pods without log files."""
    scanner = SilenceScanner()
    signals = await scanner.scan(index)
    # Running pods without log files in our fixture should trigger LOG_FILE_MISSING
    log_missing = [s for s in signals if s.signal_type == "LOG_FILE_MISSING"]
    # Our fixture has multiple running pods with no log directories
    assert len(log_missing) >= 1


# ══════════════════════════════════════════════════════════════════════
# TriageEngine tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_triage_engine_runs(index: BundleIndex) -> None:
    """TriageEngine.run should produce a TriageResult with findings."""
    engine = TriageEngine()
    result = await engine.run(index)

    # Should have critical pods (CrashLoopBackOff + OOMKilled)
    assert len(result.critical_pods) >= 1
    critical_types = {p.issue_type for p in result.critical_pods}
    assert "CrashLoopBackOff" in critical_types or "OOMKilled" in critical_types

    # Should have config issues
    assert len(result.config_issues) >= 1


@pytest.mark.asyncio
async def test_triage_engine_has_node_issues(index: BundleIndex) -> None:
    """TriageEngine should populate node_issues from NodeScanner."""
    engine = TriageEngine()
    result = await engine.run(index)
    assert len(result.node_issues) >= 2  # MemoryPressure + NotReady


@pytest.mark.asyncio
async def test_triage_engine_has_deployment_issues(index: BundleIndex) -> None:
    """TriageEngine should populate deployment_issues from DeploymentScanner."""
    engine = TriageEngine()
    result = await engine.run(index)
    assert len(result.deployment_issues) >= 1


@pytest.mark.asyncio
async def test_triage_engine_has_warning_events(index: BundleIndex) -> None:
    """TriageEngine should populate warning_events from EventScanner."""
    engine = TriageEngine()
    result = await engine.run(index)
    assert len(result.warning_events) >= 1


@pytest.mark.asyncio
async def test_triage_engine_separates_critical_and_warning(index: BundleIndex) -> None:
    """TriageEngine should correctly separate critical from warning pod issues."""
    engine = TriageEngine()
    result = await engine.run(index)

    critical_types = {p.issue_type for p in result.critical_pods}
    warning_types = {p.issue_type for p in result.warning_pods}

    # CrashLoopBackOff and OOMKilled should be critical
    for ct in critical_types:
        assert ct in {"CrashLoopBackOff", "OOMKilled", "CreateContainerConfigError"}

    # Pending, ImagePullBackOff should be warning
    for wt in warning_types:
        assert wt not in {"CrashLoopBackOff", "OOMKilled", "CreateContainerConfigError"}
