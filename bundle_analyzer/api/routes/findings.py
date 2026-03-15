"""Findings, timeline, predictions, and uncertainty endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.response_scrubber import (
    scrub_findings_list,
    scrub_predictions_list,
    scrub_timeline_list,
    scrub_uncertainty_list,
)
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import (
    AnalysisResult,
    Finding,
    HistoricalEvent,
    PredictedFailure,
    UncertaintyGap,
)

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["findings"])


async def _ensure_analysis(bundle_id: str, session: BundleSession) -> None:
    """Ensure analysis is available, falling back to DB if needed.

    Tries to restore analysis from the database if not in memory.

    Args:
        bundle_id: The bundle identifier.
        session: The bundle session to check/populate.

    Raises:
        HTTPException: 404 if analysis is not available anywhere.
    """
    if session.analysis is not None:
        return

    # Try loading from database
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is not None:
            from bundle_analyzer.db.repository import get_bundle_record
            async with _session_factory() as db:
                record = await get_bundle_record(db, bundle_id)
                if record is not None and record.analysis_json is not None:
                    try:
                        session.analysis = AnalysisResult.model_validate(record.analysis_json)
                        if session.analysis.triage is not None:
                            session.triage = session.analysis.triage
                        return
                    except Exception as exc:
                        logger.warning("Failed to deserialize analysis from DB: {}", exc)
    except Exception as exc:
        logger.warning("Failed to load analysis from DB: {}", exc)

    raise HTTPException(
        status_code=404,
        detail="Analysis not yet complete. "
        f"Current status: {session.status}",
    )


@router.get("/findings", response_model=list[Finding])
async def get_findings(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
    severity: str | None = Query(None, description="Filter by severity: critical, warning, info"),
    type: str | None = Query(None, alias="type", description="Filter by finding type"),
    resource: str | None = Query(None, description="Filter by resource (substring match)"),
) -> Any:
    """Return findings with optional filters.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.
        severity: Optional severity filter.
        type: Optional finding type filter.
        resource: Optional resource name substring filter.

    Returns:
        Filtered list of Finding objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None

    findings = session.analysis.findings

    if severity is not None:
        findings = [f for f in findings if f.severity == severity]
    if type is not None:
        findings = [f for f in findings if f.type == type]
    if resource is not None:
        findings = [f for f in findings if resource.lower() in f.resource.lower()]

    return scrub_findings_list(findings)


@router.get("/timeline", response_model=list[HistoricalEvent])
async def get_timeline(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the reconstructed cluster timeline.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of HistoricalEvent objects sorted by timestamp.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_timeline_list(session.analysis.timeline)


@router.get("/predictions", response_model=list[PredictedFailure])
async def get_predictions(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return predicted failures from trend analysis.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of PredictedFailure objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_predictions_list(session.analysis.predictions)


@router.get("/uncertainty", response_model=list[UncertaintyGap])
async def get_uncertainty(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return explicit uncertainty gaps in the analysis.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of UncertaintyGap objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_uncertainty_list(session.analysis.uncertainty)
