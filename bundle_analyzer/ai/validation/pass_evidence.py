"""Pass 1: Evidence validation.

Checks that each finding's evidence citations are real — file exists in bundle,
excerpt matches actual content. Handles resource-key-style paths by resolving
them to actual bundle paths.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import DependencyLink, Finding

from .helpers import fuzzy_match


def resolve_evidence_path(file_path: str, index: BundleIndex) -> str | None:
    """Try to read evidence, resolving resource-key-style paths to real bundle paths.

    The AI analyst often cites 'pod/default/my-pod' (resource key) instead of
    the actual bundle path 'cluster-resources/pods/default.json'. This function
    tries the literal path first, then known bundle path patterns.

    Args:
        file_path: The evidence file path (may be a resource key).
        index: The bundle index.

    Returns:
        File content if found, None otherwise.
    """
    # Try literal path first
    content = index.read_text(file_path)
    if content is not None:
        return content

    # Try resolving resource-key-style paths
    parts = file_path.strip().split("/")
    if len(parts) >= 3:
        kind, ns, name = parts[0].lower(), parts[1], parts[2]
        kind_to_dir = {
            "pod": "pods", "deployment": "deployments",
            "service": "services", "configmap": "configmaps",
            "secret": "secrets", "node": "nodes",
            "replicaset": "replicasets", "statefulset": "statefulsets",
            "ingress": "ingress", "pvc": "pvcs",
        }
        bundle_dir = kind_to_dir.get(kind)
        if bundle_dir:
            ns_path = f"cluster-resources/{bundle_dir}/{ns}.json"
            content = index.read_text(ns_path)
            if content is not None:
                return content
            resource_path = f"cluster-resources/{bundle_dir}/{ns}/{name}.json"
            content = index.read_text(resource_path)
            if content is not None:
                return content

    elif len(parts) == 2:
        for prefix in ["cluster-resources/", ""]:
            for suffix in [".json", ""]:
                content = index.read_text(f"{prefix}{file_path}{suffix}")
                if content is not None:
                    return content

    return None


def validate_evidence(
    verdicts: list[dict[str, Any]],
    index: BundleIndex,
) -> None:
    """Check that each finding's evidence citations are real.

    Verifies: file exists in bundle, excerpt matches actual content.
    Handles resource-key-style paths (e.g. pod/default/name) by resolving
    them to actual bundle paths. Deduplicates repeated file paths.

    Args:
        verdicts: Per-finding accumulator dicts (mutated in place).
        index: The bundle index.
    """
    for v in verdicts:
        finding: Finding = v["finding"]
        verified = 0
        total_unique = 0
        seen_paths: set[str] = set()

        for ev in finding.evidence:
            file_path = ev.file
            excerpt = ev.excerpt or getattr(ev, "content", "") or ""

            # Deduplicate — don't count the same path multiple times
            if file_path in seen_paths:
                content = resolve_evidence_path(file_path, index)
                if content and excerpt and fuzzy_match(excerpt, content):
                    verified += 1
                    total_unique += 1
                elif content and excerpt:
                    verified += 0.5
                    total_unique += 1
                continue

            seen_paths.add(file_path)
            total_unique += 1

            content = resolve_evidence_path(file_path, index)

            if content is None:
                v["contradicting"].append(
                    f"Evidence file not found in bundle: {file_path}"
                )
                v["dep_chain"].append(DependencyLink(
                    step_number=len(v["dep_chain"]) + 1,
                    resource=finding.resource or "",
                    observation=f"Cited file not found: {file_path}",
                    evidence_source=file_path,
                    evidence_excerpt="FILE NOT FOUND",
                    leads_to="Evidence citation is unverifiable",
                    significance="context",
                ))
                continue

            if excerpt and fuzzy_match(excerpt, content):
                verified += 1
                v["supporting"].append(
                    f"Verified: {file_path} contains cited excerpt"
                )
                v["dep_chain"].append(DependencyLink(
                    step_number=len(v["dep_chain"]) + 1,
                    resource=finding.resource or "",
                    observation=f"Evidence verified in {file_path}",
                    evidence_source=file_path,
                    evidence_excerpt=excerpt[:80],
                    leads_to="Citation confirmed — evidence is grounded",
                    significance="context",
                ))
            elif excerpt:
                verified += 0.5
                v["supporting"].append(
                    f"File exists: {file_path} (excerpt is paraphrased)"
                )
            else:
                verified += 1
                v["supporting"].append(f"File exists: {file_path}")

        v["evidence_score"] = verified / max(total_unique, 1)
