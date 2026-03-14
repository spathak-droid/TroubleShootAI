"""Backward-compatibility shim — re-exports ChainWalker from the new package.

The implementation has been refactored into the ``chain_walking`` sub-package.
Import from here continues to work for all existing callers.
"""

from bundle_analyzer.graph.chain_walking import ChainWalker  # noqa: F401

__all__ = ["ChainWalker"]
