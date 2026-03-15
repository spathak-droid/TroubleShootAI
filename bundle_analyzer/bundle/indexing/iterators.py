"""Iterator methods for BundleIndex -- pods, events, analysis, preflight."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from bundle_analyzer.bundle.indexing.readers import read_json


def get_all_pods(root: Path) -> Iterator[dict[str, Any]]:
    """Yield every pod JSON object found in the bundle.

    Walks ``cluster-resources/pods/<namespace>/<pod>.json`` and yields
    the parsed dict for each file.

    Args:
        root: Bundle root directory.

    Yields:
        Pod resource dicts.
    """
    pods_dir = root / "cluster-resources" / "pods"
    if not pods_dir.is_dir():
        return
    for ns_dir in sorted(pods_dir.iterdir()):
        if not ns_dir.is_dir():
            # Might be a single pods.json list
            if ns_dir.suffix == ".json":
                data = read_json(root, str(ns_dir.relative_to(root)))
                if isinstance(data, list):
                    yield from data
                elif isinstance(data, dict):
                    yield from (data.get("items") or [])
            continue
        for pod_file in sorted(ns_dir.glob("*.json")):
            data = read_json(root, str(pod_file.relative_to(root)))
            if data is None:
                continue
            if isinstance(data, dict):
                # Could be a single pod or a list wrapper
                if "items" in data:
                    items = data["items"]
                    if isinstance(items, list):
                        yield from items
                else:
                    yield data
            elif isinstance(data, list):
                yield from data


def get_events(root: Path, namespace: str | None = None) -> list[dict[str, Any]]:
    """Return cluster events, optionally filtered by namespace.

    Args:
        root: Bundle root directory.
        namespace: If provided, only return events from this namespace.

    Returns:
        List of event dicts, most-recent first.
    """
    events: list[dict[str, Any]] = []
    events_dir = root / "cluster-resources" / "events"
    if not events_dir.is_dir():
        return events

    for f in sorted(events_dir.glob("*.json")):
        ns_name = f.stem  # filename is typically <namespace>.json
        if namespace and ns_name != namespace:
            continue
        data = read_json(root, str(f.relative_to(root)))
        if isinstance(data, list):
            events.extend(data)
        elif isinstance(data, dict):
            events.extend(data.get("items") or [])

    # Sort by lastTimestamp descending (if available)
    def _sort_key(ev: dict[str, Any]) -> str:
        return ev.get("lastTimestamp") or ev.get("metadata", {}).get("creationTimestamp") or ""

    events.sort(key=_sort_key, reverse=True)
    return events


def read_existing_analysis(root: Path, read_json_fn: Callable[[str], dict[str, Any] | list[Any] | None]) -> list[dict[str, Any]]:
    """Read the bundle's own analysis results, if present.

    Troubleshoot bundles may contain ``analysis.json`` with pre-computed
    analysis from the collector's analyzers.

    Args:
        root: Bundle root directory.
        read_json_fn: Bound read_json method from BundleIndex.

    Returns:
        List of analysis result dicts, or empty list.
    """
    for candidate in ("analysis.json", "analyzers/analysis.json"):
        data = read_json_fn(candidate)
        if data is not None:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", data.get("analyses", [data]))
    return []


def read_preflight_results(root: Path, read_json_fn: Callable[[str], dict[str, Any] | list[Any] | None]) -> list[dict[str, Any]]:
    """Read preflight check results from the bundle, if present.

    Checks common locations: ``preflight.json``, ``host-preflight.json``,
    ``preflights/results.json``.

    Args:
        root: Bundle root directory.
        read_json_fn: Bound read_json method from BundleIndex.

    Returns:
        List of preflight result dicts, or empty list.
    """
    for candidate in ("preflight.json", "host-preflight.json", "preflights/results.json"):
        data = read_json_fn(candidate)
        if data is not None:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", data.get("results", [data]))
    return []
