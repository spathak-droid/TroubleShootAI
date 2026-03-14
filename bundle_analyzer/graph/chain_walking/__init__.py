"""Causal Chain Walking package — traces symptoms to root causes.

Re-exports the ChainWalker facade for convenient access.
"""

from bundle_analyzer.graph.chain_walking.walker import ChainWalker

__all__ = ["ChainWalker"]
