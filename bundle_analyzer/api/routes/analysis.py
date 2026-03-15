"""Analysis pipeline endpoints -- start, status, and result retrieval."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from loguru import logger

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.schemas import (
    AnalysisStatus,
    AnalysisStatusEnum,
    AnalyzeRequest,
)
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import AnalysisResult, EvaluationResult, TriageResult

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["analysis"])


async def _run_pipeline(session: BundleSession, context_path: Path | None = None) -> None:
    """Execute the full analysis pipeline as a background task.

    Stages: extract -> index -> triage -> AI analysis.
    Updates session state and pushes progress messages at each step.

    Args:
        session: The bundle session to run the pipeline on.
        context_path: Optional path to ISV context file.
    """
    try:
        # Stage 1: Extract
        session.status = "extracting"
        session.update_progress("extracting", 0.05, "Extracting bundle...")

        from bundle_analyzer.bundle.extractor import BundleExtractor

        extractor = BundleExtractor()
        if session.bundle_path is None:
            raise ValueError("No bundle file path set on session")
        root = await extractor.extract(session.bundle_path)
        session.extracted_root = root

        # Stage 2: Index
        session.update_progress("indexing", 0.15, "Indexing bundle contents...")

        from bundle_analyzer.bundle.indexer import BundleIndex

        index = await BundleIndex.build(root)
        session.index = index

        # Stage 3: Triage
        session.status = "triaging"
        session.update_progress("triaging", 0.25, "Running triage scanners...")

        from bundle_analyzer.triage.engine import TriageEngine

        engine = TriageEngine()
        triage = await engine.run(index)
        session.triage = triage

        # Stage 4: AI Analysis
        session.status = "analyzing"
        session.update_progress("analyzing", 0.35, "Starting AI analysis...")

        from bundle_analyzer.ai.context_injector import ContextInjector
        from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator

        context_injector = ContextInjector(context_path=context_path)
        orchestrator = AnalysisOrchestrator()

        def progress_callback(stage: str, pct: float, message: str) -> None:
            """Map orchestrator progress (0-1) to pipeline range (0.35-0.95)."""
            mapped_pct = 0.35 + (pct * 0.60)
            session.update_progress(stage, mapped_pct, message)

        analysis = await orchestrator.run(
            triage=triage,
            index=index,
            context_injector=context_injector,
            progress_callback=progress_callback,
        )
        session.analysis = analysis

        # Complete
        session.status = "complete"
        session.update_progress("complete", 1.0, "Analysis complete")
        logger.info("Pipeline complete for session {}", session.id)

    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        session.update_progress("error", session.progress, f"Error: {exc}")
        logger.error("Pipeline failed for session {}: {}", session.id, exc)


@router.post("/analyze")
async def start_analysis(
    session: BundleSession = Depends(get_session),
    request: AnalyzeRequest | None = Body(default=None),
    context: str | None = None,
) -> AnalysisStatus:
    """Start the full analysis pipeline as a background task.

    If analysis is already running or complete, returns the current status
    without restarting.

    Args:
        session: The bundle session to analyze.
        context: Optional path to an ISV context file.

    Returns:
        Current AnalysisStatus.
    """
    if session.status in ("extracting", "triaging", "analyzing"):
        return AnalysisStatus(
            bundle_id=session.id,
            status=AnalysisStatusEnum(session.status),
            progress=session.progress,
            current_stage=session.current_stage,
            message="Analysis already in progress",
        )

    if session.status == "complete":
        return AnalysisStatus(
            bundle_id=session.id,
            status=AnalysisStatusEnum.complete,
            progress=1.0,
            current_stage="complete",
            message="Analysis already complete",
        )

    # Backward-compatible context resolution:
    # - query parameter `?context=/path/to/file`
    # - JSON body { "context": "/path/to/file" }
    context_value = context if context is not None else (request.context if request else None)
    context_path = Path(context_value) if context_value else None
    asyncio.create_task(_run_pipeline(session, context_path))

    return AnalysisStatus(
        bundle_id=session.id,
        status=AnalysisStatusEnum.extracting,
        progress=0.0,
        current_stage="extracting",
        message="Analysis started",
    )


@router.get("/analysis", response_model=AnalysisResult)
async def get_analysis(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the full AnalysisResult for a completed analysis.

    Args:
        session: The bundle session.

    Returns:
        The complete AnalysisResult.

    Raises:
        HTTPException: 404 if analysis has not completed yet.
    """
    if session.analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not yet complete. "
            f"Current status: {session.status}",
        )
    return session.analysis


