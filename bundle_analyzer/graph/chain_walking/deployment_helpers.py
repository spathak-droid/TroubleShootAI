"""Deployment and node helper functions for chain walking.

Functions for finding pods belonging to deployments, finding pods on nodes,
parsing memory strings, and finding biggest resource consumers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bundle_analyzer.models import PodIssue, TriageResult

from .data_access import find_pod_json

if TYPE_CHECKING:
    pass


def find_deployment_pods(
    triage: TriageResult,
    pod_cache: dict[str, dict],
    namespace: str,
    deployment_name: str,
) -> list[PodIssue]:
    """Find pod issues that belong to a deployment.

    Matches by checking if the pod name starts with the deployment name
    (deployment -> replicaset -> pod naming convention), or by checking
    ownerReferences in pod JSON.

    Args:
        triage: The triage results.
        pod_cache: The pre-built pod cache.
        namespace: Kubernetes namespace.
        deployment_name: Deployment name.

    Returns:
        List of PodIssue objects belonging to this deployment.
    """
    all_pods = triage.critical_pods + triage.warning_pods
    matched: list[PodIssue] = []

    for pod in all_pods:
        if pod.namespace != namespace:
            continue
        # Check by name prefix (deployment-replicaset-pod pattern)
        if pod.pod_name.startswith(deployment_name + "-"):
            matched.append(pod)
            continue
        # Check ownerReferences in pod JSON
        pod_json = find_pod_json(pod_cache, pod.namespace, pod.pod_name)
        if pod_json:
            owners = pod_json.get("metadata", {}).get("ownerReferences", [])
            for owner in owners:
                if owner.get("kind") == "ReplicaSet" and owner.get("name", "").startswith(
                    deployment_name + "-"
                ):
                    matched.append(pod)
                    break

    return matched


def find_pods_on_node(
    pod_cache: dict[str, dict],
    node_name: str,
) -> list[dict]:
    """Find all pods scheduled on a specific node.

    Args:
        pod_cache: The pre-built pod cache.
        node_name: The node name.

    Returns:
        List of dicts with 'name', 'namespace', 'json' for each pod on the node.
    """
    pods: list[dict] = []
    for _key, pod_json in pod_cache.items():
        if pod_json.get("spec", {}).get("nodeName") == node_name:
            meta = pod_json.get("metadata", {})
            pods.append({
                "name": meta.get("name", ""),
                "namespace": meta.get("namespace", ""),
                "json": pod_json,
            })
    return pods


def find_biggest_consumer(pods_on_node: list[dict]) -> dict | None:
    """Find the pod requesting the most memory on a node.

    Args:
        pods_on_node: List of pod info dicts from find_pods_on_node.

    Returns:
        A dict with 'name', 'namespace', 'resource_desc' for the biggest
        consumer, or None if no pods have resource requests.
    """
    biggest: dict | None = None
    biggest_bytes = 0

    for pod_info in pods_on_node:
        pod_json = pod_info.get("json", {})
        total = 0
        for container in pod_json.get("spec", {}).get("containers", []):
            mem_req = container.get("resources", {}).get("requests", {}).get("memory", "")
            total += parse_memory(mem_req)
            mem_lim = container.get("resources", {}).get("limits", {}).get("memory", "")
            total += parse_memory(mem_lim)

        if total > biggest_bytes:
            biggest_bytes = total
            biggest = {
                "name": pod_info["name"],
                "namespace": pod_info["namespace"],
                "resource_desc": f"memory requests+limits: {biggest_bytes} bytes",
            }

    return biggest


def parse_memory(value: str) -> int:
    """Parse a Kubernetes memory string (e.g. '128Mi', '1Gi') to bytes.

    Args:
        value: The memory string.

    Returns:
        Memory in bytes, or 0 if unparseable.
    """
    if not value:
        return 0
    value = str(value).strip()
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
    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return int(float(value[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    try:
        return int(value)
    except ValueError:
        return 0
