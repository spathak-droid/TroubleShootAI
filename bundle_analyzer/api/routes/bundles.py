"""Bundle upload, listing, and deletion endpoints."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bundle_analyzer.api.deps import get_db, get_session, get_store
from bundle_analyzer.api.firebase_auth import get_current_user
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
    user_id: str = Depends(get_current_user),
    store: SessionStore = Depends(get_store),
    db: AsyncSession | None = Depends(get_db),
) -> UploadResponse:
    """Upload a support bundle file (streaming, handles 500MB+).

    Args:
        file: The uploaded bundle file (tar.gz).
        user_id: Authenticated Firebase user UID.
        store: Injected session store.
        db: Optional database session.

    Returns:
        UploadResponse with the new bundle_id.
    """
    dest = await save_upload(file)
    session = store.create(filename=file.filename or "bundle.tar.gz", bundle_path=dest, user_id=user_id)

    # Persist to database with user_id
    if db is not None:
        try:
            from bundle_analyzer.db.repository import create_bundle_record
            await create_bundle_record(db, session.id, session.filename, user_id=user_id)
        except Exception as exc:
            logger.warning("Failed to persist bundle to DB: {}", exc)

    return UploadResponse(
        bundle_id=session.id,
        filename=session.filename,
        message="Bundle uploaded successfully",
    )


@router.get("", response_model=list[BundleInfo])
async def list_bundles(
    user_id: str = Depends(get_current_user),
    store: SessionStore = Depends(get_store),
    db: AsyncSession | None = Depends(get_db),
) -> list[BundleInfo]:
    """List bundles for the authenticated user.

    Args:
        user_id: Authenticated Firebase user UID.
        store: Injected session store.
        db: Optional database session.

    Returns:
        List of BundleInfo summaries for this user only.
    """
    # Try database first — filter by user_id
    if db is not None:
        try:
            from bundle_analyzer.db.repository import list_bundle_records
            records = await list_bundle_records(db, user_id=user_id)
            results: list[BundleInfo] = []

            for record in records:
                # If session is live in memory, use its current status
                mem_session = store.get(record.id)
                if mem_session is not None and mem_session.status in (
                    "extracting", "triaging", "analyzing"
                ):
                    status = AnalysisStatusEnum(mem_session.status)
                else:
                    status = AnalysisStatusEnum(record.status)

                results.append(
                    BundleInfo(
                        id=record.id,
                        filename=record.filename,
                        status=status,
                        uploaded_at=record.uploaded_at,
                        completed_at=record.completed_at,
                        summary=record.summary,
                        finding_count=record.finding_count,
                        critical_count=record.critical_count,
                        warning_count=record.warning_count,
                    )
                )

            # Add any in-memory sessions not yet in DB (same user only)
            db_ids = {r.id for r in records}
            for session in store.list_all():
                if session.id not in db_ids and session.user_id == user_id:
                    results.append(
                        BundleInfo(
                            id=session.id,
                            filename=session.filename,
                            status=AnalysisStatusEnum(session.status),
                            uploaded_at=session.uploaded_at,
                        )
                    )

            return results
        except Exception as exc:
            logger.warning("DB list failed, falling back to in-memory: {}", exc)

    # Fallback: in-memory session store — filter by user_id
    results = []
    for session in store.list_all():
        if session.user_id != user_id:
            continue
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
    user_id: str = Depends(get_current_user),
    session: BundleSession = Depends(get_session),
    store: SessionStore = Depends(get_store),
    db: AsyncSession | None = Depends(get_db),
) -> dict[str, str]:
    """Delete a bundle and clean up its files.

    Args:
        user_id: Authenticated Firebase user UID.
        session: The bundle session to delete.
        store: Injected session store.
        db: Optional database session.

    Returns:
        Confirmation message.
    """
    # Verify ownership
    if db is not None:
        try:
            from bundle_analyzer.db.repository import get_bundle_record
            record = await get_bundle_record(db, session.id)
            if record is not None and record.user_id != user_id:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Not your bundle")
        except ImportError:
            pass

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

    # Remove from database
    if db is not None:
        try:
            from bundle_analyzer.db.repository import delete_bundle_record
            await delete_bundle_record(db, session.id)
        except Exception as exc:
            logger.warning("Failed to delete bundle from DB: {}", exc)

    store.delete(session.id)
    return {"detail": f"Bundle {session.id} deleted"}
