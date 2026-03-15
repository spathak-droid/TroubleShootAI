"""Analysis pipeline endpoints -- start, status, and result retrieval."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from loguru import logger

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.response_scrubber import scrub_analysis_response, scrub_triage_response
from bundle_analyzer.api.schemas import (
    AnalysisStatus,
    AnalysisStatusEnum,
    AnalyzeRequest,
)
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import AnalysisResult, EvaluationResult, TriageResult

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["analysis"])


async def _persist_analysis_to_db(session: BundleSession, analysis: AnalysisResult) -> None:
    """Save completed analysis to the database.

    Args:
        session: The bundle session.
        analysis: The completed AnalysisResult.
    """
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is None:
            return

        from bundle_analyzer.db.repository import save_analysis_result

        # Count findings by severity
        findings = getattr(analysis, "findings", []) or []
        finding_count = len(findings)
        critical_count = sum(1 for f in findings if getattr(f, "severity", "") == "critical")
        warning_count = sum(1 for f in findings if getattr(f, "severity", "") == "warning")
        summary = getattr(analysis, "summary", None)

        # Serialize to dict
        analysis_dict = analysis.model_dump(mode="json") if hasattr(analysis, "model_dump") else {}

        async with _session_factory() as db:
            await save_analysis_result(
                db,
                bundle_id=session.id,
                analysis_dict=analysis_dict,
                summary=summary,
                finding_count=finding_count,
                critical_count=critical_count,
                warning_count=warning_count,
            )
    except Exception as exc:
        logger.warning("Failed to persist analysis to DB: {}", exc)


async def _persist_error_to_db(bundle_id: str, error: str) -> None:
    """Update the database record to reflect a pipeline error.

    Args:
        bundle_id: The bundle identifier.
        error: Error message string.
    """
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is None:
            return

        from bundle_analyzer.db.repository import update_bundle_status

        async with _session_factory() as db:
            await update_bundle_status(db, bundle_id, "error", error=error)
    except Exception as exc:
        logger.warning("Failed to persist error to DB: {}", exc)


async def _run_pipeline(
    session: BundleSession,
    context_text: str | None = None,
    context_path: Path | None = None,
) -> None:
    """Execute the full analysis pipeline as a background task.

    Stages: extract -> index -> triage -> AI analysis.
    Updates session state and pushes progress messages at each step.

    Args:
        session: The bundle session to run the pipeline on.
        context_text: Optional ISV context as raw text from the user.
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

        context_injector = ContextInjector(context_text=context_text, context_path=context_path)
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

        # Persist analysis result to database
        await _persist_analysis_to_db(session, analysis)

    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        session.update_progress("error", session.progress, f"Error: {exc}")
        logger.error("Pipeline failed for session {}: {}", session.id, exc)

        # Update DB status to error
        await _persist_error_to_db(session.id, str(exc))


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

    # Context resolution: query param or JSON body
    context_value = context if context is not None else (request.context if request else None)

    # Determine if context is a file path or raw text
    context_text: str | None = None
    context_path: Path | None = None
    if context_value:
        p = Path(context_value)
        if p.exists() and p.is_file():
            context_path = p
        else:
            context_text = context_value

    asyncio.create_task(_run_pipeline(session, context_text=context_text, context_path=context_path))

    return AnalysisStatus(
        bundle_id=session.id,
        status=AnalysisStatusEnum.extracting,
        progress=0.0,
        current_stage="extracting",
        message="Analysis started",
    )


