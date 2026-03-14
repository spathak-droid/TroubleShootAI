"""Helper functions for deterministic validation.

Provides text normalization, keyword extraction, and fuzzy matching
utilities used across validation passes.
"""

from __future__ import annotations

import re


def normalize_resource_key(resource: str) -> tuple[str, str, str]:
    """Parse a resource string like 'Pod/default/my-pod' into (kind, ns, name).

    Args:
        resource: Resource string from a finding.

    Returns:
        Tuple of (kind_lower, namespace, name). Empty strings for missing parts.
    """
    parts = resource.strip().split("/")
    if len(parts) >= 3:
        return (parts[0].lower(), parts[1], parts[2])
    if len(parts) == 2:
        return (parts[0].lower(), "", parts[1])
    return (resource.lower(), "", "")


def extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from a root cause / description string.

    Args:
        text: Natural language text.

    Returns:
        Set of lowercase keywords (length > 2).
    """
    words = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).split()
    stop = {"the", "and", "for", "was", "are", "this", "that", "with", "from", "has", "not", "but"}
    return {w for w in words if len(w) > 2 and w not in stop}


def fuzzy_match(excerpt: str, content: str) -> bool:
    """Check if an excerpt appears in content with fuzzy whitespace matching.

    Args:
        excerpt: The claimed excerpt from evidence.
        content: The actual file content.

    Returns:
        True if the excerpt (or a normalized version) is found in content.
    """
    if not excerpt or not content:
        return False

    # Direct substring
    if excerpt in content:
        return True

    # Normalize whitespace for both
    norm_excerpt = " ".join(excerpt.split()).lower()
    norm_content = " ".join(content.split()).lower()

    if norm_excerpt in norm_content:
        return True

    # Check if first 60 chars of excerpt match (LLM may have truncated)
    short = norm_excerpt[:60]
    if len(short) > 15 and short in norm_content:
        return True

    return False
