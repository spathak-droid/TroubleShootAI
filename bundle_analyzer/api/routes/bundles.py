"""Bundle upload, listing, and deletion endpoints."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, UploadFile

from loguru import logger

from bundle_analyzer.api.deps import get_session, get_store
from bundle_analyzer.api.schemas import (
    AnalysisStatusEnum,
    BundleInfo,
    UploadResponse,
)
from bundle_analyzer.api.session import BundleSession, SessionStore
from bundle_analyzer.api.upload import save_upload

router = APIRouter(prefix="/bundles", tags=["bundles"])


@router.post("/upload", response_model=UploadResponse)
async def upload_bundle(
    file: UploadFile,
    store: SessionStore = Depends(get_store),
) -> UploadResponse:
    """Upload a support bundle file (streaming, handles 500MB+).

    Args:
        file: The uploaded bundle file (tar.gz).
        store: Injected session store.

    Returns:
        UploadResponse with the new bundle_id.
    """
    dest = await save_upload(file)
    session = store.create(filename=file.filename or "bundle.tar.gz", bundle_path=dest)

    return UploadResponse(
        bundle_id=session.id,
        filename=session.filename,
        message="Bundle uploaded successfully",
    )


@router.get("", response_model=list[BundleInfo])
async def list_bundles(
    store: SessionStore = Depends(get_store),
) -> list[BundleInfo]:
    """List all uploaded bundles.

    Args:
        store: Injected session store.

    Returns:
        List of BundleInfo summaries.
    """
    results: list[BundleInfo] = []
    for session in store.list_all():
        metadata = None
        if session.index is not None and session.index.metadata is not None:
            metadata = session.index.metadata.model_dump(mode="json")
        results.append(
            BundleInfo(
                id=session.id,
                filename=session.filename,
                status=AnalysisStatusEnum(session.status),
                uploaded_at=session.uploaded_at,
                metadata=metadata,
            )
        )
    return results


@router.delete("/{bundle_id}")
async def delete_bundle(
    session: BundleSession = Depends(get_session),
    store: SessionStore = Depends(get_store),
) -> dict[str, str]:
    """Delete a bundle and clean up its files.

    Args:
        session: The bundle session to delete.
        store: Injected session store.

    Returns:
        Confirmation message.
    """
    # Clean up extracted files
    if session.extracted_root is not None and session.extracted_root.exists():
        try:
            shutil.rmtree(session.extracted_root, ignore_errors=True)
            logger.info("Cleaned up extracted dir {}", session.extracted_root)
        except OSError as exc:
            logger.warning("Failed to clean extracted dir: {}", exc)

    # Clean up the uploaded bundle file
    if session.bundle_path is not None and session.bundle_path.exists():
        try:
            session.bundle_path.unlink()
            logger.info("Cleaned up bundle file {}", session.bundle_path)
        except OSError as exc:
            logger.warning("Failed to clean bundle file: {}", exc)

    store.delete(session.id)
    return {"detail": f"Bundle {session.id} deleted"}
