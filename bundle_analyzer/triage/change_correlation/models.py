"""Data models for change correlation analysis.

Defines the core Pydantic models used to represent detected changes,
their correlations with failures, and the overall change report.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChangeEvent(BaseModel):
    """A detected change in the cluster that may correlate with failures."""

    resource_type: str  # "Deployment", "ConfigMap", "Secret", "Node", etc.
    resource_name: str
    namespace: str = ""
    change_type: Literal[
        "created", "modified", "scaled", "restarted", "deleted", "rolled_out"
    ]
    timestamp: datetime
    detail: str = ""  # human readable description


class ChangeCorrelation(BaseModel):
    """A correlation between a change and a failure."""

    change: ChangeEvent
    failure_description: str  # what broke
    time_delta_seconds: float  # how long after the change the failure appeared
    correlation_strength: Literal["strong", "moderate", "weak"] = "moderate"
    explanation: str = ""  # why this change might have caused the failure
    severity: Literal["critical", "warning", "info"] = "warning"


class ChangeReport(BaseModel):
    """Complete change correlation report."""

    recent_changes: list[ChangeEvent] = Field(default_factory=list)
    correlations: list[ChangeCorrelation] = Field(default_factory=list)
    timeline_window_minutes: int = 60  # how far back we looked
