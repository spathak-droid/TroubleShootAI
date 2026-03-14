"""Data access helpers for chain walking.

These functions read from the BundleIndex and triage results to look up
pod JSON, events, config issues, log patterns, and container details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import ConfigIssue, NodeIssue, TriageResult

from .constants import _LOG_PATTERNS

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def ensure_pod_index(
    index: BundleIndex,
    pod_cache: dict[str, dict],
    pods_indexed: bool,
) -> bool:
    """Build the pod cache from the bundle index if not already done.

    Args:
        index: The bundle index for reading raw Kubernetes JSON.
        pod_cache: Mutable dict to populate with pod JSON keyed by ns/name.
        pods_indexed: Whether the cache has already been built.

    Returns:
        True (always), indicating the cache is now populated.
    """
    if pods_indexed:
        return True
    for pod in index.get_all_pods():
        meta = pod.get("metadata", {})
        ns = meta.get("namespace", "")
        name = meta.get("name", "")
        if ns and name:
            pod_cache[f"{ns}/{name}"] = pod
    logger.debug("Pod cache built: {} pods indexed", len(pod_cache))
    return True


def find_pod_json(
    pod_cache: dict[str, dict],
    namespace: str,
    pod_name: str,
) -> dict | None:
    """Look up the raw pod JSON by namespace and name.

    Args:
        pod_cache: The pre-built pod cache.
        namespace: Kubernetes namespace.
        pod_name: Pod name.

    Returns:
        The pod JSON dict, or None if not found.
    """
    return pod_cache.get(f"{namespace}/{pod_name}")


def find_related_events(
    index: BundleIndex,
    namespace: str,
    name: str,
) -> list[dict]:
    """Find Warning events related to a specific resource.

    Args:
        index: The bundle index.
        namespace: Kubernetes namespace.
        name: Resource name.

    Returns:
        List of event dicts matching the resource, newest first.
    """
    events = index.get_events(namespace)
    related: list[dict] = []
    for ev in events:
        involved = ev.get("involvedObject", {})
        if involved.get("name") == name and ev.get("type") == "Warning":
            related.append(ev)
    return related


def check_config_issues(
    triage: TriageResult,
    namespace: str,
    pod_name: str,
) -> list[ConfigIssue]:
    """Find config issues referencing this pod.

    Args:
        triage: The triage results.
        namespace: Kubernetes namespace.
        pod_name: Pod name.

    Returns:
        List of ConfigIssue objects that reference this pod.
    """
    return [
        ci for ci in triage.config_issues
        if ci.namespace == namespace and ci.referenced_by == pod_name
    ]


def get_log_patterns(
    index: BundleIndex,
    namespace: str,
    pod_name: str,
    container: str,
) -> list[str]:
    """Read last 20 lines of pod logs and check for known error patterns.

    Args:
        index: The bundle index.
        namespace: Kubernetes namespace.
        pod_name: Pod name.
        container: Container name.

    Returns:
        List of matched pattern labels (e.g. "connection_refused").
    """
    if not container:
        return []

    lines = list(index.stream_log(
        namespace=namespace,
        pod=pod_name,
        container=container,
        previous=False,
        last_n_lines=20,
    ))

    if not lines:
        # Try previous logs
        lines = list(index.stream_log(
            namespace=namespace,
            pod=pod_name,
            container=container,
            previous=True,
            last_n_lines=20,
        ))

    matched: list[str] = []
    for line in lines:
        for pattern, label in _LOG_PATTERNS:
            if pattern.search(line) and label not in matched:
                matched.append(label)

    return matched


def extract_exit_code(pod_json: dict, container_name: str) -> int | None:
    """Extract the exit code from the last terminated container state.

    Args:
        pod_json: Raw pod JSON dict.
        container_name: Container name to check.

    Returns:
        The exit code, or None if not found.
    """
    statuses = pod_json.get("status", {}).get("containerStatuses", [])
    for cs in statuses:
        if container_name and cs.get("name") != container_name:
            continue
        last_state = cs.get("lastState", {})
        terminated = last_state.get("terminated", {})
        if "exitCode" in terminated:
            return terminated["exitCode"]
        # Also check current state
        current = cs.get("state", {})
        term_current = current.get("terminated", {})
        if "exitCode" in term_current:
            return term_current["exitCode"]
    return None


def has_memory_limits(pod_json: dict | None, container_name: str) -> bool:
    """Check whether the specified container has memory limits.

    Args:
        pod_json: Raw pod JSON dict, or None.
        container_name: Container name to check.

    Returns:
        True if memory limits are set, False otherwise.
    """
    if not pod_json:
        return False
    containers = pod_json.get("spec", {}).get("containers", [])
    for c in containers:
        if container_name and c.get("name") != container_name:
            continue
        limits = c.get("resources", {}).get("limits", {})
        if "memory" in limits:
            return True
    return False


def check_node_memory_pressure(
    pod_json: dict | None,
    node_issues: list[NodeIssue],
) -> str | None:
    """Check if the node this pod runs on has MemoryPressure.

    Args:
        pod_json: Raw pod JSON dict, or None.
        node_issues: List of NodeIssue from triage results.

    Returns:
        The node name if under pressure, or None.
    """
    if not pod_json:
        return None
    node_name = pod_json.get("spec", {}).get("nodeName")
    if not node_name:
        return None
    for ni in node_issues:
        if ni.node_name == node_name and ni.condition == "MemoryPressure":
            return node_name
    return None


def check_liveness_probe(pod_json: dict | None, container_name: str) -> str | None:
    """Check if the container has a liveness probe and describe it.

    Args:
        pod_json: Raw pod JSON dict, or None.
        container_name: Container name to check.

    Returns:
        A description of the liveness probe, or None if not configured.
    """
    if not pod_json:
        return None
    containers = pod_json.get("spec", {}).get("containers", [])
    for c in containers:
        if container_name and c.get("name") != container_name:
            continue
        probe = c.get("livenessProbe")
        if probe:
            if "httpGet" in probe:
                http = probe["httpGet"]
                return f"httpGet {http.get('path', '/')}:{http.get('port', '?')}"
            if "tcpSocket" in probe:
                return f"tcpSocket port {probe['tcpSocket'].get('port', '?')}"
            if "exec" in probe:
                cmd = probe["exec"].get("command", [])
                return f"exec {' '.join(cmd[:3])}"
            return "probe configured (unknown type)"
    return None


def get_restart_policy(pod_json: dict | None) -> str:
    """Get the pod's restart policy.

    Args:
        pod_json: Raw pod JSON dict, or None.

    Returns:
        The restart policy string (defaults to "Always").
    """
    if not pod_json:
        return "Always"
    return pod_json.get("spec", {}).get("restartPolicy", "Always")
