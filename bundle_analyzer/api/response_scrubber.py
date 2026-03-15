"""Scrub API responses before sending to frontend.

Ensures sensitive data (credentials, IPs, secrets) embedded in
evidence excerpts, findings, and timeline events is redacted
before reaching the browser.
"""

from __future__ import annotations

import copy
from typing import Any

from bundle_analyzer.security.scrubber import BundleScrubber

_scrubber = BundleScrubber()


def scrub_analysis_response(data: Any) -> Any:
    """Scrub an AnalysisResult before returning via API.

    Handles both Pydantic model instances and raw dicts (from DB).
    Scrubs text fields that may contain sensitive data while preserving
    structural/numeric fields.

    Args:
        data: AnalysisResult model or dict to scrub.

    Returns:
        Scrubbed copy (original is not modified).
    """
    if data is None:
        return data

    # Convert to dict if Pydantic model
    if hasattr(data, "model_dump"):
        result = data.model_dump(mode="json")
    elif isinstance(data, dict):
        result = copy.deepcopy(data)
    else:
        return data

    # Scrub findings
    for finding in result.get("findings", []):
        _scrub_text_field(finding, "symptom")
        _scrub_text_field(finding, "root_cause")
        _scrub_evidence_list(finding.get("evidence", []))
        fix = finding.get("fix")
        if fix and isinstance(fix, dict):
            _scrub_text_field(fix, "description")

    # Scrub timeline events
    for event in result.get("timeline", []):
        _scrub_text_field(event, "description")

    # Scrub predictions
    for pred in result.get("predictions", []):
        _scrub_text_field(pred, "prevention")
        _scrub_evidence_list(pred.get("evidence", []))

    # Scrub uncertainty gaps
    for gap in result.get("uncertainty", []):
        _scrub_text_field(gap, "question")
        _scrub_text_field(gap, "reason")
        _scrub_text_field(gap, "to_investigate")

    # Scrub log diagnoses
    for diag in result.get("log_diagnoses", []):
        _scrub_text_field(diag, "diagnosis")
        _scrub_text_field(diag, "summary")
        _scrub_evidence_list(diag.get("evidence", []))

    # Scrub top-level fields
    _scrub_text_field(result, "root_cause")
    _scrub_text_field(result, "summary")
    _scrub_text_field(result, "cluster_summary")

    return result


def scrub_triage_response(data: Any) -> Any:
    """Scrub a TriageResult before returning via API.

    Args:
        data: TriageResult model or dict to scrub.

    Returns:
        Scrubbed copy.
    """
    if data is None:
        return data

    if hasattr(data, "model_dump"):
        result = data.model_dump(mode="json")
    elif isinstance(data, dict):
        result = copy.deepcopy(data)
    else:
        return data

    # Scrub pod issue fields that may contain log excerpts
    for field in ("critical_pods", "warning_pods"):
        for pod in result.get(field, []):
            _scrub_text_field(pod, "message")
            _scrub_text_field(pod, "evidence_excerpt")

    for node in result.get("node_issues", []):
        _scrub_text_field(node, "message")
        _scrub_text_field(node, "evidence_excerpt")

    for cfg in result.get("config_issues", []):
        _scrub_text_field(cfg, "message")
        _scrub_text_field(cfg, "evidence_excerpt")

    return result


def scrub_findings_list(findings: list[Any]) -> list[dict[str, Any]]:
    """Scrub a list of Finding objects/dicts.

    Args:
        findings: List of Finding models or dicts.

    Returns:
        List of scrubbed dicts.
    """
    result: list[dict[str, Any]] = []
    for f in findings:
        if hasattr(f, "model_dump"):
            d = f.model_dump(mode="json")
        elif isinstance(f, dict):
            d = copy.deepcopy(f)
        else:
            result.append(f)
            continue
        _scrub_text_field(d, "symptom")
        _scrub_text_field(d, "root_cause")
        _scrub_evidence_list(d.get("evidence", []))
        fix = d.get("fix")
        if fix and isinstance(fix, dict):
            _scrub_text_field(fix, "description")
        result.append(d)
    return result


def scrub_timeline_list(events: list[Any]) -> list[dict[str, Any]]:
    """Scrub a list of HistoricalEvent objects/dicts.

    Args:
        events: List of HistoricalEvent models or dicts.

    Returns:
        List of scrubbed dicts.
    """
    result: list[dict[str, Any]] = []
    for e in events:
        if hasattr(e, "model_dump"):
            d = e.model_dump(mode="json")
        elif isinstance(e, dict):
            d = copy.deepcopy(e)
        else:
            result.append(e)
            continue
        _scrub_text_field(d, "description")
        result.append(d)
    return result


def scrub_predictions_list(predictions: list[Any]) -> list[dict[str, Any]]:
    """Scrub a list of PredictedFailure objects/dicts.

    Args:
        predictions: List of PredictedFailure models or dicts.

    Returns:
        List of scrubbed dicts.
    """
    result: list[dict[str, Any]] = []
    for p in predictions:
        if hasattr(p, "model_dump"):
            d = p.model_dump(mode="json")
        elif isinstance(p, dict):
            d = copy.deepcopy(p)
        else:
            result.append(p)
            continue
        _scrub_text_field(d, "prevention")
        _scrub_evidence_list(d.get("evidence", []))
        result.append(d)
    return result


def scrub_uncertainty_list(gaps: list[Any]) -> list[dict[str, Any]]:
    """Scrub a list of UncertaintyGap objects/dicts.

    Args:
        gaps: List of UncertaintyGap models or dicts.

    Returns:
        List of scrubbed dicts.
    """
    result: list[dict[str, Any]] = []
    for g in gaps:
        if hasattr(g, "model_dump"):
            d = g.model_dump(mode="json")
        elif isinstance(g, dict):
            d = copy.deepcopy(g)
        else:
            result.append(g)
            continue
        _scrub_text_field(d, "question")
        _scrub_text_field(d, "reason")
        _scrub_text_field(d, "to_investigate")
        result.append(d)
    return result


def _scrub_evidence_list(evidence: list[Any]) -> None:
    """Scrub a list of evidence items, handling both dicts and strings.

    Args:
        evidence: List of evidence dicts or strings.
    """
    for i, ev in enumerate(evidence):
        if isinstance(ev, dict):
            _scrub_text_field(ev, "excerpt")
            _scrub_text_field(ev, "content")
        elif isinstance(ev, str) and ev:
            scrubbed, _ = _scrubber.scrub_for_storage(
                ev, source_type="unknown", source_path="api-response.evidence"
            )
            evidence[i] = scrubbed


def _scrub_text_field(obj: Any, key: str) -> None:
    """Scrub a single text field in a dict, in place.

    Safely handles non-dict objects by skipping them.

    Args:
        obj: Dict containing the field (or any other type, which is skipped).
        key: Field name to scrub.
    """
    if not isinstance(obj, dict):
        return
    val = obj.get(key)
    if isinstance(val, str) and val:
        scrubbed, _ = _scrubber.scrub_for_storage(
            val, source_type="unknown", source_path=f"api-response.{key}"
        )
        obj[key] = scrubbed
