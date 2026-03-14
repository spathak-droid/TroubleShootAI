"""AI analysis output models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A citation linking a finding to a specific file and excerpt in the bundle.

    Forces grounding of AI analysis in actual bundle data to prevent hallucination.
    """

    file: str  # e.g. "cluster-resources/pods/demo-app/api-server.json"
    excerpt: str  # the specific data cited
    line_number: int | None = None


class Fix(BaseModel):
    """A recommended remediation action for a finding.

    May include a YAML patch, kubectl commands, and a risk assessment.
    """

    description: str
    yaml_patch: str | None = None
    commands: list[str] = Field(default_factory=list)
    risk: Literal["safe", "disruptive", "needs-verification"] = "needs-verification"


class Finding(BaseModel):
    """A single finding from AI analysis.

    Represents one detected issue with root cause analysis, evidence citations,
    a confidence score, and an optional fix.
    """

    id: str
    severity: Literal["critical", "warning", "info"]
    type: str
    resource: str  # "pod/demo-app/postgres-0"
    symptom: str
    root_cause: str
    evidence: list[Evidence]
    fix: Fix | None = None
    confidence: float  # 0.0-1.0


class HistoricalEvent(BaseModel):
    """A reconstructed event from temporal archaeology.

    Represents a point in the cluster's timeline reconstructed from
    metadata timestamps, events, and log entries.
    """

    timestamp: datetime
    event_type: str
    resource_type: str
    resource_name: str
    namespace: str | None = None
    description: str
    is_trigger: bool = False  # archaeology engine marks this


class PredictedFailure(BaseModel):
    """A forward-looking prediction of an impending failure.

    Based on trend analysis of resource usage, event patterns, and
    other signals that suggest a failure is approaching.
    """

    resource: str
    failure_type: str
    estimated_eta_seconds: int | None = None  # None = already failed
    confidence: float
    evidence: list[str]
    prevention: str


class UncertaintyGap(BaseModel):
    """An explicit acknowledgement of what the analysis does NOT know.

    Engineers need to know what the bundle cannot tell them, what additional
    data to collect, and how impactful the gap might be.
    """

    question: str
    reason: str
    to_investigate: str = ""
    collect_command: str = ""
    impact: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class SimulationResult(BaseModel):
    """Result of a what-if simulation for a proposed fix.

    Predicts whether a fix will resolve the issues, what new issues
    it might create, and what manual steps remain afterward.
    """

    fix_resolves: list[str]
    fix_creates: list[str]
    residual_issues: list[str]
    recovery_timeline: str
    manual_steps_after: list[str]
    confidence: float


class AnalystOutput(BaseModel):
    """Structured output from a single AI analyst.

    Every analyst (pod, node, config, etc.) returns this exact shape.
    Never free text -- always structured JSON.
    """

    analyst: str  # "pod" | "node" | "config"
    findings: list[Finding]
    root_cause: str | None = None
    confidence: float
    evidence: list[Evidence]
    remediation: list[Fix]
    uncertainty: list[str]
