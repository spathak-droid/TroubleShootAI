"""Tests for the new Phase 7B triage scanners: probe, resource, ingress, storage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.triage.ingress_scanner import IngressScanner
from bundle_analyzer.triage.probe_scanner import ProbeScanner
from bundle_analyzer.triage.resource_scanner import ResourceScanner
from bundle_analyzer.triage.storage_scanner import StorageScanner

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"
DEMO_BUNDLE = Path(__file__).parent.parent / "demo-bundle"


@pytest_asyncio.fixture
async def index() -> BundleIndex:
    """Build a BundleIndex from the sample bundle fixture."""
    return await BundleIndex.build(SAMPLE_BUNDLE)


@pytest_asyncio.fixture
async def demo_index() -> BundleIndex:
    """Build a BundleIndex from the demo bundle (has richer data)."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip("demo-bundle not present")
    return await BundleIndex.build(DEMO_BUNDLE)


# ══════════════════════════════════════════════════════════════════════
# ProbeScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_probe_scanner_bad_path(index: BundleIndex) -> None:
    """ProbeScanner should detect the bad-probe-pod with suspicious liveness path."""
    scanner = ProbeScanner()
    issues = await scanner.scan(index)
    bad_path_issues = [i for i in issues if i.issue == "bad_path"]
    assert len(bad_path_issues) >= 1
    pod_names = [i.pod_name for i in bad_path_issues]
    assert "bad-probe-pod" in pod_names


@pytest.mark.asyncio
async def test_probe_scanner_demo_bundle_bad_probe(demo_index: BundleIndex) -> None:
    """ProbeScanner should detect break-bad-probe pod in the demo bundle."""
    scanner = ProbeScanner()
    issues = await scanner.scan(demo_index)
    bad_path_issues = [i for i in issues if i.issue == "bad_path"]
    pod_names = [i.pod_name for i in bad_path_issues]
    # The demo bundle pod name includes a replicaset hash suffix
    matching = [n for n in pod_names if n.startswith("break-bad-probe")]
    assert len(matching) >= 1, f"Expected break-bad-probe pod, got: {pod_names}"


@pytest.mark.asyncio
async def test_probe_scanner_no_readiness(index: BundleIndex) -> None:
    """ProbeScanner should flag pods with liveness but no readiness probe."""
    scanner = ProbeScanner()
    issues = await scanner.scan(index)
    no_readiness = [i for i in issues if i.issue == "no_readiness_probe"]
    # bad-probe-pod has liveness but no readiness
    pod_names = [i.pod_name for i in no_readiness]
    assert "bad-probe-pod" in pod_names


@pytest.mark.asyncio
async def test_probe_scanner_empty_bundle() -> None:
    """ProbeScanner should return empty list when bundle has no pods."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.get_all_pods.return_value = iter([])
    scanner = ProbeScanner()
    issues = await scanner.scan(mock_index)
    assert issues == []


# ══════════════════════════════════════════════════════════════════════
# ResourceScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resource_scanner_no_limits(index: BundleIndex) -> None:
    """ResourceScanner should detect pods without resource limits."""
    scanner = ResourceScanner()
    issues = await scanner.scan(index)
    no_limits = [i for i in issues if i.issue == "no_limits"]
    assert len(no_limits) >= 1
    # no-limits-pod has empty resources
    pod_names = [i.pod_name for i in no_limits]
    assert "no-limits-pod" in pod_names


@pytest.mark.asyncio
async def test_resource_scanner_no_requests(index: BundleIndex) -> None:
    """ResourceScanner should detect pods without resource requests."""
    scanner = ResourceScanner()
    issues = await scanner.scan(index)
    no_requests = [i for i in issues if i.issue == "no_requests"]
    assert len(no_requests) >= 1
    pod_names = [i.pod_name for i in no_requests]
    assert "no-limits-pod" in pod_names


@pytest.mark.asyncio
async def test_resource_scanner_besteffort(index: BundleIndex) -> None:
    """ResourceScanner should detect BestEffort QoS class."""
    scanner = ResourceScanner()
    issues = await scanner.scan(index)
    besteffort = [
        i for i in issues
        if i.issue == "no_limits" and "BestEffort" in i.message
    ]
    assert len(besteffort) >= 1


@pytest.mark.asyncio
async def test_resource_scanner_empty_bundle() -> None:
    """ResourceScanner should return empty list when bundle has no pods."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.get_all_pods.return_value = iter([])
    mock_index.read_json.return_value = None
    mock_index.root = Path("/nonexistent")
    scanner = ResourceScanner()
    issues = await scanner.scan(mock_index)
    assert issues == []


