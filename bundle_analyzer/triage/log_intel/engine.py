"""LogIntelligenceEngine -- the public facade for log intelligence.

Pre-processes container logs to extract structured intelligence: error
frequencies, rate spikes, stack trace groups, interesting windows,
and pattern matches. Runs only on pods with known issues.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import (
    ContainerTimeline,
    ErrorRateBucket,
    LogIntelligence,
    PatternFrequency,
    PodLogIntelligence,
    TimelineEntry,
)

from .constants import (
    BUCKET_SECONDS,
    FAILURE_PATTERNS,
    MAX_CONTAINERS_PER_POD,
    MAX_PATTERNS,
    MAX_PODS,
    SIDECAR_NAMES,
)
from .correlation import correlate_containers
from .level_extraction import extract_level
from .stack_traces import detect_stack_traces
from .timestamp import detect_ts_format, parse_timestamp
from .windows import find_interesting_windows

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class LogIntelligenceEngine:
    """Pre-processes container logs to extract structured intelligence.

    Streams entire log files in a single pass, extracting error frequencies,
    rate spikes, stack trace groups, interesting windows, and pattern matches.
    Runs only on pods with known issues to keep runtime bounded.
    """

    async def scan(
        self,
        index: "BundleIndex",
        pods_of_interest: list[dict],
    ) -> dict[str, PodLogIntelligence]:
        """Scan logs for all pods of interest and produce intelligence.

        Args:
            index: The bundle index for reading log files.
            pods_of_interest: List of pod JSON dicts to analyze.

        Returns:
            Dict keyed by 'namespace/pod_name' -> PodLogIntelligence.
        """
        results: dict[str, PodLogIntelligence] = {}

        pods = pods_of_interest[:MAX_PODS]
        logger.info("LogIntelligenceEngine: scanning {} pod(s)", len(pods))

        tasks = [
            self._scan_pod(index, pod)
            for pod in pods
        ]
        pod_results = await asyncio.gather(*tasks, return_exceptions=True)

        for pod, result in zip(pods, pod_results):
            metadata = pod.get("metadata", {})
            ns = metadata.get("namespace", "default")
            name = metadata.get("name", "unknown")
            key = f"{ns}/{name}"

            if isinstance(result, PodLogIntelligence):
                results[key] = result
            elif isinstance(result, Exception):
                logger.warning("LogIntelligenceEngine: failed for {}: {}", key, result)

        logger.info("LogIntelligenceEngine: produced intelligence for {} pod(s)", len(results))
        return results

    async def _scan_pod(
        self,
        index: "BundleIndex",
        pod: dict,
    ) -> PodLogIntelligence:
        """Scan all containers in a single pod."""
        metadata = pod.get("metadata", {})
        ns = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        status = pod.get("status", {})

        container_statuses = status.get("containerStatuses", [])
        init_statuses = status.get("initContainerStatuses", [])
        all_statuses = (list(container_statuses) + list(init_statuses))[:MAX_CONTAINERS_PER_POD]

        # Determine container specs for sidecar detection
        spec_containers = pod.get("spec", {}).get("containers", [])
        container_names_from_spec = {c.get("name", "") for c in spec_containers}  # noqa: F841

        container_intels: list[LogIntelligence] = []
        for cs in all_statuses:
            if not isinstance(cs, dict):
                continue
            container_name = cs.get("name", "unknown")
            is_sidecar = container_name.lower() in SIDECAR_NAMES

            # Scan current logs
            intel = await asyncio.to_thread(
                self._scan_container_sync,
                index, ns, pod_name, container_name, is_sidecar,
            )
            container_intels.append(intel)

        # Cross-container correlation
        correlations = correlate_containers(container_intels)

        # Build unified timelines
        timelines: list[ContainerTimeline] = []
        for ci in container_intels:
            entries: list[TimelineEntry] = []
            for pf in ci.top_patterns[:5]:
                if pf.first_seen:
                    entries.append(TimelineEntry(
                        timestamp=pf.first_seen,
                        level="ERROR",
                        message=f"{pf.pattern} (x{pf.count})",
                    ))
            entries.sort(key=lambda e: e.timestamp)
            timelines.append(ContainerTimeline(
                container_name=ci.container_name,
                is_sidecar=ci.is_sidecar,
                entries=entries,
            ))

        return PodLogIntelligence(
            namespace=ns,
            pod_name=pod_name,
            containers=container_intels,
            cross_container_correlations=correlations,
            unified_timeline=timelines,
        )

    def _scan_container_sync(
        self,
        index: "BundleIndex",
        namespace: str,
        pod_name: str,
        container_name: str,
        is_sidecar: bool,
    ) -> LogIntelligence:
        """Single-pass scan of a container's log file (sync, runs in thread)."""
        lines: list[str] = []
        timestamps: list[datetime | None] = []
        levels: list[str] = []
        pattern_counts: Counter[str] = Counter()
        pattern_samples: dict[str, str] = {}
        pattern_first_seen: dict[str, datetime | None] = {}
        pattern_last_seen: dict[str, datetime | None] = {}
        level_counts: Counter[str] = Counter()

        detected_fmt: str | None = None
        has_oom = False
        has_conn_err = False
        has_perm_err = False
        has_dns = False
        has_cert = False
        has_ratelimit = False

        # Stream entire log file
        log_lines = list(index.stream_log_full(namespace, pod_name, container_name))

        # Also get previous logs
        prev_lines = list(index.stream_log_full(namespace, pod_name, container_name, previous=True))
        all_lines = prev_lines + log_lines
        lines = all_lines

        if not lines:
            return LogIntelligence(
                namespace=namespace,
                pod_name=pod_name,
                container_name=container_name,
                is_sidecar=is_sidecar,
                total_lines_scanned=0,
            )

        # Auto-detect timestamp format
        detected_fmt = detect_ts_format(lines[:20])

        # Single pass
        for line in lines:
            ts = parse_timestamp(line, detected_fmt)
            timestamps.append(ts)

            lvl = extract_level(line)
            levels.append(lvl)
            level_counts[lvl] += 1

            # Match against failure patterns
            for category, label, regex, sev in FAILURE_PATTERNS:
                if regex.search(line):
                    pattern_counts[label] += 1
                    if label not in pattern_samples:
                        pattern_samples[label] = line[:500]
                        pattern_first_seen[label] = ts
                    pattern_last_seen[label] = ts

                    # Set boolean flags
                    if category == "oom":
                        has_oom = True
                    elif category == "connection":
                        has_conn_err = True
                    elif category in ("auth",):
                        has_perm_err = True
                    elif category == "dns":
                        has_dns = True
                    elif category == "tls":
                        has_cert = True
                    elif category == "ratelimit":
                        has_ratelimit = True

        # Build PatternFrequency list
        top_patterns: list[PatternFrequency] = []
        for label, count in pattern_counts.most_common(MAX_PATTERNS):
            first = pattern_first_seen.get(label)
            last = pattern_last_seen.get(label)
            rate = 0.0
            is_spike = False
            if first and last and first != last:
                duration_min = max((last - first).total_seconds() / 60, 0.0167)
                rate = count / duration_min
                is_spike = rate > 50  # >50/minute is a spike

            top_patterns.append(PatternFrequency(
                pattern=label,
                sample_line=pattern_samples.get(label, ""),
                count=count,
                first_seen=first,
                last_seen=last,
                rate_per_minute=round(rate, 1),
                is_spike=is_spike,
            ))

        # Error rate timeline
        error_rate_timeline: list[ErrorRateBucket] = []
        first_ts = next((t for t in timestamps if t is not None), None)
        if first_ts:
            buckets: dict[int, dict[str, int]] = defaultdict(lambda: {"error": 0, "warn": 0, "total": 0})
            for ts, lvl in zip(timestamps, levels):
                if ts:
                    bucket_id = int((ts - first_ts).total_seconds()) // BUCKET_SECONDS
                    buckets[bucket_id]["total"] += 1
                    if lvl in ("ERROR", "FATAL"):
                        buckets[bucket_id]["error"] += 1
                    elif lvl == "WARN":
                        buckets[bucket_id]["warn"] += 1

            for bucket_id in sorted(buckets):
                b = buckets[bucket_id]
                error_rate_timeline.append(ErrorRateBucket(
                    timestamp=first_ts + timedelta(seconds=bucket_id * BUCKET_SECONDS),
                    bucket_seconds=BUCKET_SECONDS,
                    error_count=b["error"],
                    warn_count=b["warn"],
                    total_count=b["total"],
                ))

        # Stack traces
        stack_traces = detect_stack_traces(lines, timestamps)

        # Interesting windows
        interesting_windows = find_interesting_windows(lines, levels, timestamps)

        # Time span
        valid_ts = [t for t in timestamps if t is not None]
        time_span = (min(valid_ts), max(valid_ts)) if valid_ts else (None, None)

        # Dominant error
        dominant_error = top_patterns[0].pattern if top_patterns else ""

        return LogIntelligence(
            namespace=namespace,
            pod_name=pod_name,
            container_name=container_name,
            is_sidecar=is_sidecar,
            total_lines_scanned=len(lines),
            time_span=time_span,
            top_patterns=top_patterns,
            error_rate_timeline=error_rate_timeline,
            stack_traces=stack_traces,
            interesting_windows=interesting_windows,
            level_counts=dict(level_counts),
            has_oom_indicators=has_oom,
            has_connection_errors=has_conn_err,
            has_permission_errors=has_perm_err,
            has_dns_failures=has_dns,
            has_cert_errors=has_cert,
            has_rate_limiting=has_ratelimit,
            dominant_error=dominant_error,
        )
