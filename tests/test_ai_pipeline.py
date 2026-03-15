"""Tests for the AI analysis pipeline.

All Anthropic API calls are mocked -- these tests verify orchestration logic,
retry behavior, response parsing, interview history, and context injection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bundle_analyzer.ai.context_injector import ContextInjector
from bundle_analyzer.ai.synthesis import SynthesisEngine
from bundle_analyzer.models import (
    AnalysisResult,
    AnalystOutput,
    BundleMetadata,
    Evidence,
    Finding,
    Fix,
    K8sEvent,
    PodIssue,
    TriageResult,
    UncertaintyGap,
)

SAMPLE_BUNDLE = Path(__file__).parent / "fixtures" / "sample_bundle"


# ── Helpers ───────────────────────────────────────────────────────────


def _make_triage() -> TriageResult:
    """Create a minimal TriageResult for testing."""
    return TriageResult(
        critical_pods=[
            PodIssue(
                namespace="default",
                pod_name="crash-pod",
                container_name="app",
                issue_type="CrashLoopBackOff",
                restart_count=15,
                exit_code=1,
                message="CrashLoopBackOff",
            ),
        ],
        warning_events=[
            K8sEvent(
                namespace="default",
                name="event1",
                reason="BackOff",
                message="Back-off restarting",
                type="Warning",
                involved_object_kind="Pod",
                involved_object_name="crash-pod",
                last_timestamp=datetime(2024, 1, 15, 10, 5, tzinfo=UTC),
                count=5,
            ),
        ],
    )


def _make_analyst_output(analyst: str = "pod") -> AnalystOutput:
    """Create a minimal AnalystOutput for testing."""
    return AnalystOutput(
        analyst=analyst,
        findings=[
            Finding(
                id="pod-abc123",
                severity="critical",
                type="pod-failure",
                resource="pod/default/crash-pod",
                symptom="CrashLoopBackOff",
                root_cause="Application exits with code 1 on startup",
                evidence=[Evidence(file="pod/default/crash-pod", excerpt="exit code 1")],
                confidence=0.85,
                fix=Fix(description="Fix application startup error"),
            ),
        ],
        root_cause="Application exits with code 1 on startup",
        confidence=0.85,
        evidence=[Evidence(file="pod/default/crash-pod", excerpt="exit code 1")],
        remediation=[Fix(description="Fix startup")],
        uncertainty=["Cannot determine if external dependency is down"],
    )


def _make_analysis_result() -> AnalysisResult:
    """Create a minimal AnalysisResult for testing."""
    return AnalysisResult(
        bundle_metadata=BundleMetadata(bundle_path=Path(".")),
        triage=_make_triage(),
        findings=[],
        root_cause=None,
        confidence=0.0,
        timeline=[],
        predictions=[],
        uncertainty=[
            UncertaintyGap(
                question="AI analysis was not performed",
                reason="No API key",
                impact="HIGH",
            )
        ],
        cluster_summary="Test cluster",
        analysis_duration_seconds=1.0,
    )


def _mock_anthropic_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response."""
    content_block = SimpleNamespace(text=text)
    usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    return SimpleNamespace(content=[content_block], usage=usage)


# ══════════════════════════════════════════════════════════════════════
# BundleAnalyzerClient retry tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_client_retry_on_rate_limit() -> None:
    """BundleAnalyzerClient.complete should retry on rate limit errors."""
    from bundle_analyzer.ai.client import BundleAnalyzerClient

    client = BundleAnalyzerClient(api_key="test-key", max_retries=3)

    call_count = 0

    class RateLimitError(Exception):
        """Mock rate limit error."""

    async def mock_call(system, user, max_tokens, temperature):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RateLimitError("429 rate limited")
        return "success"

    client._call_async = mock_call

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.complete(system="test", user="test")

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_client_exhausts_retries() -> None:
    """BundleAnalyzerClient.complete should raise after max retries."""
    from bundle_analyzer.ai.client import BundleAnalyzerClient

    client = BundleAnalyzerClient(api_key="test-key", max_retries=2)

    class RateLimitError(Exception):
        """Mock rate limit error."""

    async def mock_call(system, user, max_tokens, temperature):
        raise RateLimitError("429 rate limited")

    client._call_async = mock_call

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RateLimitError):
            await client.complete(system="test", user="test")


@pytest.mark.asyncio
async def test_client_tracks_tokens() -> None:
    """BundleAnalyzerClient should accumulate token usage."""
    from bundle_analyzer.ai.client import BundleAnalyzerClient

    client = BundleAnalyzerClient(api_key="test-key", max_retries=1)

    async def mock_call(system, user, max_tokens, temperature):
        client.total_input_tokens += 100
        client.total_output_tokens += 50
        return "hello"

    client._call_async = mock_call

    await client.complete(system="s", user="u")
    assert client.total_input_tokens == 100
    assert client.total_output_tokens == 50

    await client.complete(system="s", user="u")
    assert client.total_input_tokens == 200
    assert client.total_output_tokens == 100


