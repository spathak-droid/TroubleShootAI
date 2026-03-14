"""Timestamp parsing and format detection for log lines.

Supports 8 timestamp formats: ISO 8601, klog, Python/Java, Go, syslog,
epoch seconds, epoch milliseconds, and RFC 2822.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


# ── Timestamp patterns ────────────────────────────────────────────────

_TS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ISO 8601: 2024-01-15T14:03:17.123Z or with offset
    (re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))'), 'iso8601'),
    # Klog: I0115 14:03:17.123456  (Kubernetes component logs)
    (re.compile(r'[IWEF](\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+)'), 'klog'),
    # Python/Java: 2024-01-15 14:03:17,123 or .123
    (re.compile(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,\.]\d{3})'), 'python_java'),
    # Go log: 2024/01/15 14:03:17
    (re.compile(r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})'), 'go'),
    # Syslog: Jan 15 14:03:17
    (re.compile(r'([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})'), 'syslog'),
    # Epoch millis: 1705326197123
    (re.compile(r'^(\d{13})'), 'epoch_ms'),
    # Epoch seconds: 1705326197
    (re.compile(r'^(\d{10})(?:\.\d+)?'), 'epoch'),
    # RFC 2822: Mon, 15 Jan 2024 14:03:17
    (re.compile(r'([A-Z][a-z]{2},\s+\d{2}\s+[A-Z][a-z]{2}\s+\d{4}\s+\d{2}:\d{2}:\d{2})'), 'rfc2822'),
]


def parse_timestamp(line: str, detected_format: str | None = None) -> datetime | None:
    """Extract a timestamp from a log line.

    If detected_format is given, try only that format first (fast path).
    Falls back to trying all patterns.

    Args:
        line: A single log line to parse.
        detected_format: Optional format hint for fast-path matching.

    Returns:
        A timezone-aware datetime, or None if no timestamp found.
    """
    patterns_to_try = _TS_PATTERNS
    if detected_format:
        patterns_to_try = [p for p in _TS_PATTERNS if p[1] == detected_format] + _TS_PATTERNS

    for regex, fmt in patterns_to_try:
        m = regex.search(line)
        if not m:
            continue
        raw = m.group(1)
        try:
            if fmt == 'iso8601':
                return datetime.fromisoformat(raw.replace('Z', '+00:00'))
            elif fmt == 'klog':
                # Format: MMDD HH:MM:SS.ffffff -- no year, assume current year
                now = datetime.now(timezone.utc)
                dt = datetime.strptime(raw, "%m%d %H:%M:%S.%f")
                return dt.replace(year=now.year, tzinfo=timezone.utc)
            elif fmt == 'python_java':
                raw_norm = raw.replace(',', '.')
                return datetime.strptime(raw_norm, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            elif fmt == 'go':
                return datetime.strptime(raw, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elif fmt == 'syslog':
                now = datetime.now(timezone.utc)
                dt = datetime.strptime(raw, "%b %d %H:%M:%S")
                return dt.replace(year=now.year, tzinfo=timezone.utc)
            elif fmt == 'epoch_ms':
                return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
            elif fmt == 'epoch':
                return datetime.fromtimestamp(int(raw), tz=timezone.utc)
            elif fmt == 'rfc2822':
                return datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, OSError, OverflowError):
            continue
    return None


def detect_ts_format(lines: list[str], sample_size: int = 20) -> str | None:
    """Auto-detect timestamp format from the first N lines.

    Args:
        lines: Log lines to sample from.
        sample_size: Number of lines to check.

    Returns:
        Format string (e.g. 'iso8601', 'klog') or None.
    """
    for line in lines[:sample_size]:
        for regex, fmt in _TS_PATTERNS:
            if regex.search(line):
                return fmt
    return None
