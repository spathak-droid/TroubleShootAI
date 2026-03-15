"""Resource scanner -- detects missing resource requests/limits and overcommitment.

Examines container resource specifications and compares against node
allocatable capacity to find scheduling and stability risks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import ResourceIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def _parse_cpu(value: str | int | float) -> float:
    """Parse a Kubernetes CPU quantity to fractional cores.

    Examples:
        '100m' -> 0.1
        '4' -> 4.0
        '4000m' -> 4.0
    """
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.endswith("m"):
        return float(s[:-1]) / 1000.0
    return float(s)


def _parse_memory(value: str | int | float) -> int:
    """Parse a Kubernetes memory quantity to bytes.

    Examples:
        '16Gi' -> 17179869184
        '256Mi' -> 268435456
        '1024Ki' -> 1048576
        '1000000' -> 1000000
    """
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    multipliers = {
        "Ki": 1024,
        "Mi": 1024 ** 2,
        "Gi": 1024 ** 3,
        "Ti": 1024 ** 4,
        "Pi": 1024 ** 5,
        "k": 1000,
        "M": 1000 ** 2,
        "G": 1000 ** 3,
        "T": 1000 ** 4,
        "P": 1000 ** 5,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    # Plain number (bytes)
    return int(float(s))


class ResourceScanner:
    """Scans pods for resource request/limit issues.

    Detects containers with no limits, no requests, BestEffort QoS,
    requests exceeding node capacity, and overcommitted nodes.
    """

    async def scan(self, index: BundleIndex) -> list[ResourceIssue]:
        """Scan all pods and return detected resource issues.

        Args:
            index: The bundle index providing access to pod and node data.

        Returns:
            A list of ResourceIssue objects for every resource problem found.
        """
        issues: list[ResourceIssue] = []

        # Parse node allocatable capacity
        node_capacity = self._get_node_capacity(index)

        # Track per-node resource requests for overcommitment check
        node_requests: dict[str, dict[str, float]] = {}  # node -> {"cpu": X, "memory": Y}

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for resource scan: {}", exc)
            return issues

        for pod in pods:
            try:
                pod_issues, pod_node_reqs = self._scan_pod(pod, node_capacity)
                issues.extend(pod_issues)

                # Accumulate per-node requests
                node_name = pod.get("spec", {}).get("nodeName")
                if node_name and pod_node_reqs:
                    if node_name not in node_requests:
                        node_requests[node_name] = {"cpu": 0.0, "memory": 0.0}
                    node_requests[node_name]["cpu"] += pod_node_reqs.get("cpu", 0.0)
                    node_requests[node_name]["memory"] += pod_node_reqs.get("memory", 0.0)
            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.warning("Error scanning resources for pod {}: {}", pod_name, exc)

        # Check for overcommitted nodes
        for node_name, reqs in node_requests.items():
            if node_name in node_capacity:
                cap = node_capacity[node_name]
                if cap["memory"] > 0 and reqs["memory"] > cap["memory"]:
                    pct = (reqs["memory"] / cap["memory"]) * 100
                    issues.append(ResourceIssue(
                        namespace="cluster",
                        pod_name=f"node/{node_name}",
                        container_name="",
                        issue="overcommitted_node",
                        message=(
                            f"Node '{node_name}' memory requests "
                            f"({reqs['memory'] / (1024**3):.1f}Gi) exceed allocatable "
                            f"({cap['memory'] / (1024**3):.1f}Gi) at {pct:.0f}%."
                        ),
                        resource_type="memory",
                        severity="critical",
                        source_file="cluster-resources/nodes.json",
                        evidence_excerpt=(
                            f"node={node_name}, memory_requests={reqs['memory'] / (1024**3):.1f}Gi, "
                            f"allocatable={cap['memory'] / (1024**3):.1f}Gi, usage={pct:.0f}%"
                        ),
                    ))
                if cap["cpu"] > 0 and reqs["cpu"] > cap["cpu"]:
                    pct = (reqs["cpu"] / cap["cpu"]) * 100
                    issues.append(ResourceIssue(
                        namespace="cluster",
                        pod_name=f"node/{node_name}",
                        container_name="",
                        issue="overcommitted_node",
                        message=(
                            f"Node '{node_name}' CPU requests "
                            f"({reqs['cpu']:.2f} cores) exceed allocatable "
                            f"({cap['cpu']:.2f} cores) at {pct:.0f}%."
                        ),
                        resource_type="cpu",
                        severity="critical",
                        source_file="cluster-resources/nodes.json",
                        evidence_excerpt=(
                            f"node={node_name}, cpu_requests={reqs['cpu']:.2f}, "
                            f"allocatable={cap['cpu']:.2f}, usage={pct:.0f}%"
                        ),
                    ))

        logger.info("ResourceScanner found {} issues across {} pods", len(issues), len(pods))
        return issues

    def _get_node_capacity(
        self, index: BundleIndex,
    ) -> dict[str, dict[str, float]]:
        """Parse node allocatable capacity from nodes.json.

        Returns:
            Mapping of node_name -> {"cpu": cores_float, "memory": bytes_int}.
        """
        capacity: dict[str, dict[str, float]] = {}

        data = index.read_json("cluster-resources/nodes.json")
        if data is None:
            # Try directory-based layout
            nodes_dir = index.root / "cluster-resources" / "nodes"
            if nodes_dir.is_dir():
                for f in nodes_dir.glob("*.json"):
                    node_data = index.read_json(str(f.relative_to(index.root)))
                    if isinstance(node_data, dict):
                        self._parse_node(node_data, capacity)
            return capacity

        items: list[dict] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])

        for node in items:
            self._parse_node(node, capacity)

        return capacity

    def _parse_node(
        self, node: dict, capacity: dict[str, dict[str, float]],
    ) -> None:
        """Parse a single node dict into the capacity map."""
        name = node.get("metadata", {}).get("name", "")
        allocatable = node.get("status", {}).get("allocatable", {})
        if not name or not allocatable:
            return

        try:
            cpu = _parse_cpu(allocatable.get("cpu", "0"))
            memory = _parse_memory(allocatable.get("memory", "0"))
            capacity[name] = {"cpu": cpu, "memory": float(memory)}
        except (ValueError, TypeError) as exc:
            logger.debug("Could not parse allocatable for node {}: {}", name, exc)

    def _scan_pod(
        self,
        pod: dict,
        node_capacity: dict[str, dict[str, float]],
    ) -> tuple[list[ResourceIssue], dict[str, float]]:
        """Scan a single pod for resource issues.

        Returns:
            Tuple of (issues, pod_total_requests) where pod_total_requests
            is {"cpu": X, "memory": Y} in base units.
        """
        issues: list[ResourceIssue] = []
        pod_total: dict[str, float] = {"cpu": 0.0, "memory": 0.0}

        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        source_file = f"pods/{namespace}/{pod_name}.json"
        spec = pod.get("spec", {})
        status = pod.get("status", {})
        qos_class = status.get("qosClass", "")
        spec.get("nodeName")

        # BestEffort QoS warning
        if qos_class == "BestEffort":
            issues.append(ResourceIssue(
                namespace=namespace,
                pod_name=pod_name,
                container_name="",
                issue="no_limits",
                message=(
                    f"Pod '{pod_name}' has QoS class BestEffort (no requests or limits). "
                    "It will be the first pod evicted under memory pressure."
                ),
                resource_type="memory",
                severity="warning",
                source_file=source_file,
                evidence_excerpt="status.qosClass=BestEffort",
            ))

        containers = spec.get("containers", [])
        for container in containers:
            container_name = container.get("name", "unknown")
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})

            has_requests = bool(requests)
            has_limits = bool(limits)

            # No limits at all
            if not has_limits:
                issues.append(ResourceIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    issue="no_limits",
                    message=(
                        f"Container '{container_name}' has no resource limits. "
                        "It can consume unbounded CPU/memory and destabilize the node."
                    ),
                    resource_type="memory",
                    severity="warning",
                    source_file=source_file,
                    evidence_excerpt=f"resources.limits absent for container {container_name}",
                ))

            # No requests at all
            if not has_requests:
                issues.append(ResourceIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    issue="no_requests",
                    message=(
                        f"Container '{container_name}' has no resource requests. "
                        "The scheduler cannot make informed placement decisions."
                    ),
                    resource_type="memory",
                    severity="warning",
                    source_file=source_file,
                    evidence_excerpt=f"resources.requests absent for container {container_name}",
                ))

            # Accumulate requests for overcommitment check
            if requests.get("cpu"):
                try:
                    cpu_req = _parse_cpu(requests["cpu"])
                    pod_total["cpu"] += cpu_req
                except (ValueError, TypeError):
                    pass
            if requests.get("memory"):
                try:
                    mem_req = _parse_memory(requests["memory"])
                    pod_total["memory"] += float(mem_req)
                except (ValueError, TypeError):
                    pass

            # Check if single container requests exceed any node
            if node_capacity and requests:
                self._check_exceeds_node(
                    requests, node_capacity, namespace, pod_name,
                    container_name, issues, source_file,
                )

        return issues, pod_total

    def _check_exceeds_node(
        self,
        requests: dict,
        node_capacity: dict[str, dict[str, float]],
        namespace: str,
        pod_name: str,
        container_name: str,
        issues: list[ResourceIssue],
        source_file: str,
    ) -> None:
        """Check if a container's requests exceed all nodes' allocatable."""
        if not node_capacity:
            return

        max_node_memory = max(cap["memory"] for cap in node_capacity.values())
        max_node_cpu = max(cap["cpu"] for cap in node_capacity.values())

        if requests.get("memory"):
            try:
                mem_req = _parse_memory(requests["memory"])
                if mem_req > max_node_memory and max_node_memory > 0:
                    issues.append(ResourceIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container_name,
                        issue="exceeds_node",
                        message=(
                            f"Container '{container_name}' requests "
                            f"{mem_req / (1024**3):.1f}Gi memory but the largest "
                            f"node only has {max_node_memory / (1024**3):.1f}Gi allocatable."
                        ),
                        resource_type="memory",
                        severity="critical",
                        source_file=source_file,
                        evidence_excerpt=(
                            f"resources.requests.memory={requests['memory']}, "
                            f"max_node_allocatable={max_node_memory / (1024**3):.1f}Gi"
                        ),
                    ))
            except (ValueError, TypeError):
                pass

        if requests.get("cpu"):
            try:
                cpu_req = _parse_cpu(requests["cpu"])
                if cpu_req > max_node_cpu and max_node_cpu > 0:
                    issues.append(ResourceIssue(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container_name,
                        issue="exceeds_node",
                        message=(
                            f"Container '{container_name}' requests "
                            f"{cpu_req:.2f} CPU cores but the largest node "
                            f"only has {max_node_cpu:.2f} allocatable."
                        ),
                        resource_type="cpu",
                        severity="critical",
                        source_file=source_file,
                        evidence_excerpt=(
                            f"resources.requests.cpu={requests['cpu']}, "
                            f"max_node_allocatable={max_node_cpu:.2f}"
                        ),
                    ))
            except (ValueError, TypeError):
                pass
