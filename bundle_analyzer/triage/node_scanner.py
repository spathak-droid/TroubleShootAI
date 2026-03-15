"""Node scanner — detects MemoryPressure, DiskPressure, NotReady, and other node conditions.

Examines node status conditions, capacity, and allocatable resources
to identify infrastructure-level issues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import NodeIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Conditions that are problematic when True
_BAD_TRUE_CONDITIONS = frozenset({
    "MemoryPressure",
    "DiskPressure",
    "PIDPressure",
})


class NodeScanner:
    """Scans nodes for resource pressure conditions and readiness issues.

    Examines node status conditions and optional node-metrics to detect
    MemoryPressure, DiskPressure, PIDPressure, NotReady, and Unschedulable.
    """

    async def scan(self, index: "BundleIndex") -> list[NodeIssue]:
        """Scan all nodes and return detected issues.

        Args:
            index: The bundle index providing access to node JSON data.

        Returns:
            A list of NodeIssue objects for every problematic node found.
        """
        issues: list[NodeIssue] = []

        nodes = self._read_nodes(index)
        if not nodes:
            logger.info("NodeScanner: no nodes found in bundle")
            return issues

        # Try to read node metrics for usage percentages
        node_metrics = self._read_node_metrics(index)

        for node in nodes:
            try:
                node_issues = self._scan_node(node, node_metrics)
                issues.extend(node_issues)
            except Exception as exc:
                name = node.get("metadata", {}).get("name", "<unknown>")
                logger.warning("Error scanning node {}: {}", name, exc)

        logger.info("NodeScanner found {} issues across {} nodes", len(issues), len(nodes))
        return issues

    def _read_nodes(self, index: "BundleIndex") -> list[dict]:
        """Read node resources from the bundle."""
        try:
            data = index.read_json("cluster-resources/nodes.json")
            if data is None:
                return []
            if isinstance(data, list):
                return data
            # Might be a List resource
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.warning("Failed to read nodes: {}", exc)
            return []

    def _read_node_metrics(self, index: "BundleIndex") -> dict[str, dict]:
        """Read node metrics keyed by node name. Returns empty dict if unavailable."""
        try:
            data = index.read_json("cluster-resources/nodes/metrics.json")
            if data is None:
                # Try alternate path
                data = index.read_json("cluster-resources/node-metrics.json")
            if data is None:
                return {}
            items = data if isinstance(data, list) else data.get("items", [])
            result: dict[str, dict] = {}
            for item in items:
                name = item.get("metadata", {}).get("name")
                if name:
                    result[name] = item
            return result
        except Exception as exc:
            logger.debug("No node metrics available: {}", exc)
            return {}

    def _scan_node(self, node: dict, node_metrics: dict[str, dict]) -> list[NodeIssue]:
        """Scan a single node and return issues."""
        issues: list[NodeIssue] = []
        metadata = node.get("metadata", {})
        status = node.get("status", {})
        spec = node.get("spec", {})
        node_name = metadata.get("name", "unknown")

        conditions = status.get("conditions", [])

        # Calculate usage percentages from metrics if available
        memory_pct, cpu_pct = self._calc_usage_pct(node_name, node, node_metrics)

        # Check conditions
        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            cond_message = cond.get("message", "")

            # Bad conditions that should be False
            if cond_type in _BAD_TRUE_CONDITIONS and cond_status == "True":
                issues.append(NodeIssue(
                    node_name=node_name,
                    condition=cond_type,  # type: ignore[arg-type]
                    memory_usage_pct=memory_pct,
                    cpu_usage_pct=cpu_pct,
                    message=cond_message,
                    confidence=0.95 if cond_type != "PIDPressure" else 0.9,
                    source_file="cluster-resources/nodes.json",
                    evidence_excerpt=f"condition.type={cond_type}, status={cond_status}, message={cond_message}" if cond_message else f"condition.type={cond_type}, status={cond_status}",
                ))

            # Ready condition — bad when False
            if cond_type == "Ready" and cond_status != "True":
                issues.append(NodeIssue(
                    node_name=node_name,
                    condition="NotReady",
                    memory_usage_pct=memory_pct,
                    cpu_usage_pct=cpu_pct,
                    message=cond_message,
                    confidence=0.85,
                    source_file="cluster-resources/nodes.json",
                    evidence_excerpt=f"condition.type=Ready, status={cond_status}, message={cond_message}" if cond_message else f"condition.type=Ready, status={cond_status}",
                ))

        # Check unschedulable taint/spec
        if spec.get("unschedulable"):
            issues.append(NodeIssue(
                node_name=node_name,
                condition="Unschedulable",
                memory_usage_pct=memory_pct,
                cpu_usage_pct=cpu_pct,
                message="Node is marked unschedulable",
                confidence=1.0,
                source_file="cluster-resources/nodes.json",
                evidence_excerpt="spec.unschedulable=true",
            ))

        return issues

    def _calc_usage_pct(
        self,
        node_name: str,
        node: dict,
        node_metrics: dict[str, dict],
    ) -> tuple[float | None, float | None]:
        """Calculate memory and CPU usage percentages from metrics and allocatable."""
        metrics = node_metrics.get(node_name)
        if not metrics:
            return None, None

        allocatable = node.get("status", {}).get("allocatable", {})
        usage = metrics.get("usage", {})

        memory_pct = self._calc_memory_pct(
            usage.get("memory"), allocatable.get("memory"),
        )
        cpu_pct = self._calc_cpu_pct(
            usage.get("cpu"), allocatable.get("cpu"),
        )
        return memory_pct, cpu_pct

    def _calc_memory_pct(self, usage_str: str | None, alloc_str: str | None) -> float | None:
        """Convert Kubernetes memory strings to a percentage."""
        if not usage_str or not alloc_str:
            return None
        try:
            usage_bytes = _parse_k8s_memory(usage_str)
            alloc_bytes = _parse_k8s_memory(alloc_str)
            if alloc_bytes <= 0:
                return None
            return round((usage_bytes / alloc_bytes) * 100, 1)
        except (ValueError, TypeError):
            return None

    def _calc_cpu_pct(self, usage_str: str | None, alloc_str: str | None) -> float | None:
        """Convert Kubernetes CPU strings to a percentage."""
        if not usage_str or not alloc_str:
            return None
        try:
            usage_millicores = _parse_k8s_cpu(usage_str)
            alloc_millicores = _parse_k8s_cpu(alloc_str)
            if alloc_millicores <= 0:
                return None
            return round((usage_millicores / alloc_millicores) * 100, 1)
        except (ValueError, TypeError):
            return None


def _parse_k8s_memory(value: str) -> float:
    """Parse Kubernetes memory value (e.g., '1Gi', '512Mi', '1024Ki') to bytes."""
    value = value.strip()
    multipliers = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "K": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * mult
    return float(value)


def _parse_k8s_cpu(value: str) -> float:
    """Parse Kubernetes CPU value (e.g., '500m', '2') to millicores."""
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1])
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000
    return float(value) * 1000
