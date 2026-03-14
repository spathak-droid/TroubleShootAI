"""Reader methods for BundleIndex -- JSON, text, and path resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger


def resolve_path(root: Path, path: str) -> Path:
    """Turn a relative-to-bundle path into an absolute path.

    Args:
        root: Bundle root directory.
        path: Relative path within the bundle.

    Returns:
        Absolute path.
    """
    return root / path


def read_json(root: Path, path: str) -> dict[str, Any] | list[Any] | None:
    """Safely read and parse a JSON file relative to the bundle root.

    Args:
        root: Bundle root directory.
        path: Relative path within the bundle (e.g.
              ``cluster-resources/pods/default/my-pod.json``).

    Returns:
        Parsed JSON (dict or list) or ``None`` if the file is missing
        or cannot be parsed.
    """
    full = resolve_path(root, path)
    if not full.is_file():
        return None
    try:
        content = full.read_text(errors="replace")
        return json.loads(content)  # type: ignore[return-value]
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read JSON {}: {}", full, exc)
        return None


def read_text(root: Path, path: str) -> str | None:
    """Safely read a text file relative to the bundle root.

    Args:
        root: Bundle root directory.
        path: Relative path within the bundle.

    Returns:
        File content as a string or ``None`` if missing/unreadable.
    """
    full = resolve_path(root, path)
    if not full.is_file():
        return None
    try:
        return full.read_text(errors="replace")
    except OSError as exc:
        logger.warning("Failed to read text {}: {}", full, exc)
        return None
