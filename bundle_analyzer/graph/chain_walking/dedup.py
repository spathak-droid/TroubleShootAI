"""Deduplication logic for causal chains."""

from __future__ import annotations

from bundle_analyzer.models import CausalChain


def deduplicate(chains: list[CausalChain]) -> list[CausalChain]:
    """Deduplicate chains that share the same root cause.

    When multiple chains have identical root causes, merge their related
    resources into the chain with the highest confidence.

    Args:
        chains: List of CausalChain objects to deduplicate.

    Returns:
        Deduplicated list of CausalChain objects.
    """
    if not chains:
        return []

    by_cause: dict[str, list[CausalChain]] = {}
    no_cause: list[CausalChain] = []

    for chain in chains:
        if chain.root_cause:
            by_cause.setdefault(chain.root_cause, []).append(chain)
        else:
            no_cause.append(chain)

    result: list[CausalChain] = []
    for _cause, group in by_cause.items():
        if len(group) == 1:
            result.append(group[0])
        else:
            # Keep the one with highest confidence, merge related resources
            group.sort(key=lambda c: c.confidence, reverse=True)
            best = group[0]
            all_related = set(best.related_resources)
            for other in group[1:]:
                all_related.add(other.symptom_resource)
                all_related.update(other.related_resources)
            all_related.discard(best.symptom_resource)
            result.append(best.model_copy(update={
                "related_resources": sorted(all_related),
            }))

    result.extend(no_cause)
    return result
