"""Tests for the ResourceGraph module using the demo bundle."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.graph import ResourceEdge, ResourceGraph, ResourceNode

DEMO_BUNDLE = Path(__file__).parent.parent / "demo-bundle"


@pytest_asyncio.fixture
async def index() -> BundleIndex:
    """Build a BundleIndex from the demo bundle."""
    return await BundleIndex.build(DEMO_BUNDLE)


@pytest_asyncio.fixture
async def graph(index: BundleIndex) -> ResourceGraph:
    """Build a ResourceGraph from the demo bundle index."""
    return await ResourceGraph.build(index)


# ── Node creation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_has_pod_nodes(graph: ResourceGraph) -> None:
    """All 8 demo pods should appear as nodes."""
    pod_nodes = [n for n in graph.nodes.values() if n.kind == "Pod"]
    assert len(pod_nodes) == 8


@pytest.mark.asyncio
async def test_graph_has_node_node(graph: ResourceGraph) -> None:
    """The control-plane node should be registered (from pod.spec.nodeName)."""
    node = graph.get_node("Node//bundle-analyzer-demo-control-plane")
    assert node is not None
    assert node.kind == "Node"
    assert node.name == "bundle-analyzer-demo-control-plane"


@pytest.mark.asyncio
async def test_get_node_returns_none_for_missing(graph: ResourceGraph) -> None:
    """get_node on a non-existent key returns None."""
    assert graph.get_node("Pod/default/does-not-exist") is None


# ── Pod → Node edges ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pod_scheduled_on_node(graph: ResourceGraph) -> None:
    """Every demo pod should have a scheduled_on edge to the control-plane node."""
    pod_nodes = [n for n in graph.nodes.values() if n.kind == "Pod"]
    for pod in pod_nodes:
        targets = graph.neighbors(pod.key, relation="scheduled_on")
        assert len(targets) >= 1, f"{pod.key} has no scheduled_on edge"
        assert targets[0].kind == "Node"


@pytest.mark.asyncio
async def test_pods_on_node(graph: ResourceGraph) -> None:
    """pods_on_node should return all pods scheduled on the control-plane."""
    pods = graph.pods_on_node("bundle-analyzer-demo-control-plane")
    assert len(pods) == 8
    assert all(p.kind == "Pod" for p in pods)


# ── Owner chain ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_chain_pod_to_replicaset(graph: ResourceGraph) -> None:
    """A pod owned by a ReplicaSet should have at least one owner in the chain."""
    pod = graph.get_node("Pod/default/break-bad-probe-84fd687d57-5fc6f")
    assert pod is not None
    chain = graph.owner_chain(pod.key)
    assert len(chain) >= 1
    assert chain[0].kind == "ReplicaSet"
    assert chain[0].name == "break-bad-probe-84fd687d57"


@pytest.mark.asyncio
async def test_owned_by_edges_exist(graph: ResourceGraph) -> None:
    """Pods with ownerReferences should have owned_by edges."""
    pod_key = "Pod/default/healthy-nginx-d5c6847bd-d8nwf"
    owners = graph.neighbors(pod_key, relation="owned_by")
    assert len(owners) >= 1
    assert owners[0].kind == "ReplicaSet"


# ── ServiceAccount edges ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_account_edge(graph: ResourceGraph) -> None:
    """Pods should have uses_service_account edges."""
    pod_key = "Pod/default/healthy-nginx-d5c6847bd-d8nwf"
    sa_targets = graph.neighbors(pod_key, relation="uses_service_account")
    assert len(sa_targets) >= 1
    assert sa_targets[0].kind == "ServiceAccount"


# ── Reverse neighbors ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reverse_neighbors(graph: ResourceGraph) -> None:
    """A ReplicaSet node should have reverse owned_by edges from its pods."""
    rs_key = "ReplicaSet/default/break-bad-probe-84fd687d57"
    dependents = graph.reverse_neighbors(rs_key, relation="owned_by")
    assert len(dependents) >= 1
    assert all(d.kind == "Pod" for d in dependents)


# ── Dependents ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dependents(graph: ResourceGraph) -> None:
    """dependents() should return all nodes referencing the target."""
    node_key = "Node//bundle-analyzer-demo-control-plane"
    deps = graph.dependents(node_key)
    assert len(deps) == 8  # all 8 pods


# ── Blast radius ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blast_radius_node(graph: ResourceGraph) -> None:
    """Blast radius of the only node should include all pods."""
    node_key = "Node//bundle-analyzer-demo-control-plane"
    affected = graph.blast_radius(node_key)
    pod_names = {n.name for n in affected if n.kind == "Pod"}
    assert len(pod_names) == 8


# ── Model tests ──────────────────────────────────────────────────────


def test_resource_node_model() -> None:
    """ResourceNode should be a valid Pydantic model."""
    node = ResourceNode(kind="Pod", namespace="default", name="test", key="Pod/default/test", raw={})
    assert node.kind == "Pod"
    assert node.model_dump()["key"] == "Pod/default/test"


def test_resource_edge_model() -> None:
    """ResourceEdge should be a valid Pydantic model."""
    edge = ResourceEdge(source="Pod/default/a", target="Node//b", relation="scheduled_on")
    assert edge.relation == "scheduled_on"
    dumped = edge.model_dump()
    assert dumped["source"] == "Pod/default/a"


# ── Graph repr ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_graph_repr(graph: ResourceGraph) -> None:
    """repr should show node and edge counts."""
    r = repr(graph)
    assert "ResourceGraph" in r
    assert "nodes=" in r
    assert "edges=" in r
