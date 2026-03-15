"""Session store for tracking bundle analysis state.

Each uploaded bundle gets a BundleSession that tracks its progress
through the extraction -> triage -> analysis pipeline. The SessionStore
provides CRUD operations over sessions and persists session metadata
to disk so sessions survive server restarts.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from bundle_analyzer.ai.interview import InterviewSession
    from bundle_analyzer.bundle.indexer import BundleIndex
    from bundle_analyzer.models import AnalysisResult, EvaluationResult, TriageResult


class BundleSession:
    """Tracks the full lifecycle of a single bundle analysis.

    Attributes:
        id: Unique session identifier.
        filename: Original uploaded filename.
        status: Current pipeline stage.
        uploaded_at: When the bundle was uploaded.
        bundle_path: Path to the uploaded bundle file on disk.
        extracted_root: Path to the extracted bundle directory.
        index: BundleIndex built from the extracted bundle.
        triage: TriageResult from the triage engine.
        analysis: Full AnalysisResult from the AI pipeline.
        progress: Current progress as a float 0.0-1.0.
        current_stage: Human-readable name of the current stage.
        message: Descriptive message for the current operation.
        error: Error message if the pipeline failed.
        progress_queue: Async queue for streaming progress to WebSocket clients.
        interview_sessions: Active ask sessions keyed by session id.
    """

    def __init__(self, session_id: str, filename: str, bundle_path: Path, user_id: str | None = None) -> None:
        """Initialize a new bundle session.

        Args:
            session_id: Unique identifier for this session.
            filename: Original filename of the uploaded bundle.
            bundle_path: Filesystem path where the bundle was saved.
            user_id: Firebase UID of the owning user.
        """
        self.id: str = session_id
        self.filename: str = filename
        self.user_id: str | None = user_id
        self.status: str = "uploaded"
        self.uploaded_at: datetime = datetime.now(UTC)
        self.bundle_path: Path | None = bundle_path
        self.extracted_root: Path | None = None
        self.index: BundleIndex | None = None
        self.triage: TriageResult | None = None
        self.analysis: AnalysisResult | None = None
        self.progress: float = 0.0
        self.current_stage: str = "uploaded"
        self.message: str = "Bundle uploaded, waiting for analysis"
        self.error: str | None = None
        self.progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.evaluation: EvaluationResult | None = None
        self.evaluation_status: str = "not_started"
        self.interview_sessions: dict[str, InterviewSession] = {}

    def update_progress(self, stage: str, pct: float, message: str) -> None:
        """Update progress and push a message to the progress queue.

        Args:
            stage: Current pipeline stage name.
            pct: Progress percentage (0.0-1.0).
            message: Human-readable progress message.
        """
        self.current_stage = stage
        self.progress = pct
        self.message = message
        self.status = stage if stage in ("extracting", "triaging", "analyzing", "complete", "error") else self.status
        try:
            self.progress_queue.put_nowait({
                "stage": stage,
                "pct": pct,
                "message": message,
            })
        except asyncio.QueueFull:
            logger.warning("Progress queue full for session {}", self.id)


class SessionStore:
    """Persistent store for bundle sessions.

    Provides CRUD operations over BundleSession instances.
    Session metadata is persisted to disk so sessions survive server restarts.
    """

    _SESSIONS_DIR = Path(__file__).resolve().parent.parent.parent / ".sessions"

    def __init__(self) -> None:
        """Initialize session store and restore persisted sessions."""
        self._sessions: dict[str, BundleSession] = {}
        self._SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._restore_sessions()

    def _persist_session(self, session: BundleSession) -> None:
        """Write session metadata to disk."""
        data = {
            "id": session.id,
            "filename": session.filename,
            "status": session.status,
            "user_id": session.user_id,
            "uploaded_at": session.uploaded_at.isoformat(),
            "bundle_path": str(session.bundle_path) if session.bundle_path else None,
            "extracted_root": str(session.extracted_root) if session.extracted_root else None,
        }
        path = self._SESSIONS_DIR / f"{session.id}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def _restore_sessions(self) -> None:
        """Restore sessions from disk on startup."""
        for path in self._SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                bundle_path = Path(data["bundle_path"]) if data.get("bundle_path") else None
                if bundle_path and not bundle_path.exists():
                    logger.debug("Skipping session {} — bundle file missing", data["id"])
                    path.unlink(missing_ok=True)
                    continue
                session = BundleSession(
                    session_id=data["id"],
                    filename=data["filename"],
                    bundle_path=bundle_path or Path("/dev/null"),
                    user_id=data.get("user_id"),
                )
                session.status = data.get("status", "uploaded")
                session.uploaded_at = datetime.fromisoformat(data["uploaded_at"])
                if data.get("extracted_root"):
                    extracted = Path(data["extracted_root"])
                    if extracted.exists():
                        session.extracted_root = extracted
                self._sessions[session.id] = session
                logger.info("Restored session {} ({})", session.id, session.filename)
            except Exception as exc:
                logger.warning("Failed to restore session from {}: {}", path, exc)

    def create(self, filename: str, bundle_path: Path, user_id: str | None = None) -> BundleSession:
        """Create a new session for an uploaded bundle.

        Args:
            filename: Original filename of the uploaded bundle.
            bundle_path: Filesystem path where the bundle was saved.
            user_id: Firebase UID of the owning user.

        Returns:
            The newly created BundleSession.
        """
        session_id = uuid.uuid4().hex[:12]
        session = BundleSession(
            session_id=session_id,
            filename=filename,
            bundle_path=bundle_path,
            user_id=user_id,
        )
        self._sessions[session_id] = session
        self._persist_session(session)
        logger.info("Created session {} for {}", session_id, filename)
        return session

    def get(self, session_id: str) -> BundleSession | None:
        """Retrieve a session by its identifier.

        Args:
            session_id: The session id to look up.

        Returns:
            The BundleSession if found, or None.
        """
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        """Remove a session from the store.

        Args:
            session_id: The session id to remove.

        Returns:
            True if the session was found and removed, False otherwise.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            (self._SESSIONS_DIR / f"{session_id}.json").unlink(missing_ok=True)
            logger.info("Deleted session {}", session_id)
            return True
        return False

    def list_all(self) -> list[BundleSession]:
        """Return all active sessions.

        Returns:
            List of all BundleSession instances, ordered by upload time.
        """
        return sorted(
            self._sessions.values(),
            key=lambda s: s.uploaded_at,
            reverse=True,
        )
