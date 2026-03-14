"""Tests for bundle extraction, indexing, and reading."""

from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.extractor import BundleExtractor
from bundle_analyzer.bundle.indexer import BundleIndex

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


@pytest.fixture
def sample_bundle_path() -> Path:
    """Return the path to the sample bundle fixture directory."""
    return SAMPLE_BUNDLE


@pytest_asyncio.fixture
async def index(sample_bundle_path: Path) -> BundleIndex:
    """Build a BundleIndex from the sample bundle fixture."""
    return await BundleIndex.build(sample_bundle_path)


# ── Tar extraction tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_tar_gz() -> None:
    """BundleExtractor should extract a programmatically created .tar.gz."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # Create a small bundle structure inside a sub-directory
        bundle_dir = tmp / "my-bundle"
        pods_dir = bundle_dir / "cluster-resources" / "pods" / "default"
        pods_dir.mkdir(parents=True)
        pod_file = pods_dir / "test-pod.json"
        pod_file.write_text(json.dumps({
            "metadata": {"name": "test-pod", "namespace": "default"},
            "spec": {"containers": [{"name": "main", "image": "nginx"}]},
            "status": {"phase": "Running", "containerStatuses": [
                {"name": "main", "ready": True, "restartCount": 0}
            ]},
        }))

        # Create a tar.gz
        tar_path = tmp / "bundle.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(bundle_dir, arcname="my-bundle")

        # Extract using BundleExtractor
        async with BundleExtractor() as extractor:
            root = await extractor.extract(tar_path)
            assert root.is_dir()
            # The single top-level dir should be unwrapped
            assert (root / "cluster-resources" / "pods" / "default" / "test-pod.json").is_file()


@pytest.mark.asyncio
async def test_extract_nonexistent_bundle() -> None:
    """BundleExtractor.extract should raise FileNotFoundError for missing file."""
    async with BundleExtractor() as extractor:
        with pytest.raises(FileNotFoundError):
            await extractor.extract(Path("/nonexistent/bundle.tar.gz"))


# ── BundleIndex build tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_index(sample_bundle_path: Path) -> None:
    """BundleIndex.build should produce a valid index from a fixture directory."""
    index = await BundleIndex.build(sample_bundle_path)
    assert index is not None
    assert index.root == sample_bundle_path.resolve()
    assert "default" in index.namespaces


@pytest.mark.asyncio
async def test_build_index_not_a_dir() -> None:
    """BundleIndex.build should raise NotADirectoryError for invalid path."""
    with pytest.raises(NotADirectoryError):
        await BundleIndex.build(Path("/nonexistent/path"))


# ── read_json tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_json_valid(index: BundleIndex) -> None:
    """read_json should return parsed data for an existing JSON file."""
    data = index.read_json("cluster-resources/namespaces.json")
    assert data is not None
    assert "items" in data
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_read_json_missing(index: BundleIndex) -> None:
    """read_json should return None for a nonexistent file."""
    data = index.read_json("cluster-resources/nonexistent.json")
    assert data is None


@pytest.mark.asyncio
async def test_read_json_malformed(index: BundleIndex) -> None:
    """read_json should return None for a malformed JSON file."""
    # Create a malformed JSON file temporarily
    malformed = index.root / "malformed.json"
    malformed.write_text("{this is not valid json!!!}")
    try:
        data = index.read_json("malformed.json")
        assert data is None
    finally:
        malformed.unlink(missing_ok=True)


# ── stream_log tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_log_missing_file(index: BundleIndex) -> None:
    """stream_log should yield nothing for a nonexistent log file."""
    lines = list(index.stream_log("default", "nonexistent-pod", "main"))
    assert lines == []


@pytest.mark.asyncio
async def test_stream_log_existing_file(index: BundleIndex) -> None:
    """stream_log should yield lines from an existing log file."""
    # Create a log file in the expected location
    log_dir = index.root / "default" / "sample-pod"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "main.log"
    log_file.write_text("line1\nline2\nline3\n")
    try:
        lines = list(index.stream_log("default", "sample-pod", "main"))
        assert len(lines) == 3
        assert "line1" in lines
        assert "line3" in lines
    finally:
        log_file.unlink(missing_ok=True)
        log_dir.rmdir()
        (index.root / "default" / "sample-pod").rmdir() if (index.root / "default" / "sample-pod").exists() else None
        (index.root / "default").rmdir() if (index.root / "default").exists() and not list((index.root / "default").iterdir()) else None


# ── get_all_pods tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_pods(index: BundleIndex) -> None:
    """get_all_pods should yield pod dicts from the fixture."""
    pods = list(index.get_all_pods())
    assert len(pods) >= 1
    pod_names = [p.get("metadata", {}).get("name") for p in pods]
    assert "sample-pod" in pod_names


@pytest.mark.asyncio
async def test_get_all_pods_includes_new_fixtures(index: BundleIndex) -> None:
    """get_all_pods should yield our added fixture pods."""
    pods = list(index.get_all_pods())
    pod_names = [p.get("metadata", {}).get("name") for p in pods]
    assert "imagepull-pod" in pod_names
    assert "pending-pod" in pod_names
    assert "healthy-pod" in pod_names
    assert "highrestart-pod" in pod_names


# ── has() tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_has_data(index: BundleIndex) -> None:
    """has() should correctly report available data types."""
    assert index.has("pods") is True
    assert index.has("nonexistent_type") is False


@pytest.mark.asyncio
async def test_has_events(index: BundleIndex) -> None:
    """has() should report events as available."""
    assert index.has("events") is True


@pytest.mark.asyncio
async def test_has_deployments(index: BundleIndex) -> None:
    """has() should report deployments as available."""
    assert index.has("deployments") is True


# ── nodes data ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nodes_data(index: BundleIndex) -> None:
    """read_json should return nodes data with multiple nodes."""
    data = index.read_json("cluster-resources/nodes.json")
    assert data is not None
    items = data.get("items", [])
    assert len(items) >= 3
    names = [n["metadata"]["name"] for n in items]
    assert "ip-10-0-1-45.ec2.internal" in names
    assert "ip-10-0-2-88.ec2.internal" in names
    assert "ip-10-0-3-12.ec2.internal" in names


# ── get_events tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_events(index: BundleIndex) -> None:
    """get_events should return events from the fixture."""
    events = index.get_events()
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_get_events_namespace_filter(index: BundleIndex) -> None:
    """get_events with namespace filter should return only matching events."""
    events = index.get_events(namespace="default")
    assert len(events) >= 1
    events_other = index.get_events(namespace="nonexistent-ns")
    assert len(events_other) == 0
