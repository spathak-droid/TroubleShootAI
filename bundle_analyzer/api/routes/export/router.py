"""Export endpoints — download analysis results as JSON or HTML report."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.routes.export.html_builder import build_html_report
from bundle_analyzer.api.session import BundleSession

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["export"])


def _require_analysis(session: BundleSession) -> None:
    """Raise 404 if analysis is not complete."""
    if session.analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis not yet complete. Current status: {session.status}",
        )


@router.get("/export/json")
async def export_json(
    session: BundleSession = Depends(get_session),
) -> Response:
    """Export the full analysis result as a downloadable JSON file.

    Args:
        session: The bundle session.

    Returns:
        JSON file response with Content-Disposition header.
    """
    _require_analysis(session)
    assert session.analysis is not None

    data = session.analysis.model_dump(mode="json")
    content = json.dumps(data, indent=2, default=str)
    filename = f"analysis-{session.id}-{_timestamp()}.json"

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/html")
async def export_html(
    session: BundleSession = Depends(get_session),
) -> Response:
    """Export the analysis as a self-contained HTML report.

    Args:
        session: The bundle session.

    Returns:
        HTML file response with embedded CSS and all analysis data.
    """
    _require_analysis(session)
    assert session.analysis is not None

    analysis = session.analysis
    triage = analysis.triage
    report_html = build_html_report(analysis, triage, session)
    filename = f"report-{session.id}-{_timestamp()}.html"

    return Response(
        content=report_html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _timestamp() -> str:
    """Return a compact UTC timestamp for filenames."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
