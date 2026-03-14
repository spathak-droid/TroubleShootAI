"""Interesting window detection in log streams.

Identifies regions of interest: first errors after silence, error rate spikes,
and state transitions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from bundle_analyzer.models import LogWindow

from .constants import BUCKET_SECONDS, CONTEXT_AFTER, CONTEXT_BEFORE, MAX_WINDOWS, SPIKE_MULTIPLIER


def find_interesting_windows(
    lines: list[str],
    levels: list[str],
    timestamps: list[datetime | None],
) -> list[LogWindow]:
    """Identify interesting regions in the log.

    Detects three types of windows:
    1. First error after a period of silence (>60s gap between errors).
    2. Error rate spikes (buckets with significantly more errors than median).
    3. State transitions (started, shutting down, leader elected, etc.).

    Args:
        lines: All log lines.
        levels: Extracted log levels aligned with lines.
        timestamps: Parsed timestamps aligned with lines.

    Returns:
        Deduplicated, priority-sorted list of LogWindow objects (capped).
    """
    windows: list[LogWindow] = []
    n = len(lines)
    if n == 0:
        return windows

    # 1. First error after silence (>60s gap between errors)
    last_error_idx: int | None = None
    for i, lvl in enumerate(levels):
        if lvl in ('ERROR', 'FATAL'):
            if last_error_idx is not None and timestamps[i] and timestamps[last_error_idx]:
                gap = (timestamps[i] - timestamps[last_error_idx]).total_seconds()
                if gap > 60:
                    start = max(0, i - CONTEXT_BEFORE)
                    end = min(n, i + CONTEXT_AFTER)
                    windows.append(LogWindow(
                        start_line=start,
                        end_line=end,
                        lines=lines[start:end],
                        trigger="first_error_after_silence",
                        severity="critical",
                        timestamp_range=(timestamps[start], timestamps[min(end - 1, n - 1)]),
                    ))
            last_error_idx = i

    # 2. Error spike detection (bucket by minute)
    if any(t is not None for t in timestamps):
        error_buckets: dict[int, list[int]] = defaultdict(list)
        first_ts = next((t for t in timestamps if t is not None), None)
        if first_ts:
            for i, (lvl, ts) in enumerate(zip(levels, timestamps)):
                if ts and lvl in ('ERROR', 'FATAL'):
                    bucket = int((ts - first_ts).total_seconds()) // BUCKET_SECONDS
                    error_buckets[bucket].append(i)

            if error_buckets:
                counts = sorted(len(v) for v in error_buckets.values())
                median_count = counts[len(counts) // 2] if counts else 0
                spike_threshold = max(3, int(median_count * SPIKE_MULTIPLIER)) if median_count > 1 else 5

                for bucket_id, indices in error_buckets.items():
                    if len(indices) >= spike_threshold:
                        mid = indices[len(indices) // 2]
                        start = max(0, mid - 15)
                        end = min(n, mid + 15)
                        windows.append(LogWindow(
                            start_line=start,
                            end_line=end,
                            lines=lines[start:end],
                            trigger="error_spike",
                            severity="critical",
                            timestamp_range=(timestamps[start], timestamps[min(end - 1, n - 1)]),
                        ))

    # 3. State transitions
    _STATE_RE = re.compile(
        r'\b(started|starting|shutting\s+down|connected|disconnected|'
        r'leader\s+elected|lost\s+leadership|ready|not\s+ready|'
        r'initialized|terminated|failed\s+over)\b',
        re.I,
    )
    for i, line in enumerate(lines):
        if _STATE_RE.search(line):
            start = max(0, i - 5)
            end = min(n, i + 6)
            windows.append(LogWindow(
                start_line=start,
                end_line=end,
                lines=lines[start:end],
                trigger="state_transition",
                severity="info",
                timestamp_range=(timestamps[start] if start < len(timestamps) else None,
                                 timestamps[min(end - 1, n - 1)] if end - 1 < len(timestamps) else None),
            ))

    # Prioritize and cap
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    trigger_order = {"error_spike": 0, "first_error_after_silence": 1, "state_transition": 2}
    windows.sort(key=lambda w: (severity_order.get(w.severity, 9), trigger_order.get(w.trigger, 9)))

    # Deduplicate overlapping windows
    deduped: list[LogWindow] = []
    seen_ranges: list[tuple[int, int]] = []
    for w in windows:
        overlaps = any(
            w.start_line < er and w.end_line > sr
            for sr, er in seen_ranges
        )
        if not overlaps:
            deduped.append(w)
            seen_ranges.append((w.start_line, w.end_line))
        if len(deduped) >= MAX_WINDOWS:
            break

    return deduped
