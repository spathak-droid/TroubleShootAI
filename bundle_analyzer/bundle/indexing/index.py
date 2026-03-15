"""BundleIndex -- the main class for bundle file indexing and access."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from bundle_analyzer.bundle.indexing import factory, iterators, log_streaming, readers
from bundle_analyzer.bundle.indexing.factory import BundleMetadata


class BundleIndex:
    """In-memory index over an extracted Troubleshoot support bundle.

    All file reads during triage/analysis MUST go through this class so
    that encoding, redaction markers, and missing-file handling are
    consistent.

    Attributes:
        root: Absolute path to the extracted bundle directory.
        manifest: Mapping of logical resource names to filesystem paths.
        namespaces: Kubernetes namespaces discovered from the directory tree.
        has_data: Quick lookup -- does the bundle contain a given data type?
        rbac_errors: Collection errors found in the bundle (RBAC denied, etc.).
        metadata: Parsed :class:`BundleMetadata` for the bundle.
    """

    def __init__(
        self,
        root: Path,
        manifest: dict[str, Path],
        namespaces: list[str],
        has_data: dict[str, bool],
        rbac_errors: list[str],
        metadata: BundleMetadata,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.namespaces = namespaces
        self.has_data = has_data
        self.rbac_errors = rbac_errors
        self.metadata = metadata

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def build(cls, root: Path) -> BundleIndex:
        """Scan an extracted bundle directory and build the index.

        Args:
            root: Path to the top-level directory of the extracted bundle.

        Returns:
            A fully-populated :class:`BundleIndex`.
        """
        return await factory.build(cls, root)

    @classmethod
    def _build_sync(cls, root: Path) -> BundleIndex:
        """Blocking helper that walks the filesystem."""
        return factory.build_sync(cls, root)

    @classmethod
    def _parse_metadata(cls, root: Path) -> BundleMetadata:
        """Extract bundle metadata from version.yaml or similar files."""
        return factory.parse_metadata(root)

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    def _resolve_path(self, path: str) -> Path:
        """Turn a relative-to-bundle path into an absolute path."""
        return readers.resolve_path(self.root, path)

    def read_json(self, path: str) -> dict[str, Any] | list[Any] | None:
        """Safely read and parse a JSON file relative to the bundle root.

        Args:
            path: Relative path within the bundle (e.g.
                  ``cluster-resources/pods/default/my-pod.json``).

        Returns:
            Parsed JSON (dict or list) or ``None`` if the file is missing
            or cannot be parsed.
        """
        return readers.read_json(self.root, path)

    def read_text(self, path: str) -> str | None:
        """Safely read a text file relative to the bundle root.

        Args:
            path: Relative path within the bundle.

        Returns:
            File content as a string or ``None`` if missing/unreadable.
        """
        return readers.read_text(self.root, path)

    # ------------------------------------------------------------------
    # Log streaming
    # ------------------------------------------------------------------

    def stream_log(
        self,
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
        return log_streaming.stream_log(
            self.root, namespace, pod, container, previous, last_n_lines, first_n_lines,
        )

    @staticmethod
    def _stream_tail(path: Path, n: int) -> Iterator[str]:
        """Yield the last *n* lines of a file using a deque ring buffer."""
        return log_streaming.stream_tail(path, n)

    @staticmethod
    def _stream_previous(path: Path, head: int, tail: int) -> Iterator[str]:
        """Yield first *head* + last *tail* lines (with separator)."""
        return log_streaming.stream_previous(path, head, tail)

    def stream_log_full(
        self,
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
            namespace: Kubernetes namespace.
            pod: Pod name.
            container: Container name.
            previous: If True, look for the previous-log file.

        Yields:
            Individual log lines (without trailing newline).
        """
        return log_streaming.stream_log_full(self.root, namespace, pod, container, previous)

    def find_log_path(
        self,
        namespace: str,
        pod: str,
        container: str,
        previous: bool = False,
    ) -> Path | None:
        """Resolve the filesystem path for a container log.

        Args:
            namespace: Kubernetes namespace.
            pod: Pod name.
            container: Container name.
            previous: If True, look for the previous-log file.

        Returns:
            Absolute Path to the log file, or None if not found.
        """
        return log_streaming.find_log_path(self.root, namespace, pod, container, previous)

    # ------------------------------------------------------------------
    # Iterators
    # ------------------------------------------------------------------

    def get_all_pods(self) -> Iterator[dict[str, Any]]:
        """Yield every pod JSON object found in the bundle.

        Walks ``cluster-resources/pods/<namespace>/<pod>.json`` and yields
        the parsed dict for each file.
        """
        return iterators.get_all_pods(self.root)

    def get_events(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """Return cluster events, optionally filtered by namespace.

        Args:
            namespace: If provided, only return events from this namespace.

        Returns:
            List of event dicts, most-recent first.
        """
        return iterators.get_events(self.root, namespace)

    def read_existing_analysis(self) -> list[dict[str, Any]]:
        """Read the bundle's own analysis results, if present.

        Troubleshoot bundles may contain ``analysis.json`` with pre-computed
        analysis from the collector's analyzers.

        Returns:
            List of analysis result dicts, or empty list.
        """
        return iterators.read_existing_analysis(self.root, self.read_json)

    def read_preflight_results(self) -> list[dict[str, Any]]:
        """Read preflight check results from the bundle, if present.

        Returns:
            List of preflight result dicts, or empty list.
        """
        return iterators.read_preflight_results(self.root, self.read_json)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def has(self, resource_type: str) -> bool:
        """Check whether the bundle contains data for *resource_type*.

        Args:
            resource_type: Logical name (e.g. ``"pods"``, ``"node_metrics"``).
        """
        return self.has_data.get(resource_type, False)

    def __repr__(self) -> str:
        return (
            f"BundleIndex(root={self.root!r}, "
            f"namespaces={len(self.namespaces)}, "
            f"data_types={sum(1 for v in self.has_data.values() if v)})"
        )
