"""Bundle indexing package -- split from the monolithic indexer.py module."""

from bundle_analyzer.bundle.indexing.constants import REDACTED_MARKER
from bundle_analyzer.bundle.indexing.index import BundleIndex

__all__ = ["BundleIndex", "REDACTED_MARKER"]
