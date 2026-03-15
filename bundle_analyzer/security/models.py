"""Pydantic v2 models for the security & data protection layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class RedactionEntry(BaseModel):
    """Record of a single redaction applied to data."""
    pattern_name: str           # human name of what was matched (e.g. "JWT token")
    replacement: str            # what it was replaced with (e.g. "[REDACTED:jwt]")
    detector: str               # which detector found it (e.g. "pattern", "entropy", "structural")
    category: Literal[
        "credential", "pii", "infrastructure",
        "proprietary_code", "prompt_injection", "high_entropy"
    ]
    location: str = ""          # file/field where found
    confidence: float = 1.0     # 0.0-1.0


class SanitizationReport(BaseModel):
    """Summary of all redactions applied to a data unit."""
    total_redactions: int = 0
    redactions_by_category: dict[str, int] = Field(default_factory=dict)
    redactions_by_detector: dict[str, int] = Field(default_factory=dict)
    entries: list[RedactionEntry] = Field(default_factory=list)
    prompt_injection_detected: bool = False
    prompt_injection_count: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add(self, entry: RedactionEntry) -> None:
        """Add a redaction entry and update counters."""
        self.entries.append(entry)
        self.total_redactions += 1
        self.redactions_by_category[entry.category] = (
            self.redactions_by_category.get(entry.category, 0) + 1
        )
        self.redactions_by_detector[entry.detector] = (
            self.redactions_by_detector.get(entry.detector, 0) + 1
        )
        if entry.category == "prompt_injection":
            self.prompt_injection_detected = True
            self.prompt_injection_count += 1

    def merge(self, other: SanitizationReport) -> None:
        """Merge another report into this one."""
        for entry in other.entries:
            self.add(entry)

    def summary_line(self) -> str:
        """Return a one-line summary string."""
        if self.total_redactions == 0:
            return "No sensitive data detected"
        parts = [f"Redacted {self.total_redactions} sensitive patterns"]
        cats = []
        for cat, count in sorted(self.redactions_by_category.items()):
            cats.append(f"{count} {cat}")
        if cats:
            parts.append(f"({', '.join(cats)})")
        if self.prompt_injection_detected:
            parts.append(f"[!] {self.prompt_injection_count} prompt injection(s) neutralized")
        return " ".join(parts)


class SecurityPolicy(BaseModel):
    """Configurable security policy for data handling."""
    mode: Literal["standard", "strict", "allowlist"] = "standard"

    # What to redact
    redact_credentials: bool = True
    redact_pii: bool = True
    redact_internal_ips: bool = True
    redact_hostnames: bool = True
    redact_emails: bool = True
    redact_file_paths: bool = True
    redact_high_entropy: bool = True

    # What to preserve (diagnostic value)
    preserve_k8s_resource_names: bool = True
    preserve_namespace_names: bool = True
    preserve_label_keys: bool = True
    preserve_env_var_names: bool = True
    preserve_container_image_names: bool = True
    preserve_resource_limits: bool = True
    preserve_probe_paths: bool = True
    preserve_event_reasons: bool = True
    preserve_hidden_markers: bool = True   # ***HIDDEN*** stays as-is

    # Limits
    max_log_lines_to_llm: int = 200
    entropy_threshold: float = 4.0
    min_entropy_length: int = 16

    # Extensibility
    custom_patterns: list[str] = Field(default_factory=list)
    allowed_patterns: list[str] = Field(default_factory=list)  # allowlist mode
