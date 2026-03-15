"""Findings, timeline, predictions, and uncertainty endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.response_scrubber import (
    scrub_findings_list,
    scrub_predictions_list,
    scrub_timeline_list,
    scrub_uncertainty_list,
)
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import (
    Finding,
    HistoricalEvent,
    PredictedFailure,
    UncertaintyGap,
)

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["findings"])


def _require_analysis(session: BundleSession) -> None:
    """Raise 404 if the analysis has not completed yet.

    Args:
        session: The bundle session to check.

    Raises:
        HTTPException: 404 if analysis is not available.
    """
    if session.analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not yet complete. "
            f"Current status: {session.status}",
        )


@router.get("/findings", response_model=list[Finding])
async def get_findings(
    session: BundleSession = Depends(get_session),
    severity: str | None = Query(None, description="Filter by severity: critical, warning, info"),
    type: str | None = Query(None, alias="type", description="Filter by finding type"),
    resource: str | None = Query(None, description="Filter by resource (substring match)"),
) -> Any:
    """Return findings with optional filters.

    Args:
        session: The bundle session.
        severity: Optional severity filter.
        type: Optional finding type filter.
        resource: Optional resource name substring filter.

    Returns:
        Filtered list of Finding objects.
    """
    _require_analysis(session)
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
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the reconstructed cluster timeline.

    Args:
        session: The bundle session.

    Returns:
        List of HistoricalEvent objects sorted by timestamp.
    """
    _require_analysis(session)
    assert session.analysis is not None
    return scrub_timeline_list(session.analysis.timeline)


@router.get("/predictions", response_model=list[PredictedFailure])
async def get_predictions(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return predicted failures from trend analysis.

    Args:
        session: The bundle session.

    Returns:
        List of PredictedFailure objects.
    """
    _require_analysis(session)
    assert session.analysis is not None
    return scrub_predictions_list(session.analysis.predictions)


@router.get("/uncertainty", response_model=list[UncertaintyGap])
async def get_uncertainty(
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return explicit uncertainty gaps in the analysis.

    Args:
        session: The bundle session.

    Returns:
        List of UncertaintyGap objects.
    """
    _require_analysis(session)
    assert session.analysis is not None
    return scrub_uncertainty_list(session.analysis.uncertainty)