# ══════════════════════════════════════════════════════════════════════
# PodAnalyst parse tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pod_analyst_parses_valid_response() -> None:
    """PodAnalyst._parse_response should produce a valid AnalystOutput from JSON."""
    from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst

    analyst = PodAnalyst()
    raw_json = json.dumps({
        "immediate_cause": "Application crashes on startup",
        "root_cause": "Missing database connection string",
        "confidence": "high",
        "evidence": ["exit code 1 in container status", "no DB_URL env var"],
        "fix": "Add DB_URL environment variable to deployment",
        "what_i_cant_tell": ["Whether the database is actually reachable"],
    })

    result = analyst._parse_response(raw_json, "default", "test-pod")
    assert isinstance(result, AnalystOutput)
    assert result.analyst == "pod"
    assert len(result.findings) == 1
    assert result.findings[0].root_cause == "Missing database connection string"
    assert result.confidence == 0.9  # "high" maps to 0.9
    assert len(result.uncertainty) == 1


@pytest.mark.asyncio
async def test_pod_analyst_parses_markdown_fenced_json() -> None:
    """PodAnalyst._parse_response should handle JSON wrapped in markdown fences."""
    from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst

    analyst = PodAnalyst()
    raw = '```json\n{"immediate_cause":"crash","root_cause":"OOM","confidence":"medium","evidence":["exit 137"],"fix":"Increase memory","what_i_cant_tell":[]}\n```'

    result = analyst._parse_response(raw, "default", "test-pod")
    assert isinstance(result, AnalystOutput)
    assert result.findings[0].root_cause == "OOM"


@pytest.mark.asyncio
async def test_pod_analyst_handles_malformed_response() -> None:
    """PodAnalyst._parse_response should raise on invalid JSON."""
    from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst

    analyst = PodAnalyst()
    with pytest.raises(json.JSONDecodeError):
        analyst._parse_response("this is not json at all", "default", "test-pod")


@pytest.mark.asyncio
async def test_pod_analyst_fallback_output() -> None:
    """PodAnalyst._fallback_output should return a low-confidence output."""
    from bundle_analyzer.ai.analysts.pod_analyst import PodAnalyst

    result = PodAnalyst._fallback_output("default", "test-pod", "parse failed")
    assert isinstance(result, AnalystOutput)
    assert result.confidence == 0.1
    assert len(result.findings) == 1
    assert "parse failed" in result.findings[0].root_cause


# ══════════════════════════════════════════════════════════════════════
# AnalysisOrchestrator tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orchestrator_triage_only_without_api_key() -> None:
    """AnalysisOrchestrator should return triage-only results without API key."""
    from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator
    from bundle_analyzer.bundle.indexer import BundleIndex

    index = await BundleIndex.build(SAMPLE_BUNDLE)
    triage = _make_triage()
    injector = ContextInjector()

    orchestrator = AnalysisOrchestrator()

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        # Remove the key if present
        import os
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = await orchestrator.run(triage, index, injector)
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key

    assert isinstance(result, AnalysisResult)
    assert len(result.findings) == 0
    assert result.confidence == 0.0
    assert len(result.uncertainty) >= 1


@pytest.mark.asyncio
async def test_orchestrator_runs_all_stages() -> None:
    """AnalysisOrchestrator should call archaeology, analysts, prediction, and synthesis."""
    from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator
    from bundle_analyzer.bundle.indexer import BundleIndex

    index = await BundleIndex.build(SAMPLE_BUNDLE)
    triage = _make_triage()
    injector = ContextInjector()

    orchestrator = AnalysisOrchestrator()

    stages_reported: list[str] = []

    async def progress_cb(stage: str, pct: float, msg: str) -> None:
        stages_reported.append(stage)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with patch.object(orchestrator, "_run_analysts_parallel", new_callable=AsyncMock, return_value=[_make_analyst_output()]):
            with patch.object(orchestrator, "_run_synthesis", new_callable=AsyncMock, return_value={
                "root_cause": "test root cause",
                "confidence": "high",
                "uncertainty_report": {"what_i_cant_determine": []},
            }):
                result = await orchestrator.run(triage, index, injector, progress_callback=progress_cb)

    assert isinstance(result, AnalysisResult)
    assert "archaeology" in stages_reported
    assert "analysts" in stages_reported
    assert "synthesis" in stages_reported
    assert "complete" in stages_reported


# ══════════════════════════════════════════════════════════════════════
# SynthesisEngine tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_synthesis_receives_correct_inputs() -> None:
    """SynthesisEngine.synthesize should call client.complete with prompt data."""
    engine = SynthesisEngine()
    outputs = [_make_analyst_output()]
    triage = _make_triage()

    mock_client = MagicMock()
    synthesis_json = json.dumps({
        "root_cause": "Application crash loop",
        "confidence": "high",
        "causal_chain": ["Bad code", "Exit 1", "CrashLoopBackOff"],
        "blast_radius": "Single pod",
        "recommended_fixes": [{"priority": 1, "action": "Fix code", "expected_effect": "Pod stabilizes"}],
        "uncertainty_report": {
            "what_i_know": ["Pod is crashing"],
            "what_i_suspect": ["Code bug"],
            "what_i_cant_determine": ["External deps"],
        },
    })
    mock_client.complete = AsyncMock(return_value=synthesis_json)

    result = await engine.synthesize(mock_client, outputs, triage)
    assert result["root_cause"] == "Application crash loop"
    assert result["confidence"] == "high"

    # Verify the prompt included analyst data
    call_args = mock_client.complete.call_args
    user_prompt = call_args.kwargs.get("user") or call_args[1].get("user", "")
    assert "POD Analyst Report" in user_prompt
    assert "Critical pods: 1" in user_prompt


