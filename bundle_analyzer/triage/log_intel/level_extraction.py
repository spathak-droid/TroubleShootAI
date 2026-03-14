"""Log level extraction from various log formats.

Supports JSON structured logs, klog prefixes, bracket/colon formats,
and key=value formats.
"""

from __future__ import annotations

import re


# JSON structured logs
_JSON_LEVEL_RE: re.Pattern[str] = re.compile(r'"(?:level|severity|log\.level)":\s*"(\w+)"', re.IGNORECASE)

# Klog prefix: I/W/E/F at start
_KLOG_LEVEL_MAP: dict[str, str] = {'I': 'INFO', 'W': 'WARN', 'E': 'ERROR', 'F': 'FATAL'}

# Bracket or colon formats: [ERROR], ERROR:, level=error
_BRACKET_LEVEL_RE: re.Pattern[str] = re.compile(
    r'(?:\[|\b)(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE|CRITICAL)(?:\]|:|\s)',
    re.IGNORECASE,
)

# level=X format (structured text logs)
_KV_LEVEL_RE: re.Pattern[str] = re.compile(r'\blevel=(\w+)', re.IGNORECASE)

_LEVEL_NORMALIZE: dict[str, str] = {
    'fatal': 'FATAL', 'critical': 'FATAL',
    'error': 'ERROR', 'err': 'ERROR',
    'warn': 'WARN', 'warning': 'WARN',
    'info': 'INFO',
    'debug': 'DEBUG',
    'trace': 'TRACE',
}


def extract_level(line: str) -> str:
    """Extract log level from a line.

    Tries JSON, klog, bracket/colon, and key=value formats in order.

    Args:
        line: A single log line.

    Returns:
        Normalized level string (e.g. 'ERROR', 'WARN') or 'UNKNOWN'.
    """
    # JSON structured
    m = _JSON_LEVEL_RE.search(line)
    if m:
        return _LEVEL_NORMALIZE.get(m.group(1).lower(), m.group(1).upper())

    # Klog: starts with E0115, W0115, etc.
    if len(line) >= 5 and line[0] in _KLOG_LEVEL_MAP and line[1:5].isdigit():
        return _KLOG_LEVEL_MAP[line[0]]

    # Bracket/colon format
    m = _BRACKET_LEVEL_RE.search(line[:80])  # only search beginning
    if m:
        return _LEVEL_NORMALIZE.get(m.group(1).lower(), m.group(1).upper())

    # key=value format
    m = _KV_LEVEL_RE.search(line[:120])
    if m:
        return _LEVEL_NORMALIZE.get(m.group(1).lower(), m.group(1).upper())

    return 'UNKNOWN'
