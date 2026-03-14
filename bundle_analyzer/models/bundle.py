"""Bundle metadata model."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class BundleMetadata(BaseModel):
    """Metadata extracted from a Kubernetes support bundle.

    Captures when the bundle was collected, which versions were in use,
    and where the bundle file lives on disk.
    """

    collected_at: datetime | None = None
    kubernetes_version: str | None = None
    troubleshoot_version: str | None = None
    collection_duration_seconds: float | None = None
    bundle_path: Path