@pytest.mark.asyncio
async def test_synthesis_empty_outputs() -> None:
    """SynthesisEngine should return empty result when no analyst outputs provided."""
    engine = SynthesisEngine()
    mock_client = MagicMock()

    result = await engine.synthesize(mock_client, [], _make_triage())
    assert "No analyst outputs" in result["root_cause"]
    assert result["confidence"] == "low"
    mock_client.complete.assert_not_called()


@pytest.mark.asyncio
async def test_synthesis_handles_malformed_ai_response() -> None:
    """SynthesisEngine should fallback gracefully on non-JSON AI response."""
    engine = SynthesisEngine()
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(return_value="This is not JSON")

    outputs = [_make_analyst_output()]
    result = await engine.synthesize(mock_client, outputs, _make_triage())
    # Should use fallback
    assert result["confidence"] == "low"
    assert "root_cause" in result


# ══════════════════════════════════════════════════════════════════════
# InterviewSession tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_interview_maintains_history() -> None:
    """InterviewSession should append each Q&A to history."""
    from bundle_analyzer.ai.interview import InterviewSession

    analysis = _make_analysis_result()
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(return_value="The pod is crashing due to OOM.")

    session = InterviewSession(analysis, mock_client)
    assert len(session.history) == 0

    await session.ask("Why is the pod crashing?")
    assert len(session.history) == 2
    assert session.history[0]["role"] == "user"
    assert session.history[1]["role"] == "assistant"

    await session.ask("How do I fix it?")
    assert len(session.history) == 4


@pytest.mark.asyncio
async def test_interview_show_pod_command() -> None:
    """InterviewSession should handle 'show pod' commands locally."""
    from bundle_analyzer.ai.interview import InterviewSession

    analysis = _make_analysis_result()
    analysis.triage.critical_pods = [
        PodIssue(
            namespace="default",
            pod_name="crash-pod",
            container_name="app",
            issue_type="CrashLoopBackOff",
            restart_count=15,
            message="CrashLoop",
        )
    ]
    mock_client = MagicMock()
    session = InterviewSession(analysis, mock_client)

    response = await session.ask("show pod crash-pod")
    assert "crash-pod" in response
    assert "CrashLoopBackOff" in response
    # Should NOT call the AI
    mock_client.complete.assert_not_called()


@pytest.mark.asyncio
async def test_interview_show_events_command() -> None:
    """InterviewSession should handle 'show events' command locally."""
    from bundle_analyzer.ai.interview import InterviewSession

    analysis = _make_analysis_result()
    mock_client = MagicMock()
    session = InterviewSession(analysis, mock_client)

    response = await session.ask("show events default")
    # We have a warning event in the triage
    assert "BackOff" in response or "warning" in response.lower() or "Warning" in response
    mock_client.complete.assert_not_called()


@pytest.mark.asyncio
async def test_interview_handles_api_error() -> None:
    """InterviewSession should handle API errors gracefully."""
    from bundle_analyzer.ai.interview import InterviewSession

    analysis = _make_analysis_result()
    mock_client = MagicMock()
    mock_client.complete = AsyncMock(side_effect=RuntimeError("API down"))

    session = InterviewSession(analysis, mock_client)
    response = await session.ask("What is happening?")
    assert "Unable to process" in response
    # History should still be updated
    assert len(session.history) == 2


# ══════════════════════════════════════════════════════════════════════
# ContextInjector tests
# ══════════════════════════════════════════════════════════════════════


def test_context_injector_no_context() -> None:
    """ContextInjector with no path should return prompts unchanged."""
    injector = ContextInjector()
    assert injector.inject("hello world") == "hello world"


def test_context_injector_prepends_context(tmp_path: Path) -> None:
    """ContextInjector should prepend ISV context to prompts."""
    ctx_file = tmp_path / "context.md"
    ctx_file.write_text("Our app uses PostgreSQL 15.")

    injector = ContextInjector(context_path=ctx_file)
    result = injector.inject("Analyze this pod")
    assert "PostgreSQL 15" in result
    assert "Analyze this pod" in result
    # Context should come before the prompt
    assert result.index("PostgreSQL") < result.index("Analyze this pod")


def test_context_injector_missing_file() -> None:
    """ContextInjector should handle missing context file gracefully."""
    injector = ContextInjector(context_path=Path("/nonexistent/context.md"))
    assert injector.context is None
    assert injector.inject("test") == "test"


def test_context_injector_empty_file(tmp_path: Path) -> None:
    """ContextInjector should treat empty files as no context."""
    ctx_file = tmp_path / "empty.md"
    ctx_file.write_text("   \n  ")

    injector = ContextInjector(context_path=ctx_file)
    assert injector.context is None
