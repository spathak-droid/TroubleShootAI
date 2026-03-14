"""Bundle diff endpoint -- compare two analyzed bundles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from loguru import logger

from bundle_analyzer.api.deps import get_store
from bundle_analyzer.api.schemas import DiffRequest
from bundle_analyzer.api.session import SessionStore

router = APIRouter(tags=["diff"])


@router.post("/diff")
async def compare_bundles(
    request: DiffRequest,
    store: SessionStore = Depends(get_store),
) -> Any:
    """Compare two bundles using the DiffEngine.

    Both bundles must have completed at least the triage stage.

    Args:
        request: DiffRequest with before_bundle_id and after_bundle_id.
        store: Injected session store.

    Returns:
        DiffResult with categorized findings.

    Raises:
        HTTPException: 404 if either bundle not found or triage not complete.
    """
    before = store.get(request.before_bundle_id)
    if before is None:
        raise HTTPException(
            status_code=404,
            detail=f"Before bundle {request.before_bundle_id} not found",
        )

    after = store.get(request.after_bundle_id)
    if after is None:
        raise HTTPException(
            status_code=404,
            detail=f"After bundle {request.after_bundle_id} not found",
        )

    if before.index is None or before.triage is None:
        raise HTTPException(
            status_code=400,
            detail=f"Before bundle {request.before_bundle_id} has not completed triage. "
            f"Current status: {before.status}",
        )

    if after.index is None or after.triage is None:
        raise HTTPException(
            status_code=400,
            detail=f"After bundle {request.after_bundle_id} has not completed triage. "
            f"Current status: {after.status}",
        )

    from bundle_analyzer.ai.engines.diff import DiffEngine

    engine = DiffEngine()
    result = await engine.compare(
        before_index=before.index,
        after_index=after.index,
        before_triage=before.triage,
        after_triage=after.triage,
    )

    logger.info(
        "Diff complete: {} vs {} -- {}",
        request.before_bundle_id,
        request.after_bundle_id,
        result.summary,
    )

    return result
