"""Base types and helpers for deterministic RCA rules.

Provides the RCARule dataclass, shared helpers for collecting pod issues,
generating unique IDs, and a factory for building hypothesis dicts with
minimal boilerplate.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bundle_analyzer.models.triage import K8sEvent, PodIssue
from bundle_analyzer.models.troubleshoot import TriageResult


@dataclass
class RCARule:
    """A single deterministic root-cause analysis rule.

    Attributes:
        name: Human-readable rule identifier.
        match: Callable that inspects a TriageResult and returns a list of
            matching finding groups (each group is a list of findings).
            An empty return means the rule did not fire.
        hypothesis_template: Callable that takes the match groups and returns
            a dict suitable for constructing a Hypothesis.
    """

    name: str
    match: Callable[[TriageResult], list[list[Any]]]
    hypothesis_template: Callable[[list[list[Any]]], dict[str, Any]]


def all_pods(triage: TriageResult) -> list[PodIssue]:
    """Return all pod issues (critical + warning)."""
    return list(triage.critical_pods) + list(triage.warning_pods)


def gen_id() -> str:
    """Generate a short unique hypothesis id."""
    return uuid.uuid4().hex[:12]


def build_hypothesis(
    *,
    title: str,
    description: str,
    category: str,
    supporting_evidence: list[str],
    affected_resources: list[str],
    suggested_fixes: list[str],
    is_validated: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """Factory for building hypothesis dicts with consistent structure.

    All hypothesis builders produce the same dict shape. This avoids
    duplicating the structure across 15+ rules.
    """
    result: dict[str, Any] = {
        "id": gen_id(),
        "title": title,
        "description": description,
        "category": category,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": [],
        "affected_resources": affected_resources,
        "suggested_fixes": suggested_fixes,
        "is_validated": is_validated,
    }
    result.update(extra)
    return result


def events_by_reason(triage: TriageResult, reasons: set[str]) -> list[K8sEvent]:
    """Filter warning_events where event.reason matches any reason (case-insensitive)."""
    lower_reasons = {r.lower() for r in reasons}
    return [
        e for e in triage.warning_events
        if e.reason.lower() in lower_reasons
    ]


def log_intel_pods(triage: TriageResult, namespace: str) -> list[tuple[str, Any]]:
    """Filter log_intelligence for keys starting with namespace/."""
    prefix = f"{namespace}/"
    return [
        (key, val)
        for key, val in triage.log_intelligence.items()
        if key.startswith(prefix)
    ]
