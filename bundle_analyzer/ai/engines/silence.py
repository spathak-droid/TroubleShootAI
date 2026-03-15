"""Silence detection engine — finds what's missing from the bundle.

Identifies expected resources, logs, or metrics that are absent,
which may indicate deeper issues than what's explicitly failing.
Silence is a signal: missing data often tells more than present data.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import SilenceSignal, TriageResult


class SilenceDetectionEngine:
    """Detects missing or suspiciously absent data in the bundle.

    Checks for empty logs on running pods, missing log files, missing
    previous logs for restarted containers, namespace-wide log blocks,
    and silent init containers.
    """

    async def detect(
        self,
        index: BundleIndex,
        triage: TriageResult,
    ) -> list[SilenceSignal]:
        """Run all silence detectors and return findings.

        Args:
            index: The indexed support bundle.
            triage: The triage result from Phase 1 scanners.

        Returns:
            List of SilenceSignal objects for missing/absent data.
        """
        signals: list[SilenceSignal] = []

        signals.extend(self._check_empty_log_running_pod(index))
        signals.extend(self._check_log_file_missing(index))
        signals.extend(self._check_previous_log_missing(index))
        signals.extend(self._check_namespace_log_blocked(index))
        signals.extend(self._check_silent_init_container(index))

        logger.info("Silence detection: {} signals found", len(signals))
        return signals

    # ── Detector: Empty log on running pod ───────────────────────────

    def _check_empty_log_running_pod(
        self, index: BundleIndex
    ) -> list[SilenceSignal]:
        """Find running+ready pods whose log files exist but are empty.

        A running pod with zero log output is suspicious — it may indicate
        the application is hanging, logging to a non-standard location,
        or the log collector failed silently.
        """
        signals: list[SilenceSignal] = []

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = pod.get("status", {})
            phase = status.get("phase", "")

            if phase != "Running":
                continue

            # Check each container
            for cs in status.get("containerStatuses", []) or []:
                container_name = cs.get("name", "unknown")
                is_ready = cs.get("ready", False)
                is_running = "running" in (cs.get("state") or {})

                if not (is_ready and is_running):
                    continue

                # Look for the log file
                log_path = self._find_log_file(
                    index, namespace, pod_name, container_name, previous=False
                )

                if log_path is not None and log_path.exists():
                    file_size = log_path.stat().st_size
                    if file_size == 0:
                        signals.append(
                            SilenceSignal(
                                namespace=namespace,
                                pod_name=pod_name,
                                container_name=container_name,
                                signal_type="EMPTY_LOG_RUNNING_POD",
                                severity="warning",
                                possible_causes=[
                                    "Application logs to a file instead of stdout",
                                    "Application is hanging/deadlocked",
                                    "Log collector failed to capture output",
                                    "Container just started and has not produced output yet",
                                ],
                                note=(
                                    f"Expected: non-empty log for running+ready container "
                                    f"{container_name} in pod {pod_name}. "
                                    f"Investigate: kubectl logs {pod_name} "
                                    f"-c {container_name} -n {namespace}"
                                ),
                            )
                        )

        return signals

    # ── Detector: Log file missing ───────────────────────────────────

    def _check_log_file_missing(self, index: BundleIndex) -> list[SilenceSignal]:
        """Find pods that exist in JSON but have no log file at expected paths.

        If a pod was collected in the bundle metadata but its logs were not
        collected, this may indicate a collection error or RBAC issue.
        """
        signals: list[SilenceSignal] = []

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = pod.get("status", {})
            phase = status.get("phase", "")

            # Only check pods that should have logs (Running, Succeeded, Failed)
            if phase not in ("Running", "Succeeded", "Failed"):
                continue

            for cs in status.get("containerStatuses", []) or []:
                container_name = cs.get("name", "unknown")

                # Skip containers that never started
                state = cs.get("state", {})
                last_state = cs.get("lastState", {})
                has_ever_run = (
                    "running" in state
                    or "terminated" in state
                    or "terminated" in last_state
                )
                if not has_ever_run:
                    continue

                log_path = self._find_log_file(
                    index, namespace, pod_name, container_name, previous=False
                )

                if log_path is None:
                    signals.append(
                        SilenceSignal(
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            signal_type="LOG_FILE_MISSING",
                            severity="warning",
                            possible_causes=[
                                "Log collector did not have permission (RBAC)",
                                "Pod was too short-lived for log collection",
                                "Bundle was collected before logs were available",
                                "Log collector configuration excludes this namespace",
                            ],
                            note=(
                                f"Expected: log file for container {container_name} "
                                f"in pod {pod_name} (phase={phase}). "
                                f"Investigate: kubectl logs {pod_name} "
                                f"-c {container_name} -n {namespace}"
                            ),
                        )
                    )

        return signals

    # ── Detector: Previous log missing ───────────────────────────────

    def _check_previous_log_missing(
        self, index: BundleIndex
    ) -> list[SilenceSignal]:
        """Find restarted containers that have no previous log file.

        When restartCount > 0, the previous container log is critical for
        understanding why the container crashed. Its absence is a significant gap.
        """
        signals: list[SilenceSignal] = []

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = pod.get("status", {})

            for cs in status.get("containerStatuses", []) or []:
                container_name = cs.get("name", "unknown")
                restart_count = cs.get("restartCount", 0)

                if restart_count <= 0:
                    continue

                prev_log = self._find_log_file(
                    index, namespace, pod_name, container_name, previous=True
                )

                if prev_log is None:
                    signals.append(
                        SilenceSignal(
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            signal_type="PREVIOUS_LOG_MISSING",
                            severity="critical",
                            possible_causes=[
                                "Previous container log was garbage collected",
                                "Log collector did not capture --previous logs",
                                f"Container restarted {restart_count} times — "
                                f"only the most recent previous log is kept by kubelet",
                                "RBAC policy prevents reading previous logs",
                            ],
                            note=(
                                f"Expected: previous log for container {container_name} "
                                f"(restartCount={restart_count}) in pod {pod_name}. "
                                f"The pre-crash log is critical for root cause analysis. "
                                f"Collect: kubectl logs {pod_name} "
                                f"-c {container_name} -n {namespace} --previous"
                            ),
                        )
                    )

        return signals

    # ── Detector: Namespace log blocked ──────────────────────────────

    def _check_namespace_log_blocked(
        self, index: BundleIndex
    ) -> list[SilenceSignal]:
        """Find namespaces where no pods have any log files.

        If an entire namespace has zero logs but has running pods, this
        strongly suggests an RBAC or collection policy issue.
        """
        signals: list[SilenceSignal] = []

        # Build a map: namespace -> (has_pods, has_any_log)
        ns_stats: dict[str, dict[str, bool]] = {}

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            namespace = metadata.get("namespace", "unknown")
            pod_name = metadata.get("name", "unknown")
            status = pod.get("status", {})
            phase = status.get("phase", "")

            if namespace not in ns_stats:
                ns_stats[namespace] = {"has_pods": False, "has_any_log": False}

            # Only count pods that should produce logs
            if phase in ("Running", "Succeeded", "Failed"):
                ns_stats[namespace]["has_pods"] = True

                for cs in status.get("containerStatuses", []) or []:
                    container_name = cs.get("name", "unknown")
                    log_path = self._find_log_file(
                        index, namespace, pod_name, container_name, previous=False
                    )
                    if log_path is not None:
                        ns_stats[namespace]["has_any_log"] = True

        for namespace, stats in ns_stats.items():
            if stats["has_pods"] and not stats["has_any_log"]:
                signals.append(
                    SilenceSignal(
                        namespace=namespace,
                        pod_name="*",
                        container_name=None,
                        signal_type="RBAC_BLOCKED",
                        severity="critical",
                        possible_causes=[
                            f"RBAC policy blocks log collection in namespace {namespace}",
                            "Log collector is not configured for this namespace",
                            "All pods in this namespace are too new for log collection",
                            "Network policy prevents log collector access",
                        ],
                        note=(
                            f"Expected: at least some log files for namespace "
                            f"{namespace} which has running pods. No logs found "
                            f"for any pod. This likely indicates an RBAC or collection "
                            f"policy issue. "
                            f"Investigate: kubectl auth can-i get pods/log "
                            f"-n {namespace} --as=system:serviceaccount:default:support-bundle"
                        ),
                    )
                )

        return signals

    # ── Detector: Silent init container ──────────────────────────────

    def _check_silent_init_container(
        self, index: BundleIndex
    ) -> list[SilenceSignal]:
        """Find init containers that completed but produced no output.

        Init containers that succeed silently may hide important setup steps
        or indicate that the init container's command is a no-op.
        """
        signals: list[SilenceSignal] = []

        for pod in index.get_all_pods():
            metadata = pod.get("metadata", {})
            pod_name = metadata.get("name", "unknown")
            namespace = metadata.get("namespace", "unknown")
            status = pod.get("status", {})

            for ics in status.get("initContainerStatuses", []) or []:
                container_name = ics.get("name", "unknown")
                state = ics.get("state", {})
                terminated = state.get("terminated", {})

                # Check if init container completed successfully
                if terminated.get("reason") != "Completed":
                    continue
                if terminated.get("exitCode", -1) != 0:
                    continue

                # Look for the init container's log
                log_path = self._find_log_file(
                    index, namespace, pod_name, container_name, previous=False
                )

                if log_path is None:
                    signals.append(
                        SilenceSignal(
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            signal_type="LOG_FILE_MISSING",
                            severity="info",
                            possible_causes=[
                                "Init container produced no stdout/stderr output",
                                "Init container log was not collected",
                                "Init container ran too briefly for log capture",
                            ],
                            note=(
                                f"Expected: some output from init container "
                                f"{container_name} in pod {pod_name} (completed "
                                f"successfully). Silent init containers may hide "
                                f"setup issues. "
                                f"Investigate: kubectl logs {pod_name} "
                                f"-c {container_name} -n {namespace}"
                            ),
                        )
                    )
                elif log_path.exists() and log_path.stat().st_size == 0:
                    signals.append(
                        SilenceSignal(
                            namespace=namespace,
                            pod_name=pod_name,
                            container_name=container_name,
                            signal_type="EMPTY_LOG_RUNNING_POD",
                            severity="info",
                            possible_causes=[
                                "Init container intentionally produces no output",
                                "Init container logs to a file instead of stdout",
                                "Init container command is a no-op shell script",
                            ],
                            note=(
                                f"Expected: output from completed init container "
                                f"{container_name} in pod {pod_name}. Log file "
                                f"exists but is empty. "
                                f"Investigate: kubectl logs {pod_name} "
                                f"-c {container_name} -n {namespace}"
                            ),
                        )
                    )

        return signals

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _find_log_file(
        index: BundleIndex,
        namespace: str,
        pod_name: str,
        container_name: str,
        previous: bool = False,
    ) -> Path | None:
        """Locate a container log file in the bundle.

        Checks multiple common bundle directory layouts.

        Args:
            index: The indexed support bundle.
            namespace: Pod namespace.
            pod_name: Pod name.
            container_name: Container name.
            previous: If True, look for the previous-log file.

        Returns:
            Path to the log file if found, or None.
        """
        suffix = "-previous.log" if previous else ".log"
        candidates = [
            index.root / namespace / pod_name / f"{container_name}{suffix}",
            index.root / "pods" / namespace / pod_name / f"{container_name}{suffix}",
            index.root / namespace / pod_name / container_name / f"{container_name}{suffix}",
        ]
        if previous:
            candidates.append(
                index.root / namespace / pod_name / "previous" / f"{container_name}.log"
            )

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        return None
