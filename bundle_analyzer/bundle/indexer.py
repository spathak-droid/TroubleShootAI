"""Backward-compatible shim -- re-exports from the new indexing package.

All imports of ``from bundle_analyzer.bundle.indexer import BundleIndex``
continue to work unchanged.
"""

from bundle_analyzer.bundle.indexing import BundleIndex, REDACTED_MARKER

__all__ = ["BundleIndex", "REDACTED_MARKER"]
