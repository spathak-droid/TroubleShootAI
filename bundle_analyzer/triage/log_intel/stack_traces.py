"""Stack trace detection and grouping.

Detects Java, Python, Go, and .NET stack traces, groups duplicates
by exception type and top frames, and extracts exception info.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from bundle_analyzer.models import StackTraceGroup

from .constants import MAX_TRACE_GROUPS


# ── Start patterns per language ───────────────────────────────────────

_TRACE_START: list[tuple[str, re.Pattern[str]]] = [
    ("java", re.compile(r'(?:Exception\s+in\s+thread|^\s*(?:[\w$.]+(?:Exception|Error)):)', re.I | re.M)),
    ("python", re.compile(r'Traceback\s+\(most\s+recent\s+call\s+last\):', re.I)),
    ("go", re.compile(r'(?:^goroutine\s+\d+\s+\[|^panic:)', re.M)),
    ("dotnet", re.compile(r'(?:Unhandled\s+Exception:|System\.[\w.]+Exception:)', re.I)),
]

# ── Continuation patterns per language ────────────────────────────────

_TRACE_CONT: dict[str, re.Pattern[str]] = {
    "java": re.compile(r'^\s+at\s+|^Caused\s+by:', re.M),
    "python": re.compile(r'^\s+File\s+"|^\s+.*Error:', re.M),
    "go": re.compile(r'^\s+.*\.go:\d+|^\s+.*\+0x', re.M),
    "dotnet": re.compile(r'^\s+at\s+', re.M),
}


def detect_stack_traces(
    lines: list[str],
    timestamps: list[datetime | None],
) -> list[StackTraceGroup]:
    """Detect and group stack traces from log lines.

    Args:
        lines: All log lines from a container.
        timestamps: Parsed timestamps aligned with lines.

    Returns:
        Stack trace groups sorted by count (most frequent first).
    """
    groups: dict[str, StackTraceGroup] = {}
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        detected_lang: str | None = None

        for lang, start_re in _TRACE_START:
            if start_re.search(line):
                detected_lang = lang
                break

        if detected_lang is None:
            i += 1
            continue

        # Collect the full trace
        trace_lines = [line]
        cont_re = _TRACE_CONT.get(detected_lang)
        j = i + 1
        while j < n and cont_re and cont_re.search(lines[j]):
            trace_lines.append(lines[j])
            j += 1

        # For Python, the exception line comes after the File lines
        if detected_lang == "python" and j < n:
            trace_lines.append(lines[j])
            j += 1

        full_trace = "\n".join(trace_lines)

        # Extract exception type and message
        exc_type, exc_msg = extract_exception_info(trace_lines, detected_lang)

        # Group key: language + exception type + hash of top 3 frames
        frame_lines = [l.strip() for l in trace_lines[1:4] if l.strip()]
        frame_hash = hashlib.md5("".join(frame_lines).encode()).hexdigest()[:8]
        group_key = f"{detected_lang}:{exc_type}:{frame_hash}"

        ts = timestamps[i] if i < len(timestamps) else None

        if group_key in groups:
            grp = groups[group_key]
            grp.count += 1
            if ts:
                grp.last_seen = ts
        elif len(groups) < MAX_TRACE_GROUPS:
            groups[group_key] = StackTraceGroup(
                language=detected_lang,
                exception_type=exc_type,
                exception_message=exc_msg,
                frames=frame_lines[:10],
                count=1,
                first_seen=ts,
                last_seen=ts,
                sample_full_trace=full_trace[:2000],
            )

        i = j  # skip past the trace

    return sorted(groups.values(), key=lambda g: g.count, reverse=True)


def extract_exception_info(
    trace_lines: list[str], lang: str
) -> tuple[str, str]:
    """Extract exception type and message from a stack trace.

    Args:
        trace_lines: Lines comprising the full stack trace.
        lang: Detected language ('java', 'python', 'go', 'dotnet').

    Returns:
        Tuple of (exception_type, exception_message).
    """
    first_line = trace_lines[0].strip()
    last_line = trace_lines[-1].strip() if trace_lines else first_line

    if lang == "java":
        # "java.lang.NullPointerException: message"
        m = re.search(r'([\w$.]+(?:Exception|Error))(?::\s*(.*))?', first_line)
        if m:
            return m.group(1), m.group(2) or ""
    elif lang == "python":
        # Last line is "ValueError: message"
        m = re.match(r'(\w+(?:Error|Exception|Warning))(?::\s*(.*))?', last_line)
        if m:
            return m.group(1), m.group(2) or ""
    elif lang == "go":
        if first_line.startswith("panic:"):
            msg = first_line[6:].strip()
            return "panic", msg
        m = re.match(r'goroutine\s+\d+\s+\[([^\]]+)\]', first_line)
        if m:
            return "goroutine_blocked", m.group(1)
    elif lang == "dotnet":
        m = re.search(r'(System\.[\w.]+Exception)(?::\s*(.*))?', first_line)
        if m:
            return m.group(1), m.group(2) or ""

    return "UnknownException", first_line[:200]
