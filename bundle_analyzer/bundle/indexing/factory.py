"""Factory functions for building a BundleIndex from an extracted bundle."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel

from bundle_analyzer.bundle.indexing.constants import _KNOWN_DIRS

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexing.index import BundleIndex

# ---------------------------------------------------------------------------
# BundleMetadata -- minimal local definition.
# If bundle_analyzer.models already exports BundleMetadata we use that;
# otherwise fall back to the local stub so this module works standalone.
# ---------------------------------------------------------------------------
try:
    from bundle_analyzer.models import BundleMetadata  # type: ignore[import-untyped]
except (ImportError, AttributeError):
    class BundleMetadata(BaseModel):  # type: ignore[no-redef]
        """Minimal bundle metadata (stub until models.py provides the real one)."""
        collected_at: datetime | None = None
        kubernetes_version: str | None = None
        troubleshoot_version: str | None = None
        collection_duration_seconds: float | None = None
        bundle_path: Path = Path(".")


async def build(cls: type[BundleIndex], root: Path) -> BundleIndex:
    """Scan an extracted bundle directory and build the index.

    Args:
        cls: The BundleIndex class to instantiate.
        root: Path to the top-level directory of the extracted bundle.

    Returns:
        A fully-populated :class:`BundleIndex`.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Bundle root is not a directory: {root}")

    return await asyncio.to_thread(build_sync, cls, root)


def build_sync(cls: type[BundleIndex], root: Path) -> BundleIndex:
    """Blocking helper that walks the filesystem.

    Args:
        cls: The BundleIndex class to instantiate.
        root: Resolved path to the extracted bundle directory.

    Returns:
        A fully-populated :class:`BundleIndex`.
    """
    manifest: dict[str, Path] = {}
    namespaces: set[str] = set()
    has_data: dict[str, bool] = {}
    rbac_errors: list[str] = []

    # Walk known directories
    for rel_dir, data_key in _KNOWN_DIRS.items():
        full = root / rel_dir
        if full.is_file():
            manifest[data_key] = full
            has_data[data_key] = True
        elif full.is_dir():
            has_data[data_key] = True
            manifest[data_key] = full
            # Namespace sub-dirs (e.g. cluster-resources/pods/<ns>/)
            for child in full.iterdir():
                if child.is_dir():
                    namespaces.add(child.name)
        else:
            has_data[data_key] = False

    # Discover pod logs -- they live under <root>/<namespace>/<pod>/
    # or <root>/pods/<namespace>/<pod>/
    for candidate in (root, root / "pods"):
        if not candidate.is_dir():
            continue
        for ns_dir in candidate.iterdir():
            if not ns_dir.is_dir():
                continue
            # Check if this looks like a namespace (contains pod dirs with logs)
            for pod_dir in ns_dir.iterdir():
                if pod_dir.is_dir():
                    logs = list(pod_dir.glob("*.log")) + list(pod_dir.glob("**/*.log"))
                    if logs:
                        has_data["pod_logs"] = True
                        namespaces.add(ns_dir.name)

    # Pick up RBAC / collection errors
    errors_dir = root / "cluster-resources" / "errors"
    if errors_dir.is_dir():
        for err_file in errors_dir.rglob("*"):
            if err_file.is_file():
                try:
                    content = err_file.read_text(errors="replace")
                    if content.strip():
                        rbac_errors.append(content.strip())
                except OSError as exc:
                    logger.warning("Could not read error file {}: {}", err_file, exc)

    # Also check for errors.json at bundle root
    errors_json = root / "errors.json"
    if errors_json.is_file():
        try:
            data = json.loads(errors_json.read_text(errors="replace"))
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        rbac_errors.append(entry.get("error", str(entry)))
                    elif isinstance(entry, str):
                        rbac_errors.append(entry)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not parse errors.json: {}", exc)

    # Check for preflight results
    for pf_candidate in ("preflight.json", "host-preflight.json", "preflights/results.json"):
        pf_path = root / pf_candidate
        if pf_path.is_file():
            key = pf_candidate.replace(".json", "").replace("/", "_").replace("-", "_")
            has_data[key] = True
            manifest[key] = pf_path

    # Build metadata
    metadata = parse_metadata(root)

    sorted_ns = sorted(namespaces)
    logger.info(
        "Indexed bundle: {} namespaces, {} data types, {} RBAC errors",
        len(sorted_ns),
        sum(1 for v in has_data.values() if v),
        len(rbac_errors),
    )

    return cls(
        root=root,
        manifest=manifest,
        namespaces=sorted_ns,
        has_data=has_data,
        rbac_errors=rbac_errors,
        metadata=metadata,
    )


def parse_metadata(root: Path) -> BundleMetadata:
    """Extract bundle metadata from version.yaml or similar files.

    Args:
        root: Path to the extracted bundle root directory.

    Returns:
        Populated :class:`BundleMetadata` instance.
    """
    collected_at: datetime | None = None
    k8s_version: str | None = None
    ts_version: str | None = None
    duration: float | None = None

    # version.yaml (troubleshoot collector metadata)
    version_file = root / "version.yaml"
    if version_file.is_file():
        try:
            content = version_file.read_text(errors="replace")
            for line in content.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("collectedAt:"):
                    ts_str = line_stripped.split(":", 1)[1].strip().strip('"')
                    try:
                        collected_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                elif line_stripped.startswith("troubleshootVersion:"):
                    ts_version = line_stripped.split(":", 1)[1].strip().strip('"')
        except OSError:
            pass

    # Try to get k8s version from cluster-info or nodes
    cluster_info = root / "cluster-info" / "cluster_version.json"
    if cluster_info.is_file():
        try:
            data = json.loads(cluster_info.read_text(errors="replace"))
            k8s_version = data.get("serverVersion", {}).get("gitVersion")
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: nodes.json
    if k8s_version is None:
        nodes_file = root / "cluster-resources" / "nodes.json"
        if nodes_file.is_file():
            try:
                data = json.loads(nodes_file.read_text(errors="replace"))
                items = data if isinstance(data, list) else data.get("items", [])
                if items:
                    k8s_version = items[0].get("status", {}).get("nodeInfo", {}).get("kubeletVersion")
            except (json.JSONDecodeError, OSError):
                pass

    return BundleMetadata(
        collected_at=collected_at,
        kubernetes_version=k8s_version,
        troubleshoot_version=ts_version,
        collection_duration_seconds=duration,
        bundle_path=root,
    )
