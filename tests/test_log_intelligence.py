"""Tests for the log intelligence engine — smart log pre-processing."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from bundle_analyzer.triage.log_intelligence import (
    LogIntelligenceEngine,
    _parse_timestamp,
    _detect_ts_format,
    _extract_level,
    _detect_stack_traces,
    _find_interesting_windows,
    _correlate_containers,
)
from bundle_analyzer.models import (
    LogIntelligence,
    PodLogIntelligence,
    PatternFrequency,
    StackTraceGroup,
    LogWindow,
    CrossContainerCorrelation,
    ErrorRateBucket,
    ContainerTimeline,
    TimelineEntry,
)


# ── Timestamp parsing tests ──────────────────────────────────────────


class TestTimestampParsing:
    """Test timestamp extraction from various log formats."""

    def test_iso8601_utc(self) -> None:
        ts = _parse_timestamp('2024-01-15T14:03:17.123Z some message')
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.hour == 14

    def test_iso8601_offset(self) -> None:
        ts = _parse_timestamp('2024-01-15T14:03:17+05:30 message')
        assert ts is not None
        assert ts.year == 2024

    def test_python_java_format(self) -> None:
        ts = _parse_timestamp('2024-01-15 14:03:17,123 ERROR something')
        assert ts is not None
        assert ts.minute == 3

    def test_go_format(self) -> None:
        ts = _parse_timestamp('2024/01/15 14:03:17 msg')
        assert ts is not None
        assert ts.day == 15

    def test_klog_format(self) -> None:
        ts = _parse_timestamp('E0115 14:03:17.123456 main.go:42] error here')
        assert ts is not None
        assert ts.month == 1
        assert ts.day == 15

    def test_epoch_seconds(self) -> None:
        ts = _parse_timestamp('1705326197 message')
        assert ts is not None
        assert ts.year == 2024

    def test_epoch_millis(self) -> None:
        ts = _parse_timestamp('1705326197123 message')
        assert ts is not None
        assert ts.year == 2024

    def test_no_timestamp(self) -> None:
        ts = _parse_timestamp('just a regular log line with no time')
        assert ts is None

    def test_detected_format_fast_path(self) -> None:
        ts = _parse_timestamp('2024-01-15T10:00:00Z msg', detected_format='iso8601')
        assert ts is not None

    def test_detect_format(self) -> None:
        lines = ['2024-01-15T14:00:00Z line1', '2024-01-15T14:01:00Z line2']
        fmt = _detect_ts_format(lines)
        assert fmt == 'iso8601'


# ── Log level extraction tests ───────────────────────────────────────


class TestLogLevelExtraction:
    """Test log level parsing from various formats."""

    def test_json_level(self) -> None:
        assert _extract_level('{"level":"error","msg":"fail"}') == "ERROR"

    def test_json_severity(self) -> None:
        assert _extract_level('{"severity":"WARNING","message":"hmm"}') == "WARN"

    def test_klog_error(self) -> None:
        assert _extract_level('E0115 14:03:17.123 main.go:42] err') == "ERROR"

    def test_klog_warning(self) -> None:
        assert _extract_level('W0115 14:03:17.123 main.go:42] warn') == "WARN"

    def test_klog_info(self) -> None:
        assert _extract_level('I0115 14:03:17.123 main.go:42] info') == "INFO"

    def test_bracket_error(self) -> None:
        assert _extract_level('[ERROR] something went wrong') == "ERROR"

    def test_colon_format(self) -> None:
        assert _extract_level('ERROR: connection failed') == "ERROR"

    def test_kv_format(self) -> None:
        assert _extract_level('ts=123 level=warn msg=something') == "WARN"

    def test_unknown_level(self) -> None:
        assert _extract_level('just some text') == "UNKNOWN"

    def test_fatal(self) -> None:
        assert _extract_level('FATAL: process exiting') == "FATAL"

    def test_critical_normalizes_to_fatal(self) -> None:
        assert _extract_level('[CRITICAL] memory exhausted') == "FATAL"


# ── Stack trace detection tests ──────────────────────────────────────


class TestStackTraceDetection:
    """Test stack trace detection and grouping."""

    def test_java_exception(self) -> None:
        lines = [
            "Exception in thread main: java.lang.NullPointerException: null ref",
            "    at com.app.Service.handle(Service.java:42)",
            "    at com.app.Main.run(Main.java:10)",
            "normal log line after",
        ]
        timestamps = [None] * len(lines)
        groups = _detect_stack_traces(lines, timestamps)
        assert len(groups) == 1
        assert groups[0].language == "java"
        assert "NullPointerException" in groups[0].exception_type
        assert groups[0].count == 1

    def test_python_traceback(self) -> None:
        lines = [
            "Traceback (most recent call last):",
            '  File "app.py", line 42, in handle',
            '  File "db.py", line 10, in query',
            "ValueError: invalid literal",
            "normal log after",
        ]
        timestamps = [None] * len(lines)
        groups = _detect_stack_traces(lines, timestamps)
        assert len(groups) == 1
        assert groups[0].language == "python"
        assert "ValueError" in groups[0].exception_type

    def test_go_panic(self) -> None:
        lines = [
            "panic: runtime error: index out of range",
            "    goroutine 1 [running]:",
            "    main.go:42 +0x1a",
            "",
            "normal after",
        ]
        timestamps = [None] * len(lines)
        groups = _detect_stack_traces(lines, timestamps)
        assert len(groups) >= 1
        assert groups[0].language == "go"
        assert "panic" in groups[0].exception_type

    def test_duplicate_traces_grouped(self) -> None:
        trace = [
            "Exception in thread main: java.lang.NullPointerException: msg",
            "    at com.app.Service.handle(Service.java:42)",
        ]
        # Same trace repeated 3 times with normal lines between
        lines: list[str] = []
        for _ in range(3):
            lines.extend(trace)
            lines.append("INFO normal log line")
        timestamps = [None] * len(lines)
        groups = _detect_stack_traces(lines, timestamps)
        assert len(groups) == 1
        assert groups[0].count == 3


# ── Pattern matching tests ───────────────────────────────────────────


class TestPatternMatching:
    """Test the expanded K8s failure pattern library."""

    def test_connection_refused_detected(self) -> None:
        intel = _build_intel_from_lines([
            "INFO starting app",
            "ERROR connection refused to postgres:5432",
            "ERROR connection refused to postgres:5432",
        ])
        assert intel.has_connection_errors
        assert any("Connection refused" in p.pattern for p in intel.top_patterns)

    def test_oom_detected(self) -> None:
        intel = _build_intel_from_lines([
            "java.lang.OutOfMemoryError: Java heap space",
        ])
        assert intel.has_oom_indicators

    def test_dns_failure_detected(self) -> None:
        intel = _build_intel_from_lines([
            "ERROR: dns lookup failed for service-a.default.svc: no such host",
        ])
        assert intel.has_dns_failures

    def test_cert_error_detected(self) -> None:
        intel = _build_intel_from_lines([
            "x509: certificate has expired",
        ])
        assert intel.has_cert_errors

    def test_rate_limiting_detected(self) -> None:
        intel = _build_intel_from_lines([
            "429 Too Many Requests from API gateway",
        ])
        assert intel.has_rate_limiting

    def test_permission_error_detected(self) -> None:
        intel = _build_intel_from_lines([
            "ERROR 403 Forbidden: cannot list pods in namespace kube-system",
        ])
        assert intel.has_permission_errors


# ── Window finding tests ─────────────────────────────────────────────


class TestWindowFinding:
    """Test interesting region detection."""

    def test_state_transition_detected(self) -> None:
        lines = ["normal"] * 10 + ["server shutting down"] + ["normal"] * 10
        levels = ["INFO"] * len(lines)
        timestamps = [None] * len(lines)
        windows = _find_interesting_windows(lines, levels, timestamps)
        assert any(w.trigger == "state_transition" for w in windows)

    def test_error_spike_detected(self) -> None:
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        lines: list[str] = []
        levels: list[str] = []
        timestamps: list[datetime | None] = []

        # Baseline: 1 error per minute for 5 minutes (low rate)
        for i in range(5):
            lines.append(f"ERROR baseline error {i}")
            levels.append("ERROR")
            timestamps.append(base + timedelta(minutes=i))
            # Plus some normal lines
            for j in range(3):
                lines.append(f"INFO normal {i}-{j}")
                levels.append("INFO")
                timestamps.append(base + timedelta(minutes=i, seconds=15 * (j + 1)))

        # Spike: 20 errors in 1 minute (way above baseline)
        spike_time = base + timedelta(minutes=10)
        for i in range(20):
            lines.append(f"ERROR crash crash crash {i}")
            levels.append("ERROR")
            timestamps.append(spike_time + timedelta(seconds=i * 3))

        windows = _find_interesting_windows(lines, levels, timestamps)
        assert any(w.trigger == "error_spike" for w in windows)

    def test_first_error_after_silence(self) -> None:
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        lines = []
        levels = []
        timestamps: list[datetime | None] = []

        # Error, then 2 min of silence, then error
        lines.append("ERROR first error")
        levels.append("ERROR")
        timestamps.append(base)

        for i in range(5):
            lines.append(f"INFO normal {i}")
            levels.append("INFO")
            timestamps.append(base + timedelta(seconds=30 + i * 10))

        lines.append("ERROR second error after silence")
        levels.append("ERROR")
        timestamps.append(base + timedelta(minutes=2))

        windows = _find_interesting_windows(lines, levels, timestamps)
        assert any(w.trigger == "first_error_after_silence" for w in windows)


# ── Cross-container correlation tests ────────────────────────────────


class TestCrossContainerCorrelation:
    """Test detection of correlations between containers."""

    def test_sidecar_precedes_main(self) -> None:
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        sidecar = LogIntelligence(
            namespace="default",
            pod_name="app-1",
            container_name="istio-proxy",
            is_sidecar=True,
            total_lines_scanned=100,
            top_patterns=[
                PatternFrequency(
                    pattern="Connection reset",
                    sample_line="connection reset by peer",
                    count=5,
                    first_seen=base,
                    last_seen=base + timedelta(seconds=10),
                ),
            ],
        )
        main = LogIntelligence(
            namespace="default",
            pod_name="app-1",
            container_name="app",
            is_sidecar=False,
            total_lines_scanned=200,
            top_patterns=[
                PatternFrequency(
                    pattern="Connection refused",
                    sample_line="connection refused to upstream",
                    count=10,
                    first_seen=base + timedelta(seconds=5),
                    last_seen=base + timedelta(seconds=30),
                ),
            ],
        )

        correlations = _correlate_containers([main, sidecar])
        assert any(c.correlation_type == "sidecar_failure_precedes_main" for c in correlations)

    def test_shared_dependency_failure(self) -> None:
        base = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        c1 = LogIntelligence(
            namespace="default", pod_name="app-1", container_name="web",
            total_lines_scanned=100,
            top_patterns=[PatternFrequency(pattern="DNS lookup failed", sample_line="", count=3, first_seen=base)],
        )
        c2 = LogIntelligence(
            namespace="default", pod_name="app-1", container_name="worker",
            total_lines_scanned=100,
            top_patterns=[PatternFrequency(pattern="DNS lookup failed", sample_line="", count=5, first_seen=base)],
        )
        correlations = _correlate_containers([c1, c2])
        assert any(c.correlation_type == "shared_dependency_failure" for c in correlations)


# ── Model serialization tests ────────────────────────────────────────


class TestModelSerialization:
    """Test that all new models serialize correctly."""

    def test_log_intelligence_roundtrip(self) -> None:
        intel = LogIntelligence(
            namespace="default",
            pod_name="test-pod",
            container_name="app",
            total_lines_scanned=1000,
            level_counts={"ERROR": 42, "WARN": 15, "INFO": 943},
            has_oom_indicators=True,
            dominant_error="Out of memory",
        )
        data = intel.model_dump()
        restored = LogIntelligence.model_validate(data)
        assert restored.total_lines_scanned == 1000
        assert restored.has_oom_indicators is True

    def test_pod_log_intelligence_roundtrip(self) -> None:
        pod_intel = PodLogIntelligence(
            namespace="default",
            pod_name="test-pod",
            containers=[
                LogIntelligence(
                    namespace="default", pod_name="test-pod",
                    container_name="app", total_lines_scanned=500,
                ),
            ],
        )
        data = pod_intel.model_dump()
        restored = PodLogIntelligence.model_validate(data)
        assert len(restored.containers) == 1

    def test_stack_trace_group_serialization(self) -> None:
        grp = StackTraceGroup(
            language="java",
            exception_type="NullPointerException",
            exception_message="null ref",
            frames=["at com.app.Main.run(Main.java:10)"],
            count=23,
            sample_full_trace="Exception in thread main...",
        )
        data = grp.model_dump()
        assert data["count"] == 23
        assert data["language"] == "java"


# ── Helper ───────────────────────────────────────────────────────────


def _build_intel_from_lines(lines: list[str]) -> LogIntelligence:
    """Quick helper to run pattern matching on a list of lines."""
    from bundle_analyzer.triage.log_intelligence import _FAILURE_PATTERNS
    from collections import Counter

    pattern_counts: Counter[str] = Counter()
    has_oom = has_conn = has_perm = has_dns = has_cert = has_rl = False

    for line in lines:
        for category, label, regex, sev in _FAILURE_PATTERNS:
            if regex.search(line):
                pattern_counts[label] += 1
                if category == "oom":
                    has_oom = True
                elif category == "connection":
                    has_conn = True
                elif category == "auth":
                    has_perm = True
                elif category == "dns":
                    has_dns = True
                elif category == "tls":
                    has_cert = True
                elif category == "ratelimit":
                    has_rl = True

    patterns = [
        PatternFrequency(pattern=label, sample_line="", count=count)
        for label, count in pattern_counts.most_common()
    ]

    return LogIntelligence(
        namespace="test", pod_name="test", container_name="test",
        total_lines_scanned=len(lines),
        top_patterns=patterns,
        has_oom_indicators=has_oom,
        has_connection_errors=has_conn,
        has_permission_errors=has_perm,
        has_dns_failures=has_dns,
        has_cert_errors=has_cert,
        has_rate_limiting=has_rl,
    )
