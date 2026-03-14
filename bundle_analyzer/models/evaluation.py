"""Independent evaluation ("second opinion") models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DependencyLink(BaseModel):
    """One link in a dependency trace chain.

    Each link shows: what was observed, where the evidence came from,
    what it connects to (the next link), and why it matters.
    """

    step_number: int
    resource: str  # e.g. "Pod/default/break-bad-probe-84fd687d57-5fc6f"
    observation: str  # what was found
    evidence_source: str  # file or data source in the bundle
    evidence_excerpt: str  # actual data snippet proving the observation
    leads_to: str  # what this observation implies / connects to next
    significance: Literal["root_cause", "contributing", "symptom", "context"] = "context"


class CorrelatedSignal(BaseModel):
    """A triage signal cross-referenced during evaluation.

    Shows signals the evaluator found across different scanner types
    that relate to a single failure point.
    """

    scanner_type: str  # "probe", "resource", "silence", "event", "config", "drift", etc.
    signal: str  # what was detected
    relates_to: str  # how it connects to the failure point
    severity: Literal["critical", "warning", "info"] = "info"


class EvaluationVerdict(BaseModel):
    """Per-failure-point verdict from the independent evaluator.

    Contains a full dependency trace showing HOW the evaluator arrived
    at its conclusion, cross-referenced signals from all triage scanners,
    and detailed assessment of the pipeline's analysis.
    """

    failure_point: str
    resource: str  # K8s resource key e.g. "Pod/default/my-pod"
    app_claimed_cause: str  # what the pipeline said
    true_likely_cause: str  # evaluator's independent assessment
    correctness: Literal["Correct", "Partially Correct", "Incorrect", "Inconclusive"]

    # The full dependency trace -- step by step from symptom to root cause
    dependency_chain: list[DependencyLink] = Field(default_factory=list)

    # Cross-referenced signals from all triage scanner types
    correlated_signals: list[CorrelatedSignal] = Field(default_factory=list)

    # Evidence assessment
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)

    # What the pipeline got wrong or missed
    missed: list[str] = Field(default_factory=list)
    misinterpreted: list[str] = Field(default_factory=list)

    # Alternatives
    stronger_alternative: str | None = None
    alternative_hypotheses: list[str] = Field(default_factory=list)

    # Impact assessment
    blast_radius: list[str] = Field(default_factory=list)  # other affected resources
    remediation_assessment: str = ""  # is the suggested fix correct/complete?

    confidence_score: float = 0.0  # 0.0-1.0
    notes: str = ""


class MissedFailurePoint(BaseModel):
    """A failure point the evaluator found that the pipeline missed entirely."""

    failure_point: str
    resource: str
    evidence_summary: str
    severity: Literal["critical", "warning", "info"]
    dependency_chain: list[DependencyLink] = Field(default_factory=list)
    correlated_signals: list[CorrelatedSignal] = Field(default_factory=list)
    recommended_action: str = ""


class EvaluationResult(BaseModel):
    """Overall evaluation from the independent second-opinion engine.

    Aggregates per-failure verdicts with full dependency traces,
    cross-referenced signals, and detailed assessment of analysis quality.
    """

    verdicts: list[EvaluationVerdict] = Field(default_factory=list)
    overall_correctness: Literal["Correct", "Partially Correct", "Incorrect", "Inconclusive"] = "Inconclusive"
    overall_confidence: float = 0.0
    missed_failure_points: list[MissedFailurePoint] = Field(default_factory=list)
    cross_cutting_concerns: list[str] = Field(default_factory=list)  # issues spanning multiple findings
    evaluation_summary: str = ""
    evaluation_duration_seconds: float = 0.0
