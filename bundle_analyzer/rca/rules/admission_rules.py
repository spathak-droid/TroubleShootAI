"""RCA rules for admission control, PDB deadlocks, and stuck finalizers.

Rules: webhook_admission_failure, pdb_deadlock, finalizer_stuck.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules.base import RCARule, all_pods, build_hypothesis


# ── Rule: Webhook Admission Failure ──────────────────────────────────────

_WEBHOOK_KEYWORDS = {"webhook", "admission", "denied", "failed calling"}


def _match_webhook_admission(triage: TriageResult) -> list[list[Any]]:
    """Find webhook admission failures blocking resource creation."""
    webhook_events = [
        e for e in triage.warning_events
        if any(kw in e.message.lower() for kw in _WEBHOOK_KEYWORDS)
    ]

    zero_ready = [
        d for d in triage.deployment_issues
        if d.ready_replicas == 0
    ]

    webhook_escalations = [
        esc for esc in triage.event_escalations
        if any(kw in r.lower() for r in esc.event_reasons for kw in _WEBHOOK_KEYWORDS)
    ]

    if not webhook_events:
        return []

    if not zero_ready and not webhook_escalations:
        return []

    return [[webhook_events, zero_ready, webhook_escalations]]


def _hyp_webhook_admission(groups: list[list[Any]]) -> dict[str, Any]:
    webhook_events = groups[0][0]
    zero_ready = groups[0][1]
    webhook_escalations = groups[0][2]

    evidence = [
        f"Event: {e.namespace}/{e.involved_object_name} — {e.message[:120]}"
        for e in webhook_events[:5]
    ]
    evidence += [
        f"Deployment {d.namespace}/{d.name} has 0/{d.desired_replicas} ready replicas"
        for d in zero_ready
    ]
    evidence += [
        f"Escalation: {esc.namespace}/{esc.involved_object_name} — {esc.message[:100]}"
        for esc in webhook_escalations[:3]
    ]

    resources = [f"{e.namespace}/{e.involved_object_name}" for e in webhook_events]
    resources += [f"{d.namespace}/{d.name}" for d in zero_ready]

    return build_hypothesis(
        title="Admission Webhook Blocking Resource Creation",
        description=(
            "A validating or mutating admission webhook is rejecting resource "
            "creation requests, preventing deployments from starting. This can "
            "cause zero-ready replicas and cascading failures."
        ),
        category="admission_control",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Check webhook service endpoint health and connectivity",
            "Set failurePolicy: Ignore temporarily to unblock deployments",
            "Delete the broken ValidatingWebhookConfiguration or MutatingWebhookConfiguration",
            "Review webhook logs for rejection reasons",
        ],
    )


# ── Rule: PDB Deadlock ──────────────────────────────────────────────────

_PDB_MESSAGE_KEYWORDS = {"disruption budget", "cannot evict", "pdb", "poddisruptionbudget"}
_PDB_EVENT_REASONS = {"EvictionBlocked", "TooManyRequests"}


def _match_pdb_deadlock(triage: TriageResult) -> list[list[Any]]:
    """Find PDB-related eviction blocks."""
    pdb_events = [
        e for e in triage.warning_events
        if any(kw in e.message.lower() for kw in _PDB_MESSAGE_KEYWORDS)
        or e.reason in _PDB_EVENT_REASONS
    ]

    pdb_escalations = [
        esc for esc in triage.event_escalations
        if any(
            kw in r.lower()
            for r in esc.event_reasons
            for kw in _PDB_MESSAGE_KEYWORDS | {r.lower() for r in _PDB_EVENT_REASONS}
        )
    ]

    if not pdb_events and not pdb_escalations:
        return []

    return [[pdb_events, pdb_escalations]]


def _hyp_pdb_deadlock(groups: list[list[Any]]) -> dict[str, Any]:
    pdb_events = groups[0][0]
    pdb_escalations = groups[0][1]

    evidence = [
        f"Event: {e.namespace}/{e.involved_object_name} reason={e.reason} — {e.message[:120]}"
        for e in pdb_events[:5]
    ]
    evidence += [
        f"Escalation: {esc.namespace}/{esc.involved_object_name} — {esc.message[:100]}"
        for esc in pdb_escalations[:3]
    ]

    resources = [f"{e.namespace}/{e.involved_object_name}" for e in pdb_events]
    resources += [f"{esc.namespace}/{esc.involved_object_name}" for esc in pdb_escalations]

    return build_hypothesis(
        title="PodDisruptionBudget Blocking Eviction or Drain",
        description=(
            "A PodDisruptionBudget is preventing pod evictions, which can block "
            "node drains, cluster upgrades, and scaling operations. This creates "
            "a deadlock when the PDB's minAvailable cannot be satisfied."
        ),
        category="scheduling",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Lower minAvailable on the PDB or switch to maxUnavailable: 1",
            "Check for pending node drains that are blocked by the PDB",
            "Temporarily delete the PDB to allow the drain to proceed",
            "Ensure enough replicas exist to satisfy PDB constraints",
        ],
    )


# ── Rule: Finalizer Stuck ────────────────────────────────────────────────


def _match_finalizer_stuck(triage: TriageResult) -> list[list[Any]]:
    """Find resources stuck in Terminating due to stale finalizers."""
    finalizer_events = [
        e for e in triage.warning_events
        if "finalizer" in e.message.lower()
        or "FailedDelete" in e.reason
    ]

    terminating_pods = [
        p for p in all_pods(triage)
        if p.issue_type == "Terminating"
    ]

    drift_signals = [
        d for d in triage.drift_issues
        if "deletionTimestamp" in d.description
        or "Terminating" in d.description
        or "deletionTimestamp" in d.field
    ]

    if not finalizer_events and not terminating_pods and not drift_signals:
        return []

    return [[finalizer_events, terminating_pods, drift_signals]]


def _hyp_finalizer_stuck(groups: list[list[Any]]) -> dict[str, Any]:
    finalizer_events = groups[0][0]
    terminating_pods = groups[0][1]
    drift_signals = groups[0][2]

    evidence = [
        f"Event: {e.namespace}/{e.involved_object_name} reason={e.reason} — {e.message[:120]}"
        for e in finalizer_events[:5]
    ]
    evidence += [
        f"Pod stuck Terminating: {p.namespace}/{p.pod_name}"
        for p in terminating_pods[:5]
    ]
    evidence += [
        f"Drift: {d.namespace}/{d.name} — {d.description[:100]}"
        for d in drift_signals[:3]
    ]

    resources = [f"{e.namespace}/{e.involved_object_name}" for e in finalizer_events]
    resources += [f"{p.namespace}/{p.pod_name}" for p in terminating_pods]

    return build_hypothesis(
        title="Resource Stuck in Terminating Due to Stale Finalizer",
        description=(
            "One or more resources have a finalizer that is preventing deletion. "
            "This happens when the controller responsible for the finalizer is "
            "gone or malfunctioning, leaving the resource stuck in Terminating state."
        ),
        category="config_error",
        supporting_evidence=evidence,
        affected_resources=list(set(resources)),
        suggested_fixes=[
            "Identify which finalizer controller is responsible",
            "If the controller is gone, manually remove the finalizer from the resource spec",
            "Use kubectl edit or kubectl patch to remove the finalizer",
            "Check for namespace-level finalizers blocking namespace deletion",
        ],
    )


# ── Exported rules ──────────────────────────────────────────────────────

WEBHOOK_ADMISSION_FAILURE_RULE = RCARule(
    name="webhook_admission_failure",
    match=_match_webhook_admission,
    hypothesis_template=_hyp_webhook_admission,
)
PDB_DEADLOCK_RULE = RCARule(
    name="pdb_deadlock",
    match=_match_pdb_deadlock,
    hypothesis_template=_hyp_pdb_deadlock,
)
FINALIZER_STUCK_RULE = RCARule(
    name="finalizer_stuck",
    match=_match_finalizer_stuck,
    hypothesis_template=_hyp_finalizer_stuck,
)
