"""Crash loop analyzer -- deep analysis of crash-looping containers.

For each pod with CrashLoopBackOff or high restart count, collects
current and previous log tails, exit codes, termination reasons,
and classifies the crash pattern by analyzing log content.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import CrashLoopContext

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Minimum restart count to trigger deep analysis for non-CrashLoopBackOff pods.
_MIN_RESTART_COUNT = 3

# Maximum log lines to collect from each log source.
_LOG_TAIL_LINES = 50

# Patterns for classifying crash causes, checked in priority order.
_CRASH_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    ("oom", [
        re.compile(r"OOMKilled", re.IGNORECASE),
        re.compile(r"out\s*of\s*memory", re.IGNORECASE),
        re.compile(r"Cannot\s+allocate\s+memory", re.IGNORECASE),
        re.compile(r"memory\s+cgroup\s+out\s+of\s+memory", re.IGNORECASE),
        re.compile(r"killed\s+.*process.*oom", re.IGNORECASE),
        re.compile(r"exit\s*code[:\s]+137"),
    ]),
    ("segfault", [
        re.compile(r"signal\s*:?\s*11", re.IGNORECASE),
        re.compile(r"segmentation\s+fault", re.IGNORECASE),
        re.compile(r"SIGSEGV", re.IGNORECASE),
        re.compile(r"segfault", re.IGNORECASE),
        re.compile(r"exit\s*code[:\s]+139"),
    ]),
    ("panic", [
        re.compile(r"panic:", re.IGNORECASE),
        re.compile(r"goroutine\s+\d+\s+\[", re.IGNORECASE),
        re.compile(r"runtime\s+error:", re.IGNORECASE),
        re.compile(r"Traceback\s+\(most\s+recent\s+call\s+last\)", re.IGNORECASE),
        re.compile(r"Exception\s+in\s+thread", re.IGNORECASE),
        re.compile(r"Unhandled\s+exception", re.IGNORECASE),
        re.compile(r"fatal\s+error:", re.IGNORECASE),
    ]),
    ("config_error", [
        re.compile(r"config(uration)?\s*(error|invalid|missing|not\s+found)", re.IGNORECASE),
        re.compile(r"(env|environment)\s+var(iable)?\s+.*\s+(not\s+set|missing|required)", re.IGNORECASE),
        re.compile(r"No\s+such\s+file\s+or\s+directory", re.IGNORECASE),
        re.compile(r"permission\s+denied", re.IGNORECASE),
        re.compile(r"invalid\s+(config|yaml|json|toml)", re.IGNORECASE),
        re.compile(r"failed\s+to\s+(load|parse|read)\s+(config|settings)", re.IGNORECASE),
        re.compile(r"missing\s+required\s+(key|field|parameter)", re.IGNORECASE),
    ]),
    ("dependency_timeout", [
        re.compile(r"connection\s+refused", re.IGNORECASE),
        re.compile(r"connection\s+timed?\s*out", re.IGNORECASE),
        re.compile(r"dial\s+tcp.*:?\s*(i/o\s+)?timeout", re.IGNORECASE),
        re.compile(r"no\s+route\s+to\s+host", re.IGNORECASE),
        re.compile(r"host\s+not\s+found", re.IGNORECASE),
        re.compile(r"name\s+(or\s+service\s+)?not\s+known", re.IGNORECASE),
        re.compile(r"could\s+not\s+connect\s+to", re.IGNORECASE),
        re.compile(r"ECONNREFUSED", re.IGNORECASE),
        re.compile(r"failed\s+to\s+connect", re.IGNORECASE),
        re.compile(r"service\s+unavailable", re.IGNORECASE),
    ]),
]


def _classify_crash(
    log_lines: list[str],
    exit_code: int | None,
    termination_reason: str,
) -> str:
    """Classify the crash pattern from log content and exit metadata.

    Args:
        log_lines: Combined current and previous log lines.
        exit_code: The container's exit code, if available.
        termination_reason: The termination reason string.

    Returns:
        A crash pattern string: "oom", "segfault", "panic",
        "config_error", "dependency_timeout", or "unknown".
    """
    # Check termination reason first
    if termination_reason:
        reason_lower = termination_reason.lower()
        if "oomkilled" in reason_lower or "oom" in reason_lower:
            return "oom"

    # Check exit code
    if exit_code == 137:
        return "oom"
    if exit_code == 139:
        return "segfault"

    # Scan log content against patterns
    combined_text = "\n".join(log_lines)
    for pattern_name, regexes in _CRASH_PATTERNS:
        for regex in regexes:
            if regex.search(combined_text):
                return pattern_name

    return "unknown"


class CrashLoopAnalyzer:
    """Deep analyzer for crash-looping containers.

    For each pod with CrashLoopBackOff status or high restart count,
    collects current and previous log tails, exit codes, termination
    reasons, and classifies the crash pattern.
    """

    async def scan(self, index: BundleIndex) -> list[CrashLoopContext]:
        """Analyze all crash-looping containers in the bundle.

        Args:
            index: The bundle index providing access to pod and log data.

        Returns:
            A list of CrashLoopContext objects with deep crash analysis.
        """
        contexts: list[CrashLoopContext] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for crash loop analysis: {}", exc)
            return contexts

        for pod in pods:
            try:
                pod_contexts = self._analyze_pod(pod, index)
                contexts.extend(pod_contexts)
            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.warning("Error analyzing crash loops for pod {}: {}", pod_name, exc)

        logger.info("CrashLoopAnalyzer found {} crash contexts across {} pods", len(contexts), len(pods))
        return contexts

    def _analyze_pod(
        self, pod: dict, index: BundleIndex,
    ) -> list[CrashLoopContext]:
        """Analyze a single pod for crash-looping containers.

        Args:
            pod: The pod JSON dict.
            index: The bundle index for reading logs.

        Returns:
            List of CrashLoopContext for containers that are crash-looping.
        """
        contexts: list[CrashLoopContext] = []
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        status = pod.get("status", {})

        container_statuses = status.get("containerStatuses", [])
        init_container_statuses = status.get("initContainerStatuses", [])

        all_statuses = list(container_statuses) + list(init_container_statuses)

        for cs in all_statuses:
            if not isinstance(cs, dict):
                continue

            container_name = cs.get("name", "unknown")
            restart_count = cs.get("restartCount", 0)

            # Determine if this container needs deep analysis
            is_crashloop = False
            waiting = cs.get("state", {}).get("waiting", {})
            if waiting.get("reason") == "CrashLoopBackOff":
                is_crashloop = True

            if not is_crashloop and restart_count < _MIN_RESTART_COUNT:
                continue

            # Extract exit code and termination reason
            exit_code: int | None = None
            termination_reason = ""

            # Check last terminated state
            last_state = cs.get("lastState", {}).get("terminated", {})
            if not last_state:
                last_state = cs.get("state", {}).get("terminated", {})

            if last_state:
                exit_code = last_state.get("exitCode")
                termination_reason = last_state.get("reason", "")

            # Collect current log tail
            current_lines = list(
                index.stream_log(
                    namespace, pod_name, container_name,
                    previous=False, last_n_lines=_LOG_TAIL_LINES,
                )
            )

            # Collect previous log tail
            previous_lines = list(
                index.stream_log(
                    namespace, pod_name, container_name,
                    previous=True, last_n_lines=_LOG_TAIL_LINES,
                )
            )

            # Classify the crash pattern
            all_lines = current_lines + previous_lines
            crash_pattern = _classify_crash(all_lines, exit_code, termination_reason)

            # Build descriptive message
            message = self._build_message(
                pod_name, container_name, crash_pattern,
                exit_code, termination_reason, restart_count,
            )

            severity: str = "critical" if restart_count >= _MIN_RESTART_COUNT or is_crashloop else "warning"

            contexts.append(CrashLoopContext(
                namespace=namespace,
                pod_name=pod_name,
                container_name=container_name,
                exit_code=exit_code,
                termination_reason=termination_reason,
                last_log_lines=current_lines,
                previous_log_lines=previous_lines,
                crash_pattern=crash_pattern,
                restart_count=restart_count,
                message=message,
                severity=severity,
            ))

        return contexts

    @staticmethod
    def _build_message(
        pod_name: str,
        container_name: str,
        crash_pattern: str,
        exit_code: int | None,
        termination_reason: str,
        restart_count: int,
    ) -> str:
        """Build a human-readable message describing the crash.

        Args:
            pod_name: Name of the pod.
            container_name: Name of the container.
            crash_pattern: Classified crash pattern.
            exit_code: Exit code, if available.
            termination_reason: Termination reason string.
            restart_count: Number of restarts.

        Returns:
            A descriptive message string.
        """
        pattern_descriptions = {
            "oom": "out-of-memory (OOM) kill",
            "segfault": "segmentation fault (SIGSEGV)",
            "panic": "application panic/unhandled exception",
            "config_error": "configuration or environment error",
            "dependency_timeout": "dependency connection failure/timeout",
            "unknown": "unclassified crash",
        }

        desc = pattern_descriptions.get(crash_pattern, "unclassified crash")
        parts = [
            f"Container '{container_name}' in pod '{pod_name}' is crash-looping "
            f"({restart_count} restarts). Classified as: {desc}.",
        ]

        if exit_code is not None:
            parts.append(f"Exit code: {exit_code}.")
        if termination_reason:
            parts.append(f"Termination reason: {termination_reason}.")

        return " ".join(parts)
