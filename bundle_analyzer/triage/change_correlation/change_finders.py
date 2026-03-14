"""Change finder functions for detecting recent cluster modifications.

Each function scans a specific resource type (deployments, configmaps,
secrets, nodes, replicasets, events) for changes within the lookback window.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from loguru import logger

from bundle_analyzer.triage.change_correlation.models import ChangeEvent
from bundle_analyzer.triage.change_correlation.utils import (
    extract_items,
    in_window,
    parse_k8s_timestamp,
)

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def find_recent_deployments(
    index: "BundleIndex", before: datetime, window_minutes: int
) -> list[ChangeEvent]:
    """Find deployments created or updated within the lookback window.

    Checks ``metadata.creationTimestamp`` and the deployment revision
    annotation to detect recent deployments and rollouts.

    Args:
        index: Bundle index.
        before: The failure onset timestamp.
        window_minutes: How far back to look.

    Returns:
        List of deployment-related change events.
    """
    changes: list[ChangeEvent] = []
    cutoff = before - timedelta(minutes=window_minutes)

    if not index.has("deployments"):
        return changes

    deployments_dir = index.root / "cluster-resources" / "deployments"
    if not deployments_dir.is_dir():
        return changes

    for ns_dir in sorted(deployments_dir.iterdir()):
        if ns_dir.is_dir():
            for dep_file in sorted(ns_dir.glob("*.json")):
                rel = str(dep_file.relative_to(index.root))
                data = index.read_json(rel)
                if data is None:
                    continue
                items = extract_items(data)
                for item in items:
                    changes.extend(check_deployment(item, cutoff, before))
        elif ns_dir.suffix == ".json":
            rel = str(ns_dir.relative_to(index.root))
            data = index.read_json(rel)
            if data is None:
                continue
            items = extract_items(data)
            for item in items:
                changes.extend(check_deployment(item, cutoff, before))

    return changes


def check_deployment(
    dep: dict, cutoff: datetime, before: datetime
) -> list[ChangeEvent]:
    """Check a single deployment dict for recent changes.

    Args:
        dep: Deployment resource dict.
        cutoff: Start of the lookback window.
        before: End of the lookback window (failure onset).

    Returns:
        List of change events found in this deployment.
    """
    results: list[ChangeEvent] = []
    metadata = dep.get("metadata", {})
    name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "default")
    annotations = metadata.get("annotations", {}) or {}

    creation_ts = parse_k8s_timestamp(metadata.get("creationTimestamp"))
    if creation_ts is not None and in_window(creation_ts, cutoff, before):
        results.append(
            ChangeEvent(
                resource_type="Deployment",
                resource_name=name,
                namespace=namespace,
                change_type="created",
                timestamp=creation_ts,
                detail=f"Deployment '{name}' was created",
            )
        )

    # Check revision annotation -- high revision with recent creation
    # implies recent rollout
    revision = annotations.get("deployment.kubernetes.io/revision", "")
    if revision and creation_ts is not None:
        try:
            rev_num = int(revision)
            if rev_num > 1 and in_window(creation_ts, cutoff, before):
                results.append(
                    ChangeEvent(
                        resource_type="Deployment",
                        resource_name=name,
                        namespace=namespace,
                        change_type="rolled_out",
                        timestamp=creation_ts,
                        detail=(
                            f"Deployment '{name}' is at revision {rev_num} "
                            f"(rollout detected)"
                        ),
                    )
                )
        except ValueError:
            pass

    return results


def find_recent_config_changes(
    index: "BundleIndex", before: datetime, window_minutes: int
) -> list[ChangeEvent]:
    """Find ConfigMaps and Secrets created/modified within the window.

    Checks ``metadata.creationTimestamp`` for both ConfigMaps and Secrets.

    Args:
        index: Bundle index.
        before: The failure onset timestamp.
        window_minutes: How far back to look.

    Returns:
        List of config-related change events.
    """
    changes: list[ChangeEvent] = []
    cutoff = before - timedelta(minutes=window_minutes)

    for resource_type, dir_name in (
        ("ConfigMap", "configmaps"),
        ("Secret", "secrets"),
    ):
        if not index.has(dir_name):
            continue

        resource_dir = index.root / "cluster-resources" / dir_name
        if not resource_dir.is_dir():
            continue

        for ns_dir in sorted(resource_dir.iterdir()):
            if ns_dir.is_dir():
                for res_file in sorted(ns_dir.glob("*.json")):
                    rel = str(res_file.relative_to(index.root))
                    data = index.read_json(rel)
                    if data is None:
                        continue
                    items = extract_items(data)
                    for item in items:
                        change = check_config_resource(
                            item, resource_type, cutoff, before
                        )
                        if change is not None:
                            changes.append(change)
            elif ns_dir.suffix == ".json":
                rel = str(ns_dir.relative_to(index.root))
                data = index.read_json(rel)
                if data is None:
                    continue
                items = extract_items(data)
                for item in items:
                    change = check_config_resource(
                        item, resource_type, cutoff, before
                    )
                    if change is not None:
                        changes.append(change)

    return changes


def check_config_resource(
    item: dict,
    resource_type: str,
    cutoff: datetime,
    before: datetime,
) -> ChangeEvent | None:
    """Check a single ConfigMap or Secret for recent changes.

    Args:
        item: Resource dict.
        resource_type: ``"ConfigMap"`` or ``"Secret"``.
        cutoff: Start of the lookback window.
        before: End of the lookback window.

    Returns:
        A ``ChangeEvent`` if the resource was recently changed, else ``None``.
    """
    metadata = item.get("metadata", {})
    name = metadata.get("name", "unknown")
    namespace = metadata.get("namespace", "default")

    creation_ts = parse_k8s_timestamp(metadata.get("creationTimestamp"))
    if creation_ts is not None and in_window(creation_ts, cutoff, before):
        return ChangeEvent(
            resource_type=resource_type,
            resource_name=name,
            namespace=namespace,
            change_type="modified",
            timestamp=creation_ts,
            detail=f"{resource_type} '{name}' was created or modified recently",
        )
    return None


def find_scaling_events(
    index: "BundleIndex", before: datetime, window_minutes: int
) -> list[ChangeEvent]:
    """Find scaling and deployment-related events within the window.

    Looks for events with reasons like ``ScalingReplicaSet``,
    ``SuccessfulCreate``, ``Killing``, and ``RollingUpdate``.

    Args:
        index: Bundle index.
        before: The failure onset timestamp.
        window_minutes: How far back to look.

    Returns:
        List of scaling-related change events.
    """
    changes: list[ChangeEvent] = []
    cutoff = before - timedelta(minutes=window_minutes)

    scaling_reasons = {
        "ScalingReplicaSet",
        "SuccessfulCreate",
        "Killing",
        "RollingUpdate",
        "DeploymentRollback",
        "ScaledUp",
        "ScaledDown",
    }

    try:
        raw_events = index.get_events()
    except Exception as exc:
        logger.warning("ChangeCorrelator: failed to read events: {}", exc)
        return changes

    for raw in raw_events:
        reason = raw.get("reason", "")
        if reason not in scaling_reasons:
            continue

        metadata = raw.get("metadata", {})
        involved = raw.get("involvedObject", {})
        namespace = metadata.get("namespace", involved.get("namespace", "default"))

        ts = parse_k8s_timestamp(
            raw.get("lastTimestamp")
            or raw.get("firstTimestamp")
            or metadata.get("creationTimestamp")
        )
        if ts is None or not in_window(ts, cutoff, before):
            continue

        obj_kind = involved.get("kind", "Unknown")
        obj_name = involved.get("name", "unknown")
        message = raw.get("message", "")

        change_type: Literal[
            "created", "modified", "scaled", "restarted", "deleted", "rolled_out"
        ] = "scaled"
        if reason in ("RollingUpdate", "DeploymentRollback"):
            change_type = "rolled_out"
        elif reason == "Killing":
            change_type = "restarted"
        elif reason == "SuccessfulCreate":
            change_type = "created"

        changes.append(
            ChangeEvent(
                resource_type=obj_kind,
                resource_name=obj_name,
                namespace=namespace,
                change_type=change_type,
                timestamp=ts,
                detail=f"Event '{reason}': {message[:200]}",
            )
        )

    return changes


def find_node_changes(
    index: "BundleIndex", before: datetime, window_minutes: int
) -> list[ChangeEvent]:
    """Find nodes created or with recently changed conditions.

    Checks ``metadata.creationTimestamp`` for newly added nodes and
    ``conditions[].lastTransitionTime`` for recent condition changes.

    Args:
        index: Bundle index.
        before: The failure onset timestamp.
        window_minutes: How far back to look.

    Returns:
        List of node-related change events.
    """
    changes: list[ChangeEvent] = []
    cutoff = before - timedelta(minutes=window_minutes)

    # Try nodes.json (single file) first
    nodes_data = index.read_json("cluster-resources/nodes.json")
    if nodes_data is not None:
        items = extract_items(nodes_data)
        for item in items:
            changes.extend(check_node(item, cutoff, before))
        return changes

    # Try nodes directory
    if not index.has("nodes"):
        return changes

    nodes_dir = index.root / "cluster-resources" / "nodes"
    if not nodes_dir.is_dir():
        return changes

    for node_file in sorted(nodes_dir.glob("*.json")):
        rel = str(node_file.relative_to(index.root))
        data = index.read_json(rel)
        if data is None:
            continue
        items = extract_items(data)
        for item in items:
            changes.extend(check_node(item, cutoff, before))

    return changes


def check_node(
    node: dict, cutoff: datetime, before: datetime
) -> list[ChangeEvent]:
    """Check a single node dict for recent changes.

    Args:
        node: Node resource dict.
        cutoff: Start of the lookback window.
        before: End of the lookback window.

    Returns:
        List of change events found for this node.
    """
    results: list[ChangeEvent] = []
    metadata = node.get("metadata", {})
    name = metadata.get("name", "unknown")

    creation_ts = parse_k8s_timestamp(metadata.get("creationTimestamp"))
    if creation_ts is not None and in_window(creation_ts, cutoff, before):
        results.append(
            ChangeEvent(
                resource_type="Node",
                resource_name=name,
                change_type="created",
                timestamp=creation_ts,
                detail=f"Node '{name}' was recently added to the cluster",
            )
        )

    # Check condition transitions
    status = node.get("status", {})
    for condition in status.get("conditions", []):
        transition_ts = parse_k8s_timestamp(
            condition.get("lastTransitionTime")
        )
        if transition_ts is None or not in_window(transition_ts, cutoff, before):
            continue

        cond_type = condition.get("type", "Unknown")
        cond_status = condition.get("status", "Unknown")
        results.append(
            ChangeEvent(
                resource_type="Node",
                resource_name=name,
                change_type="modified",
                timestamp=transition_ts,
                detail=(
                    f"Node '{name}' condition '{cond_type}' "
                    f"transitioned to '{cond_status}'"
                ),
            )
        )

    return results


def find_rollout_events(
    index: "BundleIndex", before: datetime, window_minutes: int
) -> list[ChangeEvent]:
    """Detect rollouts by finding multiple ReplicaSets for the same deployment.

    When a deployment has more than one ReplicaSet with non-zero replicas,
    a rollout is in progress or was recently performed.

    Args:
        index: Bundle index.
        before: The failure onset timestamp.
        window_minutes: How far back to look.

    Returns:
        List of rollout-related change events.
    """
    changes: list[ChangeEvent] = []
    cutoff = before - timedelta(minutes=window_minutes)

    if not index.has("replicasets"):
        return changes

    rs_dir = index.root / "cluster-resources" / "replicasets"
    if not rs_dir.is_dir():
        return changes

    # Group ReplicaSets by owner deployment
    # Key: (namespace, deployment_name) -> list of (rs_name, creation_ts, replicas)
    owner_map: dict[tuple[str, str], list[tuple[str, datetime, int]]] = {}

    for ns_dir in sorted(rs_dir.iterdir()):
        files = []
        if ns_dir.is_dir():
            files = list(ns_dir.glob("*.json"))
        elif ns_dir.suffix == ".json":
            files = [ns_dir]

        for rs_file in sorted(files):
            rel = str(rs_file.relative_to(index.root))
            data = index.read_json(rel)
            if data is None:
                continue
            items = extract_items(data)
            for item in items:
                metadata = item.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                rs_name = metadata.get("name", "unknown")
                creation_ts = parse_k8s_timestamp(
                    metadata.get("creationTimestamp")
                )
                if creation_ts is None:
                    continue

                spec = item.get("spec", {})
                replicas = spec.get("replicas", 0)

                # Find owner deployment
                for owner in metadata.get("ownerReferences", []):
                    if owner.get("kind") == "Deployment":
                        dep_name = owner.get("name", "unknown")
                        key = (namespace, dep_name)
                        if key not in owner_map:
                            owner_map[key] = []
                        owner_map[key].append(
                            (rs_name, creation_ts, replicas)
                        )

    # Detect rollouts: multiple ReplicaSets for the same deployment
    for (namespace, dep_name), rs_list in owner_map.items():
        if len(rs_list) < 2:
            continue

        # Sort by creation time, newest first
        rs_list.sort(key=lambda x: x[1], reverse=True)
        newest_rs_name, newest_ts, _ = rs_list[0]

        if in_window(newest_ts, cutoff, before):
            changes.append(
                ChangeEvent(
                    resource_type="Deployment",
                    resource_name=dep_name,
                    namespace=namespace,
                    change_type="rolled_out",
                    timestamp=newest_ts,
                    detail=(
                        f"Deployment '{dep_name}' has {len(rs_list)} "
                        f"ReplicaSets (latest: '{newest_rs_name}'), "
                        f"indicating a recent rollout"
                    ),
                )
            )

    return changes
