"""Causal analysis step — builds resource graph and walks causal chains."""

from __future__ import annotations

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import CausalChain, TriageResult


async def run_causal_analysis(
    triage: TriageResult,
    index: BundleIndex,
) -> list[CausalChain]:
    """Build the resource graph and walk causal chains from symptoms to root causes.

    This runs BEFORE AI analysts — deterministic reasoning first, AI only
    for ambiguous chains that need semantic log analysis.

    Args:
        triage: Triage results with all detected issues.
        index: Bundle index for reading resources.

    Returns:
        List of causal chains linking symptoms to root causes.
    """
    try:
        from bundle_analyzer.graph import ResourceGraph
        from bundle_analyzer.graph.chain_walker import ChainWalker

        # Build the dependency graph
        graph = await ResourceGraph.build(index)
        logger.info(
            "Resource graph: {} nodes, {} edges",
            len(graph.nodes),
            len(graph.edges),
        )

        # Walk causal chains from every triage finding
        walker = ChainWalker(triage, index)
        chains = await walker.walk_all()

        resolved = sum(1 for c in chains if not c.needs_ai)
        needs_ai = sum(1 for c in chains if c.needs_ai)
        logger.info(
            "Causal analysis: {} chains ({} resolved deterministically, {} need AI)",
            len(chains),
            resolved,
            needs_ai,
        )
        return chains

    except (ImportError, AttributeError) as exc:
        logger.debug("Causal analysis not available: {}", exc)
        return []
    except Exception as exc:
        logger.warning("Causal analysis failed: {}", exc)
        return []
