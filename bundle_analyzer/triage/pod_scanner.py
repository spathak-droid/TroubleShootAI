"""Pod scanner — detects CrashLoopBackOff, OOMKilled, ImagePullBackOff, and other pod failures.

Examines pod status, container statuses, exit codes, and restart counts
to produce findings without requiring AI analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import PodIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Issue types considered critical (vs warning)
_CRITICAL_ISSUE_TYPES = frozenset({
    "CrashLoopBackOff",
    "OOMKilled",
    "CreateContainerConfigError",
})

# Restart count threshold to flag even if pod looks healthy right now
_HIGH_RESTART_THRESHOLD = 5

# Seconds a pod can be Pending before we flag it
_PENDING_THRESHOLD_SECONDS = 300  # 5 minutes


class PodScanner:
    """Scans all pods in a bundle for container-level issues.

    Detects crash loops, OOM kills, image pull failures, stuck pending pods,
    and high restart counts. Populates log paths for each flagged pod.
    """

    async def scan(self, index: "BundleIndex") -> list[PodIssue]:
        """Scan all pods and return detected issues.

        Args:
            index: The bundle index providing access to pod JSON data.

        Returns:
            A list of PodIssue objects for every problematic pod found.
        """
        issues: list[PodIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods from bundle: {}", exc)
            return issues

        for pod in pods:
            try:
                pod_issues = self._scan_pod(pod, index)
                issues.extend(pod_issues)
            except Exception as exc:
                pod_name = _safe_get(pod, "metadata", "name") or "<unknown>"
                logger.warning("Error scanning pod {}: {}", pod_name, exc)

        logger.info("PodScanner found {} issues across {} pods", len(issues), len(pods))
        return issues

    def _scan_pod(self, pod: dict, index: "BundleIndex") -> list[PodIssue]:
        """Scan a single pod dict and return any issues found."""
        issues: list[PodIssue] = []
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        phase = status.get("phase", "")

        # Check for Pending pods
        if phase == "Pending":
            issue = self._check_pending(metadata, status, namespace, pod_name)
            if issue is not None:
                issues.append(issue)

        # Check container statuses
        container_statuses = status.get("containerStatuses", [])
        init_container_statuses = status.get("initContainerStatuses", [])

        for cs in container_statuses:
            cs_issues = self._check_container_status(
                cs, namespace, pod_name, index, is_init=False,
            )
            issues.extend(cs_issues)

        for cs in init_container_statuses:
            cs_issues = self._check_container_status(
                cs, namespace, pod_name, index, is_init=True,
            )
            issues.extend(cs_issues)

        return issues

    def _check_pending(
        self,
        metadata: dict,
        status: dict,
        namespace: str,
        pod_name: str,
    ) -> PodIssue | None:
        """Check if a Pending pod has been pending too long."""
        creation_ts = metadata.get("creationTimestamp")
        if creation_ts is None:
            # No timestamp — flag it anyway since it is Pending
            return PodIssue(
                namespace=namespace,
                pod_name=pod_name,
                container_name=None,
                issue_type="Pending",
                message="Pod is in Pending phase (no creation timestamp to check age)",
            )

        try:
            if isinstance(creation_ts, str):
                created = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
            else:
                created = creation_ts
            age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
        except (ValueError, TypeError) as exc:
            logger.debug("Could not parse creationTimestamp for {}/{}: {}", namespace, pod_name, exc)
            age_seconds = _PENDING_THRESHOLD_SECONDS + 1  # flag it if we can't parse

        if age_seconds > _PENDING_THRESHOLD_SECONDS:
            conditions = status.get("conditions", [])
            message_parts: list[str] = []
            for cond in conditions:
                if cond.get("status") != "True" and cond.get("message"):
                    message_parts.append(cond["message"])
            return PodIssue(
                namespace=namespace,
                pod_name=pod_name,
                container_name=None,
                issue_type="Pending",
                message=f"Pending for {int(age_seconds)}s. {'; '.join(message_parts)}" if message_parts
                else f"Pending for {int(age_seconds)}s",
            )
        return None

    def _check_container_status(
        self,
        cs: dict,
        namespace: str,
        pod_name: str,
        index: "BundleIndex",
        *,
        is_init: bool,
    ) -> list[PodIssue]:
        """Check a single containerStatus for issues."""
        issues: list[PodIssue] = []
        container_name = cs.get("name", "unknown")
        restart_count = cs.get("restartCount", 0)
        state = cs.get("state", {})
        last_state = cs.get("lastState", {})

        detected_issue_type: str | None = None
        exit_code: int | None = None
        message = ""

        # Check waiting state
        waiting = state.get("waiting", {})
        if waiting:
            reason = waiting.get("reason", "")
            if reason == "CrashLoopBackOff":
                detected_issue_type = "CrashLoopBackOff"
                message = waiting.get("message", "Container is in CrashLoopBackOff")
            elif reason == "ImagePullBackOff" or reason == "ErrImagePull":
                detected_issue_type = "ImagePullBackOff"
                message = waiting.get("message", f"Image pull failed: {reason}")
            elif reason == "CreateContainerConfigError":
                detected_issue_type = "CreateContainerConfigError"
                message = waiting.get("message", "Container config error")

        # Check lastState for OOMKilled
        terminated_last = last_state.get("terminated", {})
        if terminated_last:
            reason = terminated_last.get("reason", "")
            if reason == "OOMKilled":
                detected_issue_type = "OOMKilled"
                exit_code = terminated_last.get("exitCode")
                message = f"OOMKilled (exit code {exit_code})"

        # Check current terminated state too
        terminated = state.get("terminated", {})
        if terminated and not detected_issue_type:
            reason = terminated.get("reason", "")
            if reason == "OOMKilled":
                detected_issue_type = "OOMKilled"
                exit_code = terminated.get("exitCode")
                message = f"OOMKilled (exit code {exit_code})"

        # Init container failures
        if is_init and not detected_issue_type:
            if terminated and terminated.get("exitCode", 0) != 0:
                detected_issue_type = "InitContainerFailed"
                exit_code = terminated.get("exitCode")
                message = f"Init container exited with code {exit_code}: {terminated.get('reason', '')}"
            elif waiting and waiting.get("reason"):
                detected_issue_type = "InitContainerFailed"
                message = f"Init container waiting: {waiting.get('reason', '')}"

        # High restart count — always flag
        if restart_count > _HIGH_RESTART_THRESHOLD and detected_issue_type is None:
            detected_issue_type = "CrashLoopBackOff"
            message = f"High restart count ({restart_count}) without active failure state"

        if detected_issue_type is None:
            return issues

        # Resolve log paths
        log_path = self._find_log_path(index, namespace, pod_name, container_name, previous=False)
        previous_log_path = self._find_log_path(index, namespace, pod_name, container_name, previous=True)

        issues.append(PodIssue(
            namespace=namespace,
            pod_name=pod_name,
            container_name=container_name,
            issue_type=detected_issue_type,
            restart_count=restart_count,
            exit_code=exit_code,
            message=message,
            log_path=log_path,
            previous_log_path=previous_log_path,
        ))

        return issues

    def _find_log_path(
        self,
        index: "BundleIndex",
        namespace: str,
        pod_name: str,
        container_name: str,
        *,
        previous: bool,
    ) -> str | None:
        """Attempt to find a log path in the bundle index.

        Returns the path string if found, None otherwise.
        """
        # Common bundle log path patterns
        suffix = "-previous" if previous else ""
        candidates = [
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.log",
            f"pod-logs/{namespace}/{pod_name}/{container_name}{suffix}.txt",
            f"podlogs/{namespace}/{pod_name}/{container_name}{suffix}.log",
        ]
        for candidate in candidates:
            try:
                if hasattr(index, "read_text"):
                    content = index.read_text(candidate)
                    if content is not None:
                        return candidate
            except Exception:
                pass
        return None


def _safe_get(d: dict, *keys: str) -> str | None:
    """Safely traverse nested dicts, returning None if any key is missing."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return str(current) if current is not None else None
