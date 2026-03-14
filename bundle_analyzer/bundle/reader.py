"""Typed convenience wrappers for reading Kubernetes resources from a bundle.

All bundle file access should go through :class:`BundleIndex` methods.  The
functions here provide higher-level, type-hinted access for common resource
types used by triage scanners and AI analysts.

Every function handles missing data gracefully -- returning empty lists or
``None`` rather than raising exceptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def read_nodes(index: "BundleIndex") -> list[dict]:
    """Return all node objects from the bundle.

    Looks for ``cluster-resources/nodes.json`` (list format) and
    ``cluster-resources/nodes/<name>.json`` (per-node files).

    Args:
        index: A built :class:`BundleIndex`.

    Returns:
        List of node dicts (Kubernetes Node objects).
    """
    nodes: list[dict] = []

    # Single nodes.json file (list or wrapper)
    data = index.read_json("cluster-resources/nodes.json")
    if isinstance(data, list):
        nodes.extend(data)
    elif isinstance(data, dict):
        nodes.extend(data.get("items", []))

    # Per-node files
    nodes_dir = index.root / "cluster-resources" / "nodes"
    if nodes_dir.is_dir():
        for f in sorted(nodes_dir.glob("*.json")):
            node = index.read_json(str(f.relative_to(index.root)))
            if isinstance(node, dict) and "metadata" in node:
                # Avoid duplicates from nodes.json
                name = node.get("metadata", {}).get("name")
                if name and not any(
                    n.get("metadata", {}).get("name") == name for n in nodes
                ):
                    nodes.append(node)

    return nodes


def read_deployments(index: "BundleIndex", namespace: str) -> list[dict]:
    """Return all Deployment objects for a given namespace.

    Args:
        index: A built :class:`BundleIndex`.
        namespace: Kubernetes namespace to look up.

    Returns:
        List of Deployment dicts.
    """
    results: list[dict] = []

    # Per-namespace directory
    ns_dir = index.root / "cluster-resources" / "deployments" / namespace
    if ns_dir.is_dir():
        for f in sorted(ns_dir.glob("*.json")):
            data = index.read_json(str(f.relative_to(index.root)))
            if isinstance(data, dict):
                if "items" in data:
                    results.extend(data["items"])
                else:
                    results.append(data)
            elif isinstance(data, list):
                results.extend(data)

    # Fallback: single deployments.json at cluster-resources level
    if not results:
        data = index.read_json("cluster-resources/deployments.json")
        if isinstance(data, list):
            results = [
                d for d in data
                if d.get("metadata", {}).get("namespace") == namespace
            ]
        elif isinstance(data, dict):
            results = [
                d for d in data.get("items", [])
                if d.get("metadata", {}).get("namespace") == namespace
            ]

    return results


def read_configmaps(index: "BundleIndex", namespace: str) -> list[dict]:
    """Return all ConfigMap objects for a given namespace.

    Args:
        index: A built :class:`BundleIndex`.
        namespace: Kubernetes namespace to look up.

    Returns:
        List of ConfigMap dicts.
    """
    results: list[dict] = []

    ns_dir = index.root / "cluster-resources" / "configmaps" / namespace
    if ns_dir.is_dir():
        for f in sorted(ns_dir.glob("*.json")):
            data = index.read_json(str(f.relative_to(index.root)))
            if isinstance(data, dict):
                if "items" in data:
                    results.extend(data["items"])
                else:
                    results.append(data)
            elif isinstance(data, list):
                results.extend(data)

    # Fallback
    if not results:
        data = index.read_json("cluster-resources/configmaps.json")
        if isinstance(data, list):
            results = [
                c for c in data
                if c.get("metadata", {}).get("namespace") == namespace
            ]
        elif isinstance(data, dict):
            results = [
                c for c in data.get("items", [])
                if c.get("metadata", {}).get("namespace") == namespace
            ]

    return results


def read_pod_spec(
    index: "BundleIndex", namespace: str, pod: str
) -> dict | None:
    """Return the full pod object for a specific pod.

    Args:
        index: A built :class:`BundleIndex`.
        namespace: Kubernetes namespace.
        pod: Pod name.

    Returns:
        Pod dict or ``None`` if not found.
    """
    # Try direct file
    data = index.read_json(f"cluster-resources/pods/{namespace}/{pod}.json")
    if isinstance(data, dict):
        return data

    # Search through all pods in namespace
    ns_dir = index.root / "cluster-resources" / "pods" / namespace
    if ns_dir.is_dir():
        for f in ns_dir.glob("*.json"):
            content = index.read_json(str(f.relative_to(index.root)))
            if isinstance(content, dict):
                if content.get("metadata", {}).get("name") == pod:
                    return content
                # Might be a list wrapper
                for item in content.get("items", []):
                    if item.get("metadata", {}).get("name") == pod:
                        return item
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("metadata", {}).get("name") == pod:
                        return item

    logger.debug("Pod spec not found: {}/{}", namespace, pod)
    return None