# ══════════════════════════════════════════════════════════════════════
# IngressScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ingress_scanner_empty_bundle() -> None:
    """IngressScanner should return empty list when bundle has no ingresses."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.namespaces = ["default"]
    mock_index.read_json.return_value = None
    scanner = IngressScanner()
    issues = await scanner.scan(mock_index)
    assert issues == []


@pytest.mark.asyncio
async def test_ingress_scanner_missing_service() -> None:
    """IngressScanner should detect ingress referencing a missing service."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.namespaces = ["default"]

    ingress_data = {
        "items": [
            {
                "metadata": {"name": "test-ingress", "namespace": "default"},
                "spec": {
                    "rules": [
                        {
                            "http": {
                                "paths": [
                                    {
                                        "path": "/",
                                        "backend": {
                                            "service": {
                                                "name": "nonexistent-svc",
                                                "port": {"number": 80},
                                            }
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
            }
        ]
    }

    def mock_read_json(path: str) -> dict | list | None:
        if "ingress" in path:
            return ingress_data
        if "services" in path:
            return {"items": []}
        if "secrets" in path:
            return {"items": []}
        return None

    mock_index.read_json.side_effect = mock_read_json
    scanner = IngressScanner()
    issues = await scanner.scan(mock_index)
    assert len(issues) >= 1
    assert issues[0].issue == "missing_service"
    assert "nonexistent-svc" in issues[0].message


# ══════════════════════════════════════════════════════════════════════
# StorageScanner tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_storage_scanner_empty_bundle() -> None:
    """StorageScanner should return empty list when bundle has no storage resources."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.namespaces = ["default"]
    mock_index.read_json.return_value = None
    mock_index.root = Path("/nonexistent")
    scanner = StorageScanner()
    issues = await scanner.scan(mock_index)
    assert issues == []


@pytest.mark.asyncio
async def test_storage_scanner_pending_pvc() -> None:
    """StorageScanner should detect PVCs in Pending phase."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.namespaces = ["default"]
    mock_index.root = Path("/nonexistent")

    pvc_data = {
        "items": [
            {
                "metadata": {"name": "data-pvc", "namespace": "default"},
                "spec": {"storageClassName": "standard"},
                "status": {"phase": "Pending"},
            }
        ]
    }

    def mock_read_json(path: str) -> dict | list | None:
        if "pvcs" in path:
            return pvc_data
        if "storage-classes" in path or "storageclasses" in path:
            return {"items": [{"metadata": {"name": "standard"}}]}
        return None

    mock_index.read_json.side_effect = mock_read_json
    scanner = StorageScanner()
    issues = await scanner.scan(mock_index)
    pending = [i for i in issues if i.issue == "pending"]
    assert len(pending) >= 1
    assert pending[0].resource_name == "data-pvc"


@pytest.mark.asyncio
async def test_storage_scanner_missing_storage_class() -> None:
    """StorageScanner should detect PVCs referencing nonexistent StorageClass."""
    mock_index = MagicMock(spec=BundleIndex)
    mock_index.namespaces = ["default"]
    mock_index.root = Path("/nonexistent")

    pvc_data = {
        "items": [
            {
                "metadata": {"name": "data-pvc", "namespace": "default"},
                "spec": {"storageClassName": "super-fast-ssd"},
                "status": {"phase": "Pending"},
            }
        ]
    }

    def mock_read_json(path: str) -> dict | list | None:
        if "pvcs" in path:
            return pvc_data
        if "storage-classes" in path or "storageclasses" in path:
            return {"items": [{"metadata": {"name": "standard"}}]}
        return None

    mock_index.read_json.side_effect = mock_read_json
    scanner = StorageScanner()
    issues = await scanner.scan(mock_index)
    missing_sc = [i for i in issues if i.issue == "missing_storage_class"]
    assert len(missing_sc) >= 1
    assert "super-fast-ssd" in missing_sc[0].message
