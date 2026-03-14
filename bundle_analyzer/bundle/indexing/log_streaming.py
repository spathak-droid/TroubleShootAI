"""Log streaming methods for BundleIndex."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from pathlib import Path

from loguru import logger


def find_log_path(
    root: Path,
    namespace: str,
    pod: str,
    container: str,
    previous: bool = False,
) -> Path | None:
    """Resolve the filesystem path for a container log.

    Uses candidate-path logic covering common bundle layouts. Returns None
    if no log file is found.

    Args:
        root: Bundle root directory.
        namespace: Kubernetes namespace.
        pod: Pod name.
        container: Container name.
        previous: If True, look for the previous-log file.

    Returns:
        Absolute Path to the log file, or None if not found.
    """
    suffix = "-previous.log" if previous else ".log"
    candidates = [
        root / namespace / pod / f"{container}{suffix}",
        root / "pods" / namespace / pod / f"{container}{suffix}",
        root / namespace / pod / container / f"{container}{suffix}",
        root / namespace / pod / f"{container}.log",
        root / "cluster-resources" / "pods" / "logs" / namespace / pod / f"{container}{suffix}",
    ]
    if previous:
        candidates.append(root / namespace / pod / "previous" / f"{container}.log")

    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def stream_log(
    root: Path,
    namespace: str,
    pod: str,
    container: str,
    previous: bool = False,
    last_n_lines: int = 200,
    first_n_lines: int = 50,
) -> Iterator[str]:
    """Yield log lines for a specific container, streamed from disk.

    For *current* logs: yields the last *last_n_lines* lines (crash
    information is usually at the end).

    For *previous* logs: yields the first *first_n_lines* lines (startup
    context) **and** the last *last_n_lines* lines (crash context).

    ``***HIDDEN***`` redaction markers are yielded as-is and are **not**
    treated as errors.

    Args:
        root: Bundle root directory.
        namespace: Kubernetes namespace.
        pod: Pod name.
        container: Container name.
        previous: If True, look for the previous-log file.
        last_n_lines: Number of lines to yield from the tail.
        first_n_lines: Number of lines to yield from the head (previous
                       logs only).

    Yields:
        Individual log lines (without trailing newline).
    """
    log_path = find_log_path(root, namespace, pod, container, previous)
    if log_path is None:
        return  # gracefully yield nothing

    try:
        if previous:
            yield from stream_previous(log_path, first_n_lines, last_n_lines)
        else:
            yield from stream_tail(log_path, last_n_lines)
    except OSError as exc:
        logger.warning("Error streaming log {}: {}", log_path, exc)


def stream_tail(path: Path, n: int) -> Iterator[str]:
    """Yield the last *n* lines of a file using a deque ring buffer.

    Args:
        path: Path to the log file.
        n: Number of trailing lines to yield.

    Yields:
        Individual log lines (without trailing newline).
    """
    ring: deque[str] = deque(maxlen=n)
    with open(path, errors="replace") as fh:
        for line in fh:
            ring.append(line.rstrip("\n"))
    yield from ring


def stream_previous(path: Path, head: int, tail: int) -> Iterator[str]:
    """Yield first *head* + last *tail* lines (with separator).

    Args:
        path: Path to the log file.
        head: Number of lines to yield from the start.
        tail: Number of lines to yield from the end.

    Yields:
        Individual log lines (without trailing newline).
    """
    head_lines: list[str] = []
    tail_ring: deque[str] = deque(maxlen=tail)
    total = 0
    with open(path, errors="replace") as fh:
        for line in fh:
            stripped = line.rstrip("\n")
            total += 1
            if total <= head:
                head_lines.append(stripped)
            tail_ring.append(stripped)

    yield from head_lines
    # If the file is short enough that head covers everything, don't
    # duplicate lines.
    if total > head:
        yield f"--- [skipped {total - head - len(tail_ring)} lines] ---"
        # Only yield tail lines that weren't already in head
        for tl in tail_ring:
            if total - len(tail_ring) >= head:
                yield tl


def stream_log_full(
    root: Path,
    namespace: str,
    pod: str,
    container: str,
    previous: bool = False,
) -> Iterator[str]:
    """Yield ALL log lines for a container, streamed from disk.

    Unlike stream_log, this yields every line without head/tail
    truncation. Used by LogIntelligenceEngine for full-file
    statistical analysis. Memory-safe: yields one line at a time.

    Args:
        root: Bundle root directory.
        namespace: Kubernetes namespace.
        pod: Pod name.
        container: Container name.
        previous: If True, look for the previous-log file.

    Yields:
        Individual log lines (without trailing newline).
    """
    log_path = find_log_path(root, namespace, pod, container, previous)
    if log_path is None:
        return

    try:
        with open(log_path, errors="replace") as fh:
            for line in fh:
                yield line.rstrip("\n")
    except OSError as exc:
        logger.warning("Error streaming full log {}: {}", log_path, exc)
