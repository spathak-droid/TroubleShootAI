"""SQLAlchemy models for persistent bundle analysis storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class BundleRecord(Base):
    """Persistent record of a bundle analysis.

    Stores metadata and the full analysis result as JSONB so it
    survives server restarts and can be queried from the homepage.
    """

    __tablename__ = "bundle_analyses"
    __table_args__ = (
        Index("ix_bundle_analyses_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, default="anonymous")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluation_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def to_info_dict(self) -> dict:
        """Convert to a dict suitable for the BundleInfo API response."""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "summary": self.summary,
            "finding_count": self.finding_count,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
        }
