"""Audit logger for security redaction events.

Maintains a structured audit trail of all redaction actions, separate from
the main application log. The audit log never contains raw sensitive data —
only metadata about what was redacted, by which detector, and when.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from bundle_analyzer.security.models import RedactionEntry, SanitizationReport


class AuditLogger:
    """Logs all redaction actions for compliance and debugging.

    Writes to a structured audit log that is separate from the main
    application log. This ensures redaction metadata is available for
    compliance review without leaking sensitive data into observability
    tools.

    Attributes:
        audit_path: Optional file path for persistent audit log.
        entries: In-memory list of audit events.
    """

    def __init__(self, audit_path: Path | None = None) -> None:
        """Initialise the audit logger.

        Args:
            audit_path: Optional file path to write audit events to.
                        If ``None``, events are kept in memory only.
        """
        self.audit_path = audit_path
        self.entries: list[dict[str, Any]] = []
        self._session_start = datetime.now(UTC)

    def log_redaction(self, entry: RedactionEntry, context: str = "") -> None:
        """Record a single redaction event.

        Args:
            entry: The redaction entry to log.
            context: Additional context (e.g., which pipeline stage).
        """
        event = {
            "type": "redaction",
            "timestamp": datetime.now(UTC).isoformat(),
            "pattern_name": entry.pattern_name,
            "detector": entry.detector,
            "category": entry.category,
            "confidence": entry.confidence,
            "location": entry.location,
            "context": context,
        }
        self.entries.append(event)
        self._write_event(event)

    def log_prompt_injection(self, detection: dict[str, Any], source: str) -> None:
        """Record a prompt injection detection event.

        Args:
            detection: Detection dict from ``PromptInjectionGuard.scan()``.
            source: Where the injection was found.
        """
        event = {
            "type": "prompt_injection",
            "timestamp": datetime.now(UTC).isoformat(),
            "injection_type": detection.get("name", "unknown"),
            "severity": detection.get("severity", "unknown"),
            "source": source,
            "preview": detection.get("matched_text", "")[:50],
        }
        self.entries.append(event)
        self._write_event(event)
        logger.warning(
            "Audit: prompt injection detected | type={} severity={} source={}",
            detection.get("name"),
            detection.get("severity"),
            source,
        )

    def log_report(self, report: SanitizationReport, context: str = "") -> None:
        """Record a complete sanitization report.

        Args:
            report: The sanitization report to log.
            context: Pipeline stage or call context.
        """
        event = {
            "type": "sanitization_report",
            "timestamp": datetime.now(UTC).isoformat(),
            "total_redactions": report.total_redactions,
            "by_category": report.redactions_by_category,
            "by_detector": report.redactions_by_detector,
            "prompt_injection_detected": report.prompt_injection_detected,
            "prompt_injection_count": report.prompt_injection_count,
            "context": context,
        }
        self.entries.append(event)
        self._write_event(event)

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate summary of all audit events this session.

        Returns:
            Dictionary with counts by type, category, and detector.
        """
        total = len(self.entries)
        by_type: dict[str, int] = {}
        by_category: dict[str, int] = {}
        by_detector: dict[str, int] = {}
        injection_count = 0

        for entry in self.entries:
            event_type = entry.get("type", "unknown")
            by_type[event_type] = by_type.get(event_type, 0) + 1

            if event_type == "redaction":
                cat = entry.get("category", "unknown")
                det = entry.get("detector", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1
                by_detector[det] = by_detector.get(det, 0) + 1
            elif event_type == "prompt_injection":
                injection_count += 1

        return {
            "session_start": self._session_start.isoformat(),
            "total_events": total,
            "events_by_type": by_type,
            "redactions_by_category": by_category,
            "redactions_by_detector": by_detector,
            "prompt_injections": injection_count,
        }

    def export_audit_log(self, path: Path) -> None:
        """Export the full audit trail to a JSON file.

        Args:
            path: Destination file path.
        """
        export = {
            "session_start": self._session_start.isoformat(),
            "exported_at": datetime.now(UTC).isoformat(),
            "total_events": len(self.entries),
            "events": self.entries,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(export, indent=2, default=str))
        logger.info("Audit log exported to {}: {} events", path, len(self.entries))

    def _write_event(self, event: dict[str, Any]) -> None:
        """Append a single event to the audit file, if configured."""
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_path, "a") as fh:
                fh.write(json.dumps(event, default=str) + "\n")
        except OSError as exc:
            logger.debug("Failed to write audit event: {}", exc)
