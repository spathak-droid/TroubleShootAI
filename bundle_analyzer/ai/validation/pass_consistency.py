"""Pass 3: Chain consistency check.

Compares ChainWalker's deterministic causal traces against AI findings
to assess whether the AI's root cause analysis agrees with hard evidence.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models import CausalChain, DependencyLink, Finding

from .helpers import extract_keywords, normalize_resource_key

# Domain synonyms — terms that mean the same thing in K8s context
_SYNONYMS: list[set[str]] = [
    {"probe", "liveness", "readiness", "healthcheck", "health"},
    {"oom", "memory", "oomkilled", "killed"},
    {"crash", "crashloop", "crashloopbackoff", "restart", "restarting"},
    {"config", "configmap", "configuration", "missing"},
    {"image", "imagepull", "imagepullbackoff", "pull"},
    {"pending", "unschedulable", "scheduling"},
    {"permission", "rbac", "forbidden"},
]


def _expand_keywords(kws: set[str]) -> set[str]:
    """Expand a keyword set with domain synonyms.

    Args:
        kws: Original keywords.

    Returns:
        Expanded keyword set including synonym matches.
    """
    expanded = set(kws)
    for group in _SYNONYMS:
        if kws & group:
            expanded |= group
    return expanded


def check_chain_consistency(
    verdicts: list[dict[str, Any]],
    chains: list[CausalChain],
) -> None:
    """Compare ChainWalker's deterministic traces against AI findings.

    Updates verdict accumulators with correctness assessment and
    chain-derived dependency links.

    Args:
        verdicts: Per-finding accumulator dicts (mutated in place).
        chains: Causal chains from ChainWalker.
    """
    if not chains:
        return

    # Build chain lookup by resource key
    chain_by_resource: dict[str, CausalChain] = {}
    for chain in chains:
        key = normalize_resource_key(chain.symptom_resource)
        chain_by_resource[f"{key[0]}/{key[1]}/{key[2]}"] = chain
        chain_by_resource[f"{key[1]}/{key[2]}"] = chain

    for v in verdicts:
        finding: Finding = v["finding"]
        if not finding.resource:
            continue

        key = normalize_resource_key(finding.resource)
        chain = (
            chain_by_resource.get(f"{key[0]}/{key[1]}/{key[2]}")
            or chain_by_resource.get(f"{key[1]}/{key[2]}")
        )
        if chain is None:
            continue

        # Convert chain steps to DependencyLinks
        for i, step in enumerate(chain.steps):
            v["dep_chain"].append(DependencyLink(
                step_number=len(v["dep_chain"]) + 1,
                resource=step.resource,
                observation=step.observation,
                evidence_source=step.evidence_file,
                evidence_excerpt=step.evidence_excerpt[:80],
                leads_to=chain.steps[i + 1].observation if i + 1 < len(chain.steps) else "-> root cause",
                significance="root_cause" if i == len(chain.steps) - 1 else "contributing",
            ))

        # Compare root causes using keyword overlap + domain synonym matching
        if chain.root_cause and finding.root_cause:
            chain_kw = extract_keywords(chain.root_cause)
            finding_kw = extract_keywords(finding.root_cause)

            expanded_chain = _expand_keywords(chain_kw)
            expanded_finding = _expand_keywords(finding_kw)

            if expanded_chain and expanded_finding:
                overlap = len(expanded_chain & expanded_finding)
                union = len(expanded_chain | expanded_finding)
                ratio = overlap / max(union, 1)
                raw_overlap = len(chain_kw & finding_kw)

                if ratio >= 0.3 or raw_overlap >= 2:
                    v["chain_match"] = "Correct"
                    v["chain_factor"] = 1.0
                    v["supporting"].append(
                        f"ChainWalker agrees: '{chain.root_cause}'"
                    )
                elif ratio >= 0.15 or raw_overlap >= 1:
                    v["chain_match"] = "Partially Correct"
                    v["chain_factor"] = 0.7
                    v["supporting"].append(
                        f"ChainWalker partially agrees: '{chain.root_cause}'"
                    )
                else:
                    v["chain_match"] = "Incorrect"
                    v["chain_factor"] = 0.4
                    v["contradicting"].append(
                        f"ChainWalker disagrees — found: '{chain.root_cause}'"
                    )
                    v["stronger_alternative"] = chain.root_cause

        elif chain.root_cause:
            v["chain_match"] = "Partially Correct"
            v["chain_factor"] = 0.6
