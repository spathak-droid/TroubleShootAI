"""Helper utilities for the forward prediction engine.

Provides node collection, Kubernetes memory parsing, and certificate
expiry extraction used across multiple prediction modules.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex


def get_all_nodes(index: BundleIndex) -> list[dict]:
    """Collect all node JSON objects from the bundle.

    Args:
        index: The indexed support bundle.

    Returns:
        List of node dicts.
    """
    nodes: list[dict] = []
    nodes_dir = index.root / "cluster-resources" / "nodes"

    if nodes_dir.is_dir():
        for node_file in sorted(nodes_dir.glob("*.json")):
            rel = str(node_file.relative_to(index.root))
            data = index.read_json(rel)
            if isinstance(data, dict):
                if "items" in data:
                    items = data["items"]
                    if isinstance(items, list):
                        nodes.extend(items)
                else:
                    nodes.append(data)
            elif isinstance(data, list):
                nodes.extend(data)
    else:
        data = index.read_json("cluster-resources/nodes.json")
        if isinstance(data, dict):
            items = data.get("items", [])
            nodes = items if isinstance(items, list) else []
        elif isinstance(data, list):
            nodes = data

    return nodes


def parse_k8s_memory(value: str | None) -> int | None:
    """Parse Kubernetes memory quantity string to bytes.

    Handles Ki, Mi, Gi, Ti, and plain integer (bytes) formats.

    Args:
        value: Memory string like "128Mi", "2Gi", "1073741824".

    Returns:
        Value in bytes or None if unparseable.
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
        "k": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }

    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return int(float(value[: -len(suffix)]) * mult)
            except ValueError:
                return None

    try:
        return int(value)
    except ValueError:
        return None


def parse_cert_expiry(b64_cert: str) -> datetime | None:
    """Extract the NotAfter date from a base64-encoded X.509 certificate.

    Uses a regex-based approach to find the expiry without requiring
    the cryptography library.

    Args:
        b64_cert: Base64-encoded PEM certificate data (from K8s secret).

    Returns:
        Certificate expiry datetime (UTC) or None.
    """
    try:
        cert_bytes = base64.b64decode(b64_cert)
        cert_text = cert_bytes.decode("utf-8", errors="replace")

        # Try to find NotAfter in human-readable PEM text (unlikely in DER)
        # For DER-encoded certs we'd need the cryptography library.
        # Best-effort: look for date patterns after "Not After"
        match = re.search(
            r"Not After\s*:\s*(.+?)(?:\n|$)", cert_text, re.IGNORECASE
        )
        if match:
            date_str = match.group(1).strip()
            # Common OpenSSL format: "Mar 15 12:00:00 2025 GMT"
            try:
                return datetime.strptime(date_str, "%b %d %H:%M:%S %Y %Z").replace(
                    tzinfo=UTC
                )
            except ValueError:
                pass
    except (ValueError, TypeError) as exc:
        logger.debug("Could not parse certificate: {}", exc)

    return None
