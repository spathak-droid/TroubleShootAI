"""Fix simulation endpoint -- runs what-if analysis for a proposed fix."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import AnalysisResult, Finding, SimulationResult

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["simulation"])


class SimulateFixRequest(BaseModel):
    """Request body for the simulate-fix endpoint.

    Attributes:
        finding_id: The ID of the finding whose fix to simulate.
        fix_index: Which fix to simulate (0-based). Defaults to the first fix.
    """

    finding_id: str
    fix_index: int = 0


async def _load_analysis(bundle_id: str, session: BundleSession) -> AnalysisResult:
    """Load analysis from session or database.

    Args:
        bundle_id: The bundle identifier.
        session: The bundle session.

    Returns:
        The AnalysisResult.

    Raises:
        HTTPException: 404 if analysis is not available.
    """
    if session.analysis is not None:
        return session.analysis

    # Try loading from database
    try:
        from bundle_analyzer.db.database import _session_factory

        if _session_factory is not None:
            from bundle_analyzer.db.repository import get_bundle_record

            async with _session_factory() as db:
                record = await get_bundle_record(db, bundle_id)
                if record is not None and record.analysis_json is not None:
                    analysis = AnalysisResult.model_validate(record.analysis_json)
                    session.analysis = analysis
                    return analysis
    except Exception as exc:
        logger.warning("Failed to load analysis from DB for simulation: {}", exc)

    raise HTTPException(
        status_code=404,
        detail="Analysis not yet complete. Cannot run simulation.",
    )


@router.post("/simulate-fix", response_model=SimulationResult)
async def simulate_fix(
    bundle_id: str,
    request: SimulateFixRequest,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Simulate the effects of applying a fix to a finding.

    Runs the FixSimulationEngine to predict what would happen if the
    specified fix were applied to the cluster.

    Args:
        bundle_id: The bundle identifier from the URL path.
        request: The simulation request with finding_id and fix_index.
        session: The bundle session.

    Returns:
        SimulationResult with predicted outcomes.

    Raises:
        HTTPException: 404 if finding not found, 400 if no fix available.
    """
    analysis = await _load_analysis(bundle_id, session)

    # Find the specified finding
    finding: Finding | None = None
    for f in analysis.findings:
        if f.id == request.finding_id:
            finding = f
            break

    if finding is None:
        raise HTTPException(
            status_code=404,
            detail=f"Finding '{request.finding_id}' not found in analysis.",
        )

    # Get the fix
    if finding.fix is None:
        raise HTTPException(
            status_code=400,
            detail=f"Finding '{request.finding_id}' has no fix to simulate.",
        )

    fix = finding.fix

    # Build a summary of the analysis for context
    summary_parts: list[str] = []
    crit = sum(1 for f in analysis.findings if f.severity == "critical")
    warn = sum(1 for f in analysis.findings if f.severity == "warning")
    info_count = sum(1 for f in analysis.findings if f.severity == "info")
    summary_parts.append(f"Total findings: {len(analysis.findings)} ({crit} critical, {warn} warning, {info_count} info)")

    if analysis.root_cause:
        summary_parts.append(f"Root cause: {analysis.root_cause}")

    for f in analysis.findings[:5]:
        summary_parts.append(f"- [{f.severity}] {f.resource}: {f.symptom}")

    analysis_summary = "\n".join(summary_parts) if summary_parts else "No summary available."

    # Run simulation
    logger.info(
        "Running fix simulation for finding {fid} in bundle {bid}",
        fid=request.finding_id,
        bid=bundle_id,
    )

    from bundle_analyzer.ai.engines.simulation import FixSimulationEngine

    engine = FixSimulationEngine()
    result = await engine.simulate(
        fix=fix,
        finding=finding,
        analysis_summary=analysis_summary,
    )

    return result
