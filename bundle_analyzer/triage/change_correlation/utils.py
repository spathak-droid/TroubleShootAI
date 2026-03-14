"""Utility functions for change correlation analysis.

Provides timestamp parsing, window checking, item extraction, and
time-delta formatting helpers used across the change correlation package.
"""

from __future__ import annotations

from datetime import datetime, timezone


def parse_k8s_timestamp(ts: str | None) -> datetime | None:
    """Parse a Kubernetes timestamp string to a timezone-aware datetime.

    Args:
        ts: ISO-8601 timestamp string (e.g. ``"2024-01-15T10:30:00Z"``).

    Returns:
        A timezone-aware ``datetime`` or ``None`` if parsing fails.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


STRENGTH_ORDER: dict[str, int] = {"strong": 0, "moderate": 1, "weak": 2}


def in_window(ts: datetime, cutoff: datetime, before: datetime) -> bool:
    """Check whether a timestamp falls within [cutoff, before].

    Handles timezone-naive timestamps by treating them as UTC.

    Args:
        ts: The timestamp to check.
        cutoff: The start of the window.
        before: The end of the window (failure onset).

    Returns:
        True if ``cutoff <= ts <= before``.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    if before.tzinfo is None:
        before = before.replace(tzinfo=timezone.utc)

    return cutoff <= ts <= before


def extract_items(data: dict | list) -> list[dict]:
    """Extract individual resource items from a JSON payload.

    Handles both list-of-items format and single-resource format.

    Args:
        data: Parsed JSON -- could be a dict, a list, or a dict with
              an ``items`` key.

    Returns:
        A flat list of resource dicts.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "items" in data:
            items = data["items"]
            return items if isinstance(items, list) else []
        return [data]
    return []


def format_delta(seconds: float) -> str:
    """Format a time delta in seconds into a human-readable string.

    Args:
        seconds: Number of seconds.

    Returns:
        A string like ``"3 minutes"`` or ``"about 1 hour"``.
    """
    if seconds < 60:
        return f"{int(seconds)} seconds"
    if seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = seconds / 3600
    return f"about {hours:.1f} hours"
