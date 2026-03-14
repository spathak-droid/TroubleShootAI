"""Constants and utility functions for the chain walking package."""

from __future__ import annotations

import re
import uuid


# ── Known error patterns in log output ───────────────────────────────

_LOG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)out of memory|OOM|cannot allocate"), "out_of_memory"),
    (re.compile(r"(?i)connection refused|ECONNREFUSED|dial tcp.*refused"), "connection_refused"),
    (re.compile(r"(?i)permission denied|forbidden|RBAC"), "permission_denied"),
    (re.compile(r"(?i)no such file|FileNotFoundError|ENOENT"), "file_not_found"),
    (re.compile(r"(?i)timeout|deadline exceeded"), "timeout"),
    (re.compile(r"(?i)crash|panic|fatal|SIGSEGV|SIGABRT"), "crash_signal"),
]


def _gen_id() -> str:
    """Generate a short unique chain identifier."""
    return uuid.uuid4().hex[:8]
