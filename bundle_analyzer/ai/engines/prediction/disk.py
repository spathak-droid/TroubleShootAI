"""Disk exhaustion prediction functions.

Predicts disk full events from node conditions, capacity vs allocatable
storage, and optional metrics-based trend extrapolation.
"""

from __future__ import annotations

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PredictedFailure

from .helpers import get_all_nodes, parse_k8s_memory


def predict_disk_full(index: BundleIndex) -> list[PredictedFailure]:
    """Predict disk exhaustion from node conditions and metrics.

    Checks for DiskPressure conditions and high disk usage percentages
    to predict imminent disk full events.

    Args:
        index: The indexed support bundle.

    Returns:
        List of PredictedFailure objects for disk-related predictions.
    """
    predictions: list[PredictedFailure] = []
    nodes = get_all_nodes(index)

    for node in nodes:
        metadata = node.get("metadata", {})
        node_name = metadata.get("name", "unknown")
        status = node.get("status", {})

        # Check conditions for DiskPressure
        for condition in status.get("conditions", []):
            if (
                condition.get("type") == "DiskPressure"
                and condition.get("status") == "True"
            ):
                predictions.append(
                    PredictedFailure(
                        resource=f"node/{node_name}",
                        failure_type="DISK_PRESSURE_ACTIVE",
                        estimated_eta_seconds=None,
                        confidence=0.95,
                        evidence=[
                            f"Node {node_name} has active DiskPressure condition",
                            f"Message: {condition.get('message', 'N/A')}",
                        ],
                        prevention=(
                            f"Free disk space on node {node_name}. "
                            f"Check: kubectl describe node {node_name}"
                        ),
                    )
                )

        # Check allocatable vs capacity for disk
        capacity = status.get("capacity", {})
        allocatable = status.get("allocatable", {})

        cap_storage = parse_k8s_memory(capacity.get("ephemeral-storage", ""))
        alloc_storage = parse_k8s_memory(
            allocatable.get("ephemeral-storage", "")
        )

        if cap_storage and alloc_storage and cap_storage > 0:
            reserved_pct = 1.0 - (alloc_storage / cap_storage)
            if reserved_pct > 0.15:
                # More than 15% reserved -- disk is getting tight
                predictions.append(
                    PredictedFailure(
                        resource=f"node/{node_name}",
                        failure_type="DISK_RESERVATION_HIGH",
                        estimated_eta_seconds=None,
                        confidence=0.5,
                        evidence=[
                            f"Node {node_name}: {reserved_pct:.0%} of ephemeral "
                            f"storage reserved by kubelet",
                        ],
                        prevention=(
                            f"Monitor disk usage on {node_name}. "
                            f"Consider adding more storage or cleaning up images."
                        ),
                    )
                )

    return predictions


def predict_disk_full_single(
    node_json: dict, metrics: dict | None = None
) -> PredictedFailure | None:
    """Extrapolate disk usage trend for a single node.

    Args:
        node_json: Node JSON with status and capacity.
        metrics: Optional metrics with disk usage data.

    Returns:
        A PredictedFailure if disk exhaustion is predicted, or None.
    """
    metadata = node_json.get("metadata", {})
    node_name = metadata.get("name", "unknown")

    if metrics:
        disk_used = metrics.get("disk_used_bytes", 0)
        disk_total = metrics.get("disk_total_bytes", 0)
        if disk_total > 0 and disk_used > 0:
            usage_pct = disk_used / disk_total
            if usage_pct > 0.85:
                remaining = disk_total - disk_used
                # Estimate: assume 1GB/hour growth rate as default
                growth_rate = metrics.get("disk_growth_bytes_per_hour", 1_073_741_824)
                if growth_rate > 0:
                    eta_seconds = int((remaining / growth_rate) * 3600)
                    return PredictedFailure(
                        resource=f"node/{node_name}",
                        failure_type="DISK_FULL_PREDICTED",
                        estimated_eta_seconds=eta_seconds,
                        confidence=0.6,
                        evidence=[
                            f"Disk usage at {usage_pct:.0%}",
                            f"Remaining: {remaining / (1024**3):.1f} GiB",
                        ],
                        prevention=f"Free disk space on node {node_name}",
                    )
    return None
