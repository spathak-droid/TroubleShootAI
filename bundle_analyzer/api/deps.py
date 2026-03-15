"""FastAPI dependency injection providers.

Centralises shared singletons (SessionStore) and common parameter
extraction (session lookup with 404 handling).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bundle_analyzer.api.session import BundleSession, SessionStore

_store = SessionStore()


def get_store() -> SessionStore:
    """Return the global session store singleton.

    Returns:
        The shared SessionStore instance.
    """
    return _store


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async database session, or None if DB is not configured.

    Yields:
        An AsyncSession for database operations.
    """
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is not None:
            async with _session_factory() as session:
                yield session
                return
    except Exception:
        pass
    # DB not available — yield None so callers can handle gracefully
    yield None  # type: ignore[arg-type]


async def get_session(
    bundle_id: str,
    store: SessionStore = Depends(get_store),
) -> BundleSession:
    """Look up a bundle session by id.

    First checks in-memory store. If not found, checks the database
    and creates a stub in-memory session from the DB record so that
    subsequent calls to status/analysis endpoints work.

    Args:
        bundle_id: The bundle/session identifier from the URL path.
        store: Injected session store.

    Returns:
        The matching BundleSession.

    Raises:
        HTTPException: 404 if no session exists in memory or DB.
    """
    session = store.get(bundle_id)
    if session is not None:
        return session

    # Try restoring from database
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is not None:
            from bundle_analyzer.db.repository import get_bundle_record
            async with _session_factory() as db:
                record = await get_bundle_record(db, bundle_id)
                if record is not None:
                    # Create a stub in-memory session from the DB record
                    stub = BundleSession(
                        session_id=record.id,
                        filename=record.filename,
                        bundle_path=Path("/dev/null"),
                    )
                    stub.status = record.status
                    stub.uploaded_at = record.uploaded_at
                    stub.progress = record.progress or 0.0
                    stub.current_stage = record.status
                    stub.message = record.summary or ""
                    stub.error = record.error

                    # Restore analysis result from JSONB if complete
                    if record.status == "complete" and record.analysis_json:
                        try:
                            from bundle_analyzer.models import AnalysisResult
                            stub.analysis = AnalysisResult.model_validate(record.analysis_json)
                            # Also populate triage from the analysis
                            if stub.analysis is not None and stub.analysis.triage is not None:
                                stub.triage = stub.analysis.triage
                        except Exception as exc:
                            logger.warning("Failed to deserialize analysis from DB: {}", exc)
                            # Store raw dict so endpoints can serve it directly
                            stub._raw_analysis_json = record.analysis_json
                            stub.analysis = None

                    # Restore evaluation if present
                    if record.evaluation_json:
                        try:
                            from bundle_analyzer.models import EvaluationResult
                            stub.evaluation = EvaluationResult.model_validate(record.evaluation_json)
                            stub.evaluation_status = "complete"
                        except Exception as exc:
                            logger.warning("Failed to deserialize evaluation from DB: {}", exc)
                            stub._raw_evaluation_json = record.evaluation_json

                    # Cache in the store so subsequent requests don't hit DB again
                    store._sessions[bundle_id] = stub
                    logger.info("Restored session {} from database", bundle_id)
                    return stub
    except Exception as exc:
        logger.warning("DB session restore failed for {}: {}", bundle_id, exc)

    raise HTTPException(
        status_code=404,
        detail=f"Bundle {bundle_id} not found",
    )
