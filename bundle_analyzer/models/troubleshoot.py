"""Troubleshoot.sh analyzer models and the TriageResult aggregator."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .log_intelligence import CrashLoopContext, PodLogIntelligence
from .triage import (
    ConfigIssue,
    DeploymentIssue,
    DriftIssue,
    EventEscalation,
    IngressIssue,
    K8sEvent,
    NetworkPolicyIssue,
    NodeIssue,
    PodIssue,
    ProbeIssue,
    QuotaIssue,
    RBACIssue,
    ResourceIssue,
    SilenceSignal,
    StorageIssue,
)


class TroubleshootAnalyzerResult(BaseModel):
    """A single result from a troubleshoot.sh analyzer."""

    name: str
    check_name: str = ""
    is_pass: bool = False
    is_warn: bool = False
    is_fail: bool = False
    title: str = ""
    message: str = ""
    uri: str = ""
    analyzer_type: str = ""  # "clusterVersion", "nodeResources", etc.
    severity: Literal["pass", "warn", "fail"] = "pass"
    strict: bool = False


class TroubleshootAnalysis(BaseModel):
    """Complete parsed troubleshoot.sh analysis from a bundle."""

    results: list[TroubleshootAnalyzerResult] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    has_results: bool = False


class PreflightCheckResult(BaseModel):
    """A single preflight check result."""

    name: str
    check_name: str = ""
    is_pass: bool = False
    is_warn: bool = False
    is_fail: bool = False
    title: str = ""
    message: str = ""
    uri: str = ""
    analyzer_type: str = ""
    severity: Literal["pass", "warn", "fail"] = "pass"


class PreflightReport(BaseModel):
    """Complete preflight check report."""

    results: list[PreflightCheckResult] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    collected_at: datetime | None = None


class ExternalAnalyzerIssue(BaseModel):
    """Issue from troubleshoot.sh that we have no native scanner for."""

    source: str = "troubleshoot.sh"
    analyzer_type: str
    name: str
    title: str
    message: str
    severity: Literal["critical", "warning", "info"]
    uri: str = ""
    corroborates: str | None = None  # ID of existing issue this confirms
    contradicts: str | None = None  # ID of existing issue this contradicts


class CoverageGap(BaseModel):
    """An area of the bundle that no scanner examines."""

    area: str  # e.g. "CronJobs", "PodDisruptionBudgets", "HorizontalPodAutoscalers"
    data_present: bool  # True if the bundle actually contains this data
    data_path: str = ""  # where in the bundle this data lives
    why_it_matters: str = ""  # brief explanation of diagnostic value
    severity: Literal["high", "medium", "low"] = "medium"


class TriageResult(BaseModel):
    """Aggregated output from all triage scanners.

    Contains every issue found by deterministic pattern-matching scanners
    before any AI analysis is performed. This is the input to the AI pipeline.
    """

    critical_pods: list[PodIssue] = Field(default_factory=list)
    warning_pods: list[PodIssue] = Field(default_factory=list)
    node_issues: list[NodeIssue] = Field(default_factory=list)
    deployment_issues: list[DeploymentIssue] = Field(default_factory=list)
    config_issues: list[ConfigIssue] = Field(default_factory=list)
    drift_issues: list[DriftIssue] = Field(default_factory=list)
    silence_signals: list[SilenceSignal] = Field(default_factory=list)
    warning_events: list[K8sEvent] = Field(default_factory=list)
    existing_analysis: list[dict] = Field(default_factory=list)  # from bundle's own analyzer
    rbac_errors: list[str] = Field(default_factory=list)
    probe_issues: list[ProbeIssue] = Field(default_factory=list)
    resource_issues: list[ResourceIssue] = Field(default_factory=list)
    ingress_issues: list[IngressIssue] = Field(default_factory=list)
    storage_issues: list[StorageIssue] = Field(default_factory=list)
    rbac_issues: list[RBACIssue] = Field(default_factory=list)
    quota_issues: list[QuotaIssue] = Field(default_factory=list)
    network_policy_issues: list[NetworkPolicyIssue] = Field(default_factory=list)
    crash_contexts: list[CrashLoopContext] = Field(default_factory=list)
    event_escalations: list[EventEscalation] = Field(default_factory=list)
    troubleshoot_analysis: TroubleshootAnalysis = Field(default_factory=TroubleshootAnalysis)
    preflight_report: PreflightReport | None = None
    external_analyzer_issues: list[ExternalAnalyzerIssue] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
    pod_anomalies: list[Any] = Field(default_factory=list)  # list[PodAnomaly] from anomaly_detector
    dependency_map: Any | None = None  # DependencyMap from dependency_scanner
    change_report: Any | None = None  # ChangeReport from change_correlator
    log_intelligence: dict[str, Any] = Field(default_factory=dict)  # str -> PodLogIntelligence