@router.get("/analysis", response_model=AnalysisResult)
async def get_analysis(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the full AnalysisResult for a completed analysis.

    Falls back to database if the result is not in memory.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        The complete AnalysisResult.

    Raises:
        HTTPException: 404 if analysis has not completed yet.
    """
    if session.analysis is not None:
        return scrub_analysis_response(session.analysis)

    # Try loading from database
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is not None:
            from bundle_analyzer.db.repository import get_bundle_record
            async with _session_factory() as db:
                record = await get_bundle_record(db, bundle_id)
                if record is not None and record.analysis_json is not None:
                    return scrub_analysis_response(record.analysis_json)
    except Exception as exc:
        logger.warning("Failed to load analysis from DB: {}", exc)

    raise HTTPException(
        status_code=404,
        detail="Analysis not yet complete. "
        f"Current status: {session.status}",
    )


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
    return scrub_triage_response(session.triage)


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

        # Persist evaluation to DB
        await _persist_evaluation_to_db(session.id, result)

    except Exception as exc:
        session.evaluation_status = "error"
        logger.error("Validation failed for session {}: {}", session.id, exc)


async def _persist_evaluation_to_db(bundle_id: str, evaluation: Any) -> None:
    """Save evaluation result to the database.

    Args:
        bundle_id: The bundle identifier.
        evaluation: The EvaluationResult to persist.
    """
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is None:
            return

        from bundle_analyzer.db.repository import save_evaluation_result

        eval_dict = evaluation.model_dump(mode="json") if hasattr(evaluation, "model_dump") else {}
        async with _session_factory() as db:
            await save_evaluation_result(db, bundle_id, eval_dict)
        logger.info("Saved evaluation to DB for bundle {}", bundle_id)
    except Exception as exc:
        logger.warning("Failed to persist evaluation to DB: {}", exc)


@router.post("/evaluate")
async def start_evaluation(
    session: BundleSession = Depends(get_session),
) -> dict[str, str]:
    """Launch independent evaluation as a background task.

    Requires analysis to be complete. Returns current evaluation status.
    If session was restored from DB (no bundle index on disk), tries to
    load evaluation from DB instead.

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

    # If no bundle index (DB-restored session), try loading eval from DB
    if session.index is None:
        evaluation = await _load_evaluation_from_db(session.id)
        if evaluation is not None:
            session.evaluation = evaluation
            session.evaluation_status = "complete"
            return {"status": "complete"}
        raise HTTPException(
            status_code=400,
            detail="Bundle files are no longer on disk (server restarted). "
            "Validation requires the original bundle to verify evidence. "
            "Please re-upload and re-analyze the bundle.",
        )

    asyncio.create_task(_run_evaluation(session))
    return {"status": "evaluating"}


@router.get("/evaluation", response_model=EvaluationResult)
async def get_evaluation(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the EvaluationResult for a completed evaluation.

    Falls back to database if not in memory.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        The complete EvaluationResult.

    Raises:
        HTTPException: 404 if evaluation has not completed yet.
    """
    if session.evaluation is not None:
        return session.evaluation

    # Try loading from DB
    evaluation = await _load_evaluation_from_db(bundle_id)
    if evaluation is not None:
        session.evaluation = evaluation
        session.evaluation_status = "complete"
        return evaluation

    raise HTTPException(
        status_code=404,
        detail="Evaluation not yet complete. "
        f"Current status: {session.evaluation_status}",
    )


@router.get("/evaluation/status")
async def get_evaluation_status(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> dict[str, str]:
    """Return the current evaluation status.

    Also checks DB for previously completed evaluations.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        Dict with status field.
    """
    if session.evaluation_status == "complete" and session.evaluation is not None:
        return {"status": "complete"}

    # Check if evaluation exists in DB
    if session.evaluation_status == "not_started":
        evaluation = await _load_evaluation_from_db(bundle_id)
        if evaluation is not None:
            session.evaluation = evaluation
            session.evaluation_status = "complete"
            return {"status": "complete"}

    return {"status": session.evaluation_status}


async def _load_evaluation_from_db(bundle_id: str) -> Any:
    """Try to load evaluation result from the database.

    Args:
        bundle_id: The bundle identifier.

    Returns:
        EvaluationResult dict if found, None otherwise.
    """
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is None:
            return None

        from bundle_analyzer.db.repository import get_bundle_record

        async with _session_factory() as db:
            record = await get_bundle_record(db, bundle_id)
            if record is not None and record.evaluation_json is not None:
                return record.evaluation_json
    except Exception as exc:
        logger.warning("Failed to load evaluation from DB: {}", exc)
    return None


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