@router.get("/analysis/status", response_model=AnalysisStatus)
async def get_analysis_status(
    session: BundleSession = Depends(get_session),
) -> AnalysisStatus:
    """Return the current analysis pipeline status.

    Args:
        session: The bundle session.

    Returns:
        Current AnalysisStatus with progress information.
    """
    return AnalysisStatus(
        bundle_id=session.id,
        status=AnalysisStatusEnum(session.status),
        progress=session.progress,
        current_stage=session.current_stage,
        message=session.error or session.message,
    )


@router.get("/triage", response_model=TriageResult)
async def get_triage(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the TriageResult (available before AI analysis completes).

    Args:
        session: The bundle session.

    Returns:
        The TriageResult from the triage scanners.

    Raises:
        HTTPException: 404 if triage has not completed yet.
    """
    if session.triage is None:
        raise HTTPException(
            status_code=404,
            detail="Triage not yet complete. "
            f"Current status: {session.status}",
        )
    return session.triage


# ── Evaluation endpoints ─────────────────────────────────────────


async def _run_evaluation(session: BundleSession) -> None:
    """Execute the deterministic validation as a background task.

    Args:
        session: The bundle session with completed analysis to evaluate.
    """
    try:
        session.evaluation_status = "evaluating"

        from bundle_analyzer.ai.deterministic_validator import DeterministicValidator

        validator = DeterministicValidator()
        result = validator.validate(
            analysis=session.analysis,
            index=session.index,
        )

        session.evaluation = result
        session.evaluation_status = "complete"
        logger.info("Validation complete for session {}", session.id)

    except Exception as exc:
        session.evaluation_status = "error"
        logger.error("Validation failed for session {}: {}", session.id, exc)


@router.post("/evaluate")
async def start_evaluation(
    session: BundleSession = Depends(get_session),
) -> dict[str, str]:
    """Launch independent evaluation as a background task.

    Requires analysis to be complete. Returns current evaluation status.

    Args:
        session: The bundle session to evaluate.

    Returns:
        Dict with evaluation status.
    """
    if session.analysis is None:
        raise HTTPException(
            status_code=400,
            detail="Analysis must be complete before evaluation can run.",
        )

    if session.evaluation_status == "evaluating":
        return {"status": "evaluating"}

    if session.evaluation_status == "complete" and session.evaluation is not None:
        return {"status": "complete"}

    asyncio.create_task(_run_evaluation(session))
    return {"status": "evaluating"}


@router.get("/evaluation", response_model=EvaluationResult)
async def get_evaluation(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the EvaluationResult for a completed evaluation.

    Args:
        session: The bundle session.

    Returns:
        The complete EvaluationResult.

    Raises:
        HTTPException: 404 if evaluation has not completed yet.
    """
    if session.evaluation is None:
        raise HTTPException(
            status_code=404,
            detail="Evaluation not yet complete. "
            f"Current status: {session.evaluation_status}",
        )
    return session.evaluation


@router.get("/evaluation/status")
async def get_evaluation_status(
    session: BundleSession = Depends(get_session),
) -> dict[str, str]:
    """Return the current evaluation status.

    Args:
        session: The bundle session.

    Returns:
        Dict with status field.
    """
    return {"status": session.evaluation_status}


@router.get("/hypotheses")
async def get_hypotheses(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return ranked RCA hypotheses for a completed analysis.

    Args:
        session: The bundle session.

    Returns:
        List of hypothesis dicts, ranked by confidence.

    Raises:
        HTTPException: 404 if analysis has not completed yet.
    """
    if session.analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not yet complete. "
            f"Current status: {session.status}",
        )
    return session.analysis.hypotheses
