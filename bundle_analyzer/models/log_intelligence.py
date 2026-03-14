"""Log intelligence models for pre-digested log analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LogWindow(BaseModel):
    """A focused window of log lines around an interesting region.

    Instead of dumping all logs, surfaces only the lines around error spikes,
    state transitions, or first-error-after-silence events.
    """

    start_line: int
    end_line: int
    lines: list[str]
    trigger: str  # "error_spike", "state_transition", "first_error_after_silence"
    severity: Literal["critical", "warning", "info"] = "warning"
    timestamp_range: tuple[datetime | None, datetime | None] = (None, None)


class PatternFrequency(BaseModel):
    """Frequency and rate analysis for a specific log pattern.

    Counts how often a pattern appears, computes rate per minute,
    and flags spikes when the rate exceeds the baseline.
    """

    pattern: str
    sample_line: str
    count: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    rate_per_minute: float = 0.0
    is_spike: bool = False


class StackTraceGroup(BaseModel):
    """A deduplicated group of identical stack traces.

    Groups traces by language, exception type, and top frame hash.
    Shows count instead of repeating the same trace 50 times.
    """

    language: Literal["java", "python", "go", "dotnet", "generic"]
    exception_type: str
    exception_message: str
    frames: list[str]
    count: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    sample_full_trace: str


class TimelineEntry(BaseModel):
    """A single entry in a container's error timeline."""

    timestamp: datetime
    level: str
    message: str


class ContainerTimeline(BaseModel):
    """Timeline entries from a single container for cross-container correlation."""

    container_name: str
    is_sidecar: bool = False
    entries: list[TimelineEntry] = Field(default_factory=list)


class CrossContainerCorrelation(BaseModel):
    """A detected correlation between events in different containers.

    Catches patterns like sidecar proxy dying before the main app,
    or shared dependency failures across containers.
    """

    source_container: str
    target_container: str
    source_event: str
    target_event: str
    time_delta_seconds: float
    correlation_type: str  # "sidecar_failure_precedes_main", "shared_dependency_failure"


class ErrorRateBucket(BaseModel):
    """Error count for a time bucket (for rate timeline visualization)."""

    timestamp: datetime
    bucket_seconds: int = 60
    error_count: int
    warn_count: int
    total_count: int


class LogIntelligence(BaseModel):
    """Pre-digested log intelligence for a single container.

    Produced by LogIntelligenceEngine. Consumed by LogAnalyst,
    PodAnalyst, and the UI instead of raw log lines. Saves AI tokens
    by surfacing only the signals that matter.
    """

    namespace: str
    pod_name: str
    container_name: str
    is_sidecar: bool = False
    total_lines_scanned: int = 0
    time_span: tuple[datetime | None, datetime | None] = (None, None)

    top_patterns: list[PatternFrequency] = Field(default_factory=list)
    error_rate_timeline: list[ErrorRateBucket] = Field(default_factory=list)
    stack_traces: list[StackTraceGroup] = Field(default_factory=list)
    interesting_windows: list[LogWindow] = Field(default_factory=list)
    level_counts: dict[str, int] = Field(default_factory=dict)

    has_oom_indicators: bool = False
    has_connection_errors: bool = False
    has_permission_errors: bool = False
    has_dns_failures: bool = False
    has_cert_errors: bool = False
    has_rate_limiting: bool = False
    dominant_error: str = ""


class PodLogIntelligence(BaseModel):
    """Aggregated log intelligence for all containers in a pod.

    Includes per-container intelligence plus cross-container correlations
    that surface sidecar failures, shared dependency issues, etc.
    """

    namespace: str
    pod_name: str
    containers: list[LogIntelligence] = Field(default_factory=list)
    cross_container_correlations: list[CrossContainerCorrelation] = Field(default_factory=list)
    unified_timeline: list[ContainerTimeline] = Field(default_factory=list)


class CrashLoopContext(BaseModel):
    """Context from previous container logs for crash analysis."""

    namespace: str
    pod_name: str
    container_name: str
    exit_code: int | None = None
    termination_reason: str = ""
    last_log_lines: list[str] = Field(default_factory=list)
    previous_log_lines: list[str] = Field(default_factory=list)
    crash_pattern: str = ""  # "oom", "segfault", "panic", "config_error", "dependency_timeout", "unknown"
    restart_count: int = 0
    message: str = ""
    severity: Literal["critical", "warning", "info"] = "critical"
