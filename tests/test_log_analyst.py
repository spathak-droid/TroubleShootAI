"""Tests for the AI log analyst — prompt building, model validation, and constants."""

from __future__ import annotations

from bundle_analyzer.ai.prompts.log_analysis import (
    LOG_ANALYSIS_SYSTEM_PROMPT,
    build_log_analysis_prompt,
)
from bundle_analyzer.models import LogDiagnosis

# ---------------------------------------------------------------------------
# System prompt constant tests
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Verify the system prompt contains all required instructions."""

    def test_system_prompt_exists_and_nonempty(self) -> None:
        """System prompt must be a non-empty string."""
        assert isinstance(LOG_ANALYSIS_SYSTEM_PROMPT, str)
        assert len(LOG_ANALYSIS_SYSTEM_PROMPT) > 100

    def test_system_prompt_requires_json(self) -> None:
        """System prompt must instruct the model to respond with JSON only."""
        assert "You must respond with valid JSON only" in LOG_ANALYSIS_SYSTEM_PROMPT

    def test_system_prompt_mentions_hidden_markers(self) -> None:
        """System prompt must explain ***HIDDEN*** redaction markers."""
        assert "***HIDDEN***" in LOG_ANALYSIS_SYSTEM_PROMPT

    def test_system_prompt_mentions_previous_logs(self) -> None:
        """System prompt must instruct the model to read previous logs."""
        assert "PREVIOUS" in LOG_ANALYSIS_SYSTEM_PROMPT or "previous" in LOG_ANALYSIS_SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_root_cause_categories(self) -> None:
        """System prompt should list the root cause categories."""
        for category in ("oom", "config_error", "dependency_failure", "permission_error"):
            assert category in LOG_ANALYSIS_SYSTEM_PROMPT

    def test_system_prompt_requires_diagnosis_fields(self) -> None:
        """System prompt should describe the required JSON fields."""
        for field in ("diagnosis", "root_cause_category", "key_log_line", "confidence"):
            assert field in LOG_ANALYSIS_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------


class TestBuildLogAnalysisPrompt:
    """Verify the prompt builder assembles all crash context into a prompt."""

    def test_basic_prompt_structure(self) -> None:
        """Prompt includes pod name, namespace, container, and crash pattern."""
        prompt = build_log_analysis_prompt(
            pod_name="api-server-7f8d9c",
            namespace="production",
            container_name="api",
            crash_pattern="panic",
            exit_code=1,
            termination_reason="Error",
            restart_count=5,
            current_logs=["INFO Starting server", "FATAL panic: nil pointer"],
            previous_logs=["INFO Connected to DB", "ERROR lost connection"],
        )

        assert "production/api-server-7f8d9c" in prompt
        assert "Container: api" in prompt
        assert "Restart count: 5" in prompt
        assert "panic" in prompt
        assert "Exit code: 1" in prompt
        assert "Error" in prompt

    def test_prompt_includes_current_logs(self) -> None:
        """Current log lines appear in the prompt."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=3,
            current_logs=["GET /health 200", "connection reset by peer"],
            previous_logs=[],
        )

        assert "GET /health 200" in prompt
        assert "connection reset by peer" in prompt

    def test_prompt_includes_previous_logs(self) -> None:
        """Previous (pre-crash) log lines appear in the prompt."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=3,
            current_logs=[],
            previous_logs=["FATAL out of memory", "killed"],
        )

        assert "FATAL out of memory" in prompt
        assert "Previous Container Logs" in prompt

    def test_prompt_with_empty_logs(self) -> None:
        """Prompt handles empty logs gracefully."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=0,
            current_logs=[],
            previous_logs=[],
        )

        assert "no current logs available" in prompt
        assert "no previous logs available" in prompt

    def test_prompt_includes_related_events(self) -> None:
        """Related events appear in the prompt when provided."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="oom",
            exit_code=137,
            termination_reason="OOMKilled",
            restart_count=10,
            current_logs=["starting..."],
            previous_logs=["killed"],
            related_events="[2024-01-01T00:00:00Z] OOMKilling (x3): Memory limit exceeded",
        )

        assert "OOMKilling" in prompt
        assert "Memory limit exceeded" in prompt

    def test_prompt_without_related_events(self) -> None:
        """Prompt handles missing events gracefully."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=0,
            current_logs=[],
            previous_logs=[],
            related_events=None,
        )

        assert "no warning events found" in prompt

    def test_prompt_omits_none_exit_code(self) -> None:
        """Exit code line is omitted when exit_code is None."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=0,
            current_logs=[],
            previous_logs=[],
        )

        assert "Exit code:" not in prompt

    def test_prompt_omits_empty_termination_reason(self) -> None:
        """Termination reason line is omitted when empty."""
        prompt = build_log_analysis_prompt(
            pod_name="web",
            namespace="default",
            container_name="nginx",
            crash_pattern="unknown",
            exit_code=None,
            termination_reason="",
            restart_count=0,
            current_logs=[],
            previous_logs=[],
        )

        assert "Termination reason:" not in prompt


# ---------------------------------------------------------------------------
# LogDiagnosis model tests
# ---------------------------------------------------------------------------


class TestLogDiagnosisModel:
    """Verify the LogDiagnosis Pydantic model validates correctly."""

    def test_minimal_valid_model(self) -> None:
        """Model with only required fields validates."""
        diag = LogDiagnosis(
            namespace="default",
            pod_name="api-server",
            container_name="api",
            diagnosis="The container ran out of memory.",
            root_cause_category="oom",
        )

        assert diag.namespace == "default"
        assert diag.pod_name == "api-server"
        assert diag.container_name == "api"
        assert diag.diagnosis == "The container ran out of memory."
        assert diag.root_cause_category == "oom"
        assert diag.confidence == 0.0
        assert diag.fix_commands == []
        assert diag.additional_context_needed == []

    def test_full_model(self) -> None:
        """Model with all fields validates."""
        diag = LogDiagnosis(
            namespace="production",
            pod_name="web-abc123",
            container_name="web",
            diagnosis="Database connection timeout causing crash loop",
            root_cause_category="dependency_failure",
            key_log_line="FATAL: could not connect to server: connection timed out",
            why="The PostgreSQL service is unreachable due to network policy",
            fix_description="Update network policy to allow egress to PostgreSQL",
            fix_commands=[
                "kubectl apply -f network-policy-fix.yaml",
                "kubectl rollout restart deployment/web",
            ],
            confidence=0.9,
            additional_context_needed=["Network policy YAML", "PostgreSQL pod status"],
        )

        assert diag.confidence == 0.9
        assert len(diag.fix_commands) == 2
        assert len(diag.additional_context_needed) == 2

    def test_model_serialization_roundtrip(self) -> None:
        """Model can be serialized to dict and back."""
        diag = LogDiagnosis(
            namespace="kube-system",
            pod_name="coredns-5d4fc",
            container_name="coredns",
            diagnosis="Config file parse error",
            root_cause_category="config_error",
            key_log_line="plugin/forward: not an IP address: 'invalid-dns'",
            confidence=0.6,
        )

        data = diag.model_dump()
        restored = LogDiagnosis(**data)

        assert restored.namespace == diag.namespace
        assert restored.pod_name == diag.pod_name
        assert restored.diagnosis == diag.diagnosis
        assert restored.confidence == diag.confidence

    def test_default_empty_lists(self) -> None:
        """Default list fields are empty, not None."""
        diag = LogDiagnosis(
            namespace="default",
            pod_name="test",
            container_name="main",
            diagnosis="test",
            root_cause_category="unknown",
        )

        assert isinstance(diag.fix_commands, list)
        assert isinstance(diag.additional_context_needed, list)
        assert len(diag.fix_commands) == 0
        assert len(diag.additional_context_needed) == 0
