"""Top-level analysis result model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .ai_output import Finding, HistoricalEvent, PredictedFailure, UncertaintyGap
from .bundle import BundleMetadata
from .causal import CausalChain, LogDiagnosis
from .evaluation import EvaluationResult
from .troubleshoot import PreflightReport, TriageResult


class AnalysisResult(BaseModel):
    """Top-level result combining triage and AI analysis.

    This is the final output structure that the TUI and CLI both consume.
    It aggregates everything: triage findings, AI findings, timeline,
    predictions, uncertainty gaps, and cluster metadata.
    """

    bundle_metadata: BundleMetadata
    triage: TriageResult
    findings: list[Finding]
    causal_chains: list[CausalChain] = Field(default_factory=list)
    root_cause: str | None = None
    confidence: float
    timeline: list[HistoricalEvent]
    predictions: list[PredictedFailure]
    uncertainty: list[UncertaintyGap]
    log_diagnoses: list[LogDiagnosis] = Field(default_factory=list)
    cluster_summary: str  # short paragraph for AI context
    preflight_report: PreflightReport | None = None
    analysis_duration_seconds: float
    sanitization_summary: str = ""  # e.g. "Redacted 47 patterns (23 credentials, 12 PII)"
    summary: str | None = None  # Human-readable summary of the analysis for homepage display
    evaluation: EvaluationResult | None = None
    hypotheses: list[dict] = Field(default_factory=list)  # ranked RCA hypotheses
    analysis_quality: Literal["high", "medium", "degraded"] = "medium"
