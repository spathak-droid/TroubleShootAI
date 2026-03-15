"""Silence scanner — detects pods that should be logging but have no output.

Identifies containers with empty or missing logs that are expected
to produce output, which may indicate a deeper issue. Also flags
RBAC-blocked resources from the bundle index.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import SilenceSignal

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Minimum pod age (seconds) before we consider missing logs suspicious
_MIN_AGE_SECONDS = 300  # 5 minutes


class SilenceScanner:
    """Scans for pods with missing, empty, or suspiciously absent log data.

    Detects:
    - Running pods with no log file in the bundle
    - Running pods with an empty log file
    - Pods with restarts but no previous log captured
    - RBAC-blocked resources from index.rbac_errors
    """

    async def scan(self, index: BundleIndex) -> list[SilenceSignal]:
        """Scan all running pods for silence signals and check RBAC errors.

        Args:
            index: The bundle index providing access to pod and log data.

        Returns:
            A list of SilenceSignal objects for every detected silence.
        """
        signals: list[SilenceSignal] = []

        # Check pod logs
        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for silence scan: {}", exc)
            pods = []

        for pod in pods:
            try:
                pod_signals = self._check_pod(pod, index)
                signals.extend(pod_signals)
            except Exception as exc:
                name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.debug("Error in silence scan for pod {}: {}", name, exc)

        # Check RBAC errors
        rbac_signals = self._check_rbac(index)
        signals.extend(rbac_signals)

        logger.info("SilenceScanner found {} signals", len(signals))
        return signals

    def _check_pod(self, pod: dict, index: BundleIndex) -> list[SilenceSignal]:
        """Check a single pod for silence signals."""
        signals: list[SilenceSignal] = []
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        phase = status.get("phase", "")

        # Only check Running pods
        if phase != "Running":
            return signals

        # Check pod age
        if not self._is_old_enough(metadata):
            return signals

        container_statuses = status.get("containerStatuses", [])
        for cs in container_statuses:
            container_name = cs.get("name", "unknown")
            restart_count = cs.get("restartCount", 0)

            # Check for log file
            has_log = self._log_exists(index, namespace, pod_name, container_name, previous=False)
            log_empty = False
            if has_log:
                log_empty = self._log_is_empty(index, namespace, pod_name, container_name, previous=False)

            expected_log_path = f"pod-logs/{namespace}/{pod_name}/{container_name}.log"

            if not has_log:
                signals.append(SilenceSignal(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    signal_type="LOG_FILE_MISSING",
                    severity="warning",
                    possible_causes=[
                        "Container stdout not captured by collector",
                        "RBAC prevented log collection",
                        "Container uses file-based logging only",
                    ],
                    note=f"Pod is Running but no log file found for container {container_name}",
                    source_file=f"pods/{namespace}/{pod_name}.json",
                    evidence_excerpt=f"phase=Running, expected log at {expected_log_path} not found",
                ))
            elif log_empty:
                signals.append(SilenceSignal(
                    namespace=namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    signal_type="EMPTY_LOG_RUNNING_POD",
                    severity="warning",
                    possible_causes=[
                        "Container produces no stdout/stderr",
                        "Logging misconfigured",
                        "Container is idle/waiting",
                    ],
                    note=f"Pod is Running but log file for {container_name} is empty",
                    source_file=expected_log_path,
                    evidence_excerpt="phase=Running, log file exists but is empty (0 bytes)",
                ))

            # Check for previous log when restarts > 0
            if restart_count > 0:
                has_prev = self._log_exists(index, namespace, pod_name, container_name, previous=True)
                if not has_prev:
                    signals.append(SilenceSignal(
                        namespace=namespace,
                        pod_name=pod_name,
                        container_name=container_name,
                        signal_type="PREVIOUS_LOG_MISSING",
                        severity="critical" if restart_count > 3 else "warning",
                        possible_causes=[
                            "Previous container log not captured by collector",
                            "Log rotation removed previous logs",
                            f"Container has restarted {restart_count} times",
                        ],
                        note=f"Container has {restart_count} restarts but no previous log captured",
                        source_file=f"pods/{namespace}/{pod_name}.json",
                        evidence_excerpt=f"restartCount={restart_count}, previous log not found",
                    ))

        return signals

    def _check_rbac(self, index: BundleIndex) -> list[SilenceSignal]:
        """Check index.rbac_errors for RBAC-blocked signals."""
        signals: list[SilenceSignal] = []
        rbac_errors = getattr(index, "rbac_errors", []) or []

        for error in rbac_errors:
            # Parse namespace from RBAC error if possible
            namespace = "cluster"
            pod_name = "rbac-blocked"

            # Try to extract namespace from error string
            if "namespace" in error.lower():
                parts = error.split()
                for i, part in enumerate(parts):
                    if part.lower() in ("namespace", "namespace:") and i + 1 < len(parts):
                        namespace = parts[i + 1].strip('"\',:')
                        break

            signals.append(SilenceSignal(
                namespace=namespace,
                pod_name=pod_name,
                container_name=None,
                signal_type="RBAC_BLOCKED",
                severity="warning",
                possible_causes=[
                    "ServiceAccount lacks permissions for this resource",
                    "ClusterRole/RoleBinding misconfigured",
                ],
                note=error,
                source_file="bundle-index/rbac-errors",
                evidence_excerpt=error[:200],
            ))

        return signals

    def _is_old_enough(self, metadata: dict) -> bool:
        """Check if pod is older than the minimum age threshold."""
        creation_ts = metadata.get("creationTimestamp")
        if creation_ts is None:
            return True  # assume old enough if we can't tell

        try:
            if isinstance(creation_ts, str):
                created = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
            else:
                created = creation_ts
            age_seconds = (datetime.now(UTC) - created).total_seconds()
            return age_seconds >= _MIN_AGE_SECONDS
        except (ValueError, TypeError):
            return True  # assume old enough on parse failure

    def _log_exists(
        self,
        index: BundleIndex,
        namespace: str,
        pod_name: str,
        container_name: str,
        *,
        previous: bool,
    ) -> bool:
        """Check if a log file exists in the bundle."""
        suffix = "-previous" if previous else ""
        candidates = [
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.log",
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.txt",
            f"podlogs/{namespace}/{pod_name}/{container_name}{suffix}.log",
        ]
        for candidate in candidates:
            try:
                content = index.read_text(candidate)
                if content is not None:
                    return True
            except Exception:
                pass
        return False

    def _log_is_empty(
        self,
        index: BundleIndex,
        namespace: str,
        pod_name: str,
        container_name: str,
        *,
        previous: bool,
    ) -> bool:
        """Check if a log file exists but is empty."""
        suffix = "-previous" if previous else ""
        candidates = [
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.log",
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.txt",
            f"podlogs/{namespace}/{pod_name}/{container_name}{suffix}.log",
        ]
        for candidate in candidates:
            try:
                content = index.read_text(candidate)
                if content is not None:
                    return len(content.strip()) == 0
            except Exception:
                pass
        return False
