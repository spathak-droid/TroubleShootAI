"""Probe scanner -- detects health probe misconfigurations in pods.

Examines liveness, readiness, and startup probes for suspicious paths,
port mismatches, missing probes, and misconfigured timing parameters.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import ProbeIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Paths that strongly suggest a misconfigured probe
_SUSPICIOUS_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"does[_-]?not[_-]?exist", re.IGNORECASE),
    re.compile(r"nonexistent", re.IGNORECASE),
    re.compile(r"/todo/?$", re.IGNORECASE),
    re.compile(r"/fixme/?$", re.IGNORECASE),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"changeme", re.IGNORECASE),
]

# Restart count threshold that suggests a slow-starting app might need a startup probe
_HIGH_RESTART_FOR_STARTUP = 3


class ProbeScanner:
    """Scans all pods for health probe misconfigurations.

    Detects suspicious probe paths, port mismatches, missing readiness
    probes, identical liveness/readiness endpoints, and missing startup
    probes for containers with high restart counts.
    """

    async def scan(self, index: "BundleIndex") -> list[ProbeIssue]:
        """Scan all pods and return detected probe issues.

        Args:
            index: The bundle index providing access to pod JSON data.

        Returns:
            A list of ProbeIssue objects for every probe problem found.
        """
        issues: list[ProbeIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for probe scan: {}", exc)
            return issues

        for pod in pods:
            try:
                pod_issues = self._scan_pod(pod)
                issues.extend(pod_issues)
            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.warning("Error scanning probes for pod {}: {}", pod_name, exc)

        logger.info("ProbeScanner found {} issues across {} pods", len(issues), len(pods))
        return issues

    def _scan_pod(self, pod: dict) -> list[ProbeIssue]:
        """Scan a single pod for probe issues."""
        issues: list[ProbeIssue] = []
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        spec = pod.get("spec", {})
        status = pod.get("status", {})

        # Build restart count map from status
        restart_counts: dict[str, int] = {}
        for cs in status.get("containerStatuses", []):
            restart_counts[cs.get("name", "")] = cs.get("restartCount", 0)

        containers = spec.get("containers", [])
        for container in containers:
            container_name = container.get("name", "unknown")
            container_ports = self._get_container_ports(container)
            restart_count = restart_counts.get(container_name, 0)

            liveness = container.get("livenessProbe")
            readiness = container.get("readinessProbe")
            startup = container.get("startupProbe")

            # Check for suspicious liveness probe paths
            if liveness:
                issues.extend(
                    self._check_suspicious_path(
                        liveness, namespace, pod_name, container_name, "liveness",
                    )
                )
                issues.extend(
                    self._check_port_mismatch(
                        liveness, container_ports, namespace, pod_name,
                        container_name, "liveness",
                    )
                )
                issues.extend(
                    self._check_timing(
                        liveness, namespace, pod_name, container_name, "liveness",
                    )
                )

            # Check for suspicious readiness probe paths
            if readiness:
                issues.extend(
                    self._check_suspicious_path(
                        readiness, namespace, pod_name, container_name, "readiness",
                    )
                )
                issues.extend(
                    self._check_port_mismatch(
                        readiness, container_ports, namespace, pod_name,
                        container_name, "readiness",
                    )
                )

            # Liveness but no readiness probe
            if liveness and not readiness:
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type="readiness",
                    issue="no_readiness_probe",
                    message=(
                        f"Container '{container_name}' has a liveness probe but no "
                        "readiness probe. Service-backed pods need readiness probes "
                        "to avoid routing traffic to unready containers."
                    ),
                    severity="warning",
                ))

            # Same endpoint for liveness and readiness
            if liveness and readiness:
                issues.extend(
                    self._check_same_endpoint(
                        liveness, readiness, namespace, pod_name, container_name,
                    )
                )

            # High restart count with no startup probe
            if restart_count >= _HIGH_RESTART_FOR_STARTUP and not startup:
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type="startup",
                    issue="missing_startup",
                    message=(
                        f"Container '{container_name}' has {restart_count} restarts "
                        "but no startup probe. Slow-starting apps should use a startup "
                        "probe to avoid being killed by the liveness probe during init."
                    ),
                    severity="warning",
                ))

        return issues

    def _get_container_ports(self, container: dict) -> set[int]:
        """Extract the set of declared container ports."""
        ports: set[int] = set()
        for port_spec in container.get("ports", []):
            cp = port_spec.get("containerPort")
            if cp is not None:
                ports.add(int(cp))
        return ports

    def _check_suspicious_path(
        self,
        probe: dict,
        namespace: str,
        pod_name: str,
        container_name: str,
        probe_type: str,
    ) -> list[ProbeIssue]:
        """Check if a probe's httpGet path looks suspicious."""
        issues: list[ProbeIssue] = []
        http_get = probe.get("httpGet", {})
        path = http_get.get("path", "")
        if not path:
            return issues

        for pattern in _SUSPICIOUS_PATH_PATTERNS:
            if pattern.search(path):
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type=probe_type,  # type: ignore[arg-type]
                    issue="bad_path",
                    message=(
                        f"{probe_type.capitalize()} probe has suspicious httpGet "
                        f"path '{path}' (matches pattern '{pattern.pattern}'). "
                        "This is likely a misconfiguration."
                    ),
                    severity="critical",
                ))
                break  # One match is enough

        return issues

    def _check_port_mismatch(
        self,
        probe: dict,
        container_ports: set[int],
        namespace: str,
        pod_name: str,
        container_name: str,
        probe_type: str,
    ) -> list[ProbeIssue]:
        """Check if the probe targets a port the container doesn't expose."""
        issues: list[ProbeIssue] = []
        if not container_ports:
            return issues  # No declared ports -- can't validate

        # Check httpGet port
        http_get = probe.get("httpGet", {})
        probe_port = http_get.get("port")

        # Check tcpSocket port
        if probe_port is None:
            tcp_socket = probe.get("tcpSocket", {})
            probe_port = tcp_socket.get("port")

        if probe_port is not None and isinstance(probe_port, int):
            if probe_port not in container_ports:
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type=probe_type,  # type: ignore[arg-type]
                    issue="bad_path",
                    message=(
                        f"{probe_type.capitalize()} probe targets port {probe_port} "
                        f"but container only exposes ports {sorted(container_ports)}."
                    ),
                    severity="warning",
                ))

        return issues

    def _check_same_endpoint(
        self,
        liveness: dict,
        readiness: dict,
        namespace: str,
        pod_name: str,
        container_name: str,
    ) -> list[ProbeIssue]:
        """Check if liveness and readiness probes share the exact same endpoint."""
        issues: list[ProbeIssue] = []

        l_http = liveness.get("httpGet", {})
        r_http = readiness.get("httpGet", {})

        if l_http and r_http:
            l_key = (l_http.get("path"), l_http.get("port"), l_http.get("scheme", "HTTP"))
            r_key = (r_http.get("path"), r_http.get("port"), r_http.get("scheme", "HTTP"))
            if l_key == r_key:
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type="liveness",
                    issue="same_endpoint",
                    message=(
                        f"Liveness and readiness probes use identical endpoint "
                        f"{l_key[2]}://*:{l_key[1]}{l_key[0]}. A single endpoint "
                        "failure will trigger both probes simultaneously, causing "
                        "the pod to be killed AND removed from service."
                    ),
                    severity="warning",
                ))

        l_tcp = liveness.get("tcpSocket", {})
        r_tcp = readiness.get("tcpSocket", {})
        if l_tcp and r_tcp:
            if l_tcp.get("port") == r_tcp.get("port"):
                issues.append(ProbeIssue(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    probe_type="liveness",
                    issue="same_endpoint",
                    message=(
                        f"Liveness and readiness probes use the same tcpSocket "
                        f"port {l_tcp.get('port')}."
                    ),
                    severity="info",
                ))

        return issues

    def _check_timing(
        self,
        probe: dict,
        namespace: str,
        pod_name: str,
        container_name: str,
        probe_type: str,
    ) -> list[ProbeIssue]:
        """Check if probe timing parameters are misconfigured."""
        issues: list[ProbeIssue] = []

        failure_threshold = probe.get("failureThreshold", 3)
        period_seconds = probe.get("periodSeconds", 10)
        initial_delay = probe.get("initialDelaySeconds", 0)

        # If the total failure window is smaller than initialDelay, the probe
        # will start failing checks before the initial delay is up -- nonsensical
        total_failure_window = failure_threshold * period_seconds
        if initial_delay > 0 and total_failure_window < initial_delay:
            issues.append(ProbeIssue(
                namespace=namespace,
                pod_name=pod_name,
                container_name=container_name,
                probe_type=probe_type,  # type: ignore[arg-type]
                issue="bad_path",
                message=(
                    f"{probe_type.capitalize()} probe timing is suspect: "
                    f"failureThreshold({failure_threshold}) * periodSeconds({period_seconds}) "
                    f"= {total_failure_window}s < initialDelaySeconds({initial_delay}s). "
                    "The probe can declare failure before the delay expires."
                ),
                severity="warning",
            ))

        return issues
