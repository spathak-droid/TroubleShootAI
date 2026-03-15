"""API-specific request and response models.

These are thin wrappers around the core domain models, tailored for
HTTP request/response semantics and WebSocket message framing.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AnalysisStatusEnum(str, Enum):
    """Status of a bundle through the analysis pipeline."""

    uploaded = "uploaded"
    extracting = "extracting"
    triaging = "triaging"
    analyzing = "analyzing"
    complete = "complete"
    error = "error"


class BundleInfo(BaseModel):
    """Summary information about an uploaded bundle."""

    id: str
    filename: str
    status: AnalysisStatusEnum
    uploaded_at: datetime
    completed_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    summary: str | None = None
    finding_count: int = 0
    critical_count: int = 0
    warning_count: int = 0


class AnalysisStatus(BaseModel):
    """Current progress of an analysis pipeline run."""

    bundle_id: str
    status: AnalysisStatusEnum
    progress: float = Field(ge=0.0, le=1.0, default=0.0)
    current_stage: str = ""
    message: str = ""


class UploadResponse(BaseModel):
    """Response returned after a successful bundle upload."""

    bundle_id: str
    filename: str
    message: str = "Bundle uploaded successfully"


class AnalyzeRequest(BaseModel):
    """Request body for starting analysis."""

    context: str | None = None


class InterviewRequest(BaseModel):
    """Request body for asking a question in an ask session."""

    question: str


class InterviewResponse(BaseModel):
    """Response from an ask session question."""

    answer: str
    history: list[dict[str, str]] = Field(default_factory=list)


class DiffRequest(BaseModel):
    """Request body for comparing two bundles."""

    before_bundle_id: str
    after_bundle_id: str


class ProgressMessage(BaseModel):
    """WebSocket message for streaming analysis progress."""

    stage: str
    pct: float = Field(ge=0.0, le=1.0)
    message: str
