"""Database repository for bundle analysis CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bundle_analyzer.db.models import BundleRecord


async def create_bundle_record(
    db: AsyncSession,
    bundle_id: str,
    filename: str,
    user_id: str = "anonymous",
) -> BundleRecord:
    """Insert a new bundle record after upload.

    Args:
        db: Async database session.
        bundle_id: Unique bundle identifier.
        filename: Original uploaded filename.
        user_id: Firebase user UID.

    Returns:
        The created BundleRecord.
    """
    record = BundleRecord(
        id=bundle_id,
        user_id=user_id,
        filename=filename,
        status="uploaded",
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info("Created DB record for bundle {} (user={})", bundle_id, user_id)
    return record


async def update_bundle_status(
    db: AsyncSession,
    bundle_id: str,
    status: str,
    progress: float = 0.0,
    error: str | None = None,
) -> None:
    """Update the status/progress of a bundle record.

    Args:
        db: Async database session.
        bundle_id: Bundle identifier.
        status: New status string.
        progress: Progress float 0.0-1.0.
        error: Error message if status is 'error'.
    """
    values: dict[str, Any] = {"status": status, "progress": progress}
    if error:
        values["error"] = error
    await db.execute(
        update(BundleRecord).where(BundleRecord.id == bundle_id).values(**values)
    )
    await db.commit()


async def save_analysis_result(
    db: AsyncSession,
    bundle_id: str,
    analysis_dict: dict[str, Any],
    summary: str | None = None,
    finding_count: int = 0,
    critical_count: int = 0,
    warning_count: int = 0,
) -> None:
    """Persist the full analysis result to the database.

    Args:
        db: Async database session.
        bundle_id: Bundle identifier.
        analysis_dict: Serialized AnalysisResult as dict.
        summary: Human-readable summary string.
        finding_count: Total number of findings.
        critical_count: Number of critical findings.
        warning_count: Number of warning findings.
    """
    await db.execute(
        update(BundleRecord)
        .where(BundleRecord.id == bundle_id)
        .values(
            status="complete",
            progress=1.0,
            completed_at=datetime.now(timezone.utc),
            analysis_json=analysis_dict,
            summary=summary,
            finding_count=finding_count,
            critical_count=critical_count,
            warning_count=warning_count,
        )
    )
    await db.commit()
    logger.info("Saved analysis result to DB for bundle {}", bundle_id)


async def save_evaluation_result(
    db: AsyncSession,
    bundle_id: str,
    evaluation_dict: dict[str, Any],
) -> None:
    """Persist the evaluation result to the database.

    Args:
        db: Async database session.
        bundle_id: Bundle identifier.
        evaluation_dict: Serialized EvaluationResult as dict.
    """
    await db.execute(
        update(BundleRecord)
        .where(BundleRecord.id == bundle_id)
        .values(evaluation_json=evaluation_dict)
    )
    await db.commit()


async def get_bundle_record(
    db: AsyncSession,
    bundle_id: str,
) -> BundleRecord | None:
    """Fetch a single bundle record by ID.

    Args:
        db: Async database session.
        bundle_id: Bundle identifier.

    Returns:
        BundleRecord if found, None otherwise.
    """
    result = await db.execute(
        select(BundleRecord).where(BundleRecord.id == bundle_id)
    )
    return result.scalar_one_or_none()


async def list_bundle_records(
    db: AsyncSession,
    user_id: str | None = None,
) -> list[BundleRecord]:
    """Fetch bundle records ordered by upload time (newest first).

    Args:
        db: Async database session.
        user_id: If provided, only return records for this user.

    Returns:
        List of BundleRecord instances.
    """
    query = select(BundleRecord)
    if user_id is not None:
        query = query.where(BundleRecord.user_id == user_id)
    query = query.order_by(BundleRecord.uploaded_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_bundle_record(
    db: AsyncSession,
    bundle_id: str,
) -> bool:
    """Delete a bundle record from the database.

    Args:
        db: Async database session.
        bundle_id: Bundle identifier.

    Returns:
        True if a record was deleted.
    """
    record = await get_bundle_record(db, bundle_id)
    if record is None:
        return False
    await db.delete(record)
    await db.commit()
    logger.info("Deleted DB record for bundle {}", bundle_id)
    return True
