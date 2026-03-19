"""Findings, timeline, predictions, uncertainty, and dependency graph endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from bundle_analyzer.api.deps import get_session
from bundle_analyzer.api.response_scrubber import (
    scrub_findings_list,
    scrub_predictions_list,
    scrub_timeline_list,
    scrub_uncertainty_list,
)
from bundle_analyzer.api.session import BundleSession
from bundle_analyzer.models import (
    AnalysisResult,
    CausalChain,
    Finding,
    HistoricalEvent,
    PredictedFailure,
    TriageResult,
    UncertaintyGap,
)

router = APIRouter(prefix="/bundles/{bundle_id}", tags=["findings"])


async def _ensure_analysis(bundle_id: str, session: BundleSession) -> None:
    """Ensure analysis is available, falling back to DB if needed.

    Tries to restore analysis from the database if not in memory.

    Args:
        bundle_id: The bundle identifier.
        session: The bundle session to check/populate.

    Raises:
        HTTPException: 404 if analysis is not available anywhere.
    """
    if session.analysis is not None:
        return

    # Try loading from database
    try:
        from bundle_analyzer.db.database import _session_factory
        if _session_factory is not None:
            from bundle_analyzer.db.repository import get_bundle_record
            async with _session_factory() as db:
                record = await get_bundle_record(db, bundle_id)
                if record is not None and record.analysis_json is not None:
                    try:
                        session.analysis = AnalysisResult.model_validate(record.analysis_json)
                        if session.analysis.triage is not None:
                            session.triage = session.analysis.triage
                        return
                    except Exception as exc:
                        logger.warning("Failed to deserialize analysis from DB: {}", exc)
    except Exception as exc:
        logger.warning("Failed to load analysis from DB: {}", exc)

    raise HTTPException(
        status_code=404,
        detail="Analysis not yet complete. "
        f"Current status: {session.status}",
    )


@router.get("/findings", response_model=list[Finding])
async def get_findings(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
    severity: str | None = Query(None, description="Filter by severity: critical, warning, info"),
    type: str | None = Query(None, alias="type", description="Filter by finding type"),
    resource: str | None = Query(None, description="Filter by resource (substring match)"),
) -> Any:
    """Return findings with optional filters.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.
        severity: Optional severity filter.
        type: Optional finding type filter.
        resource: Optional resource name substring filter.

    Returns:
        Filtered list of Finding objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None

    findings = session.analysis.findings

    if severity is not None:
        findings = [f for f in findings if f.severity == severity]
    if type is not None:
        findings = [f for f in findings if f.type == type]
    if resource is not None:
        findings = [f for f in findings if resource.lower() in f.resource.lower()]

    return scrub_findings_list(findings)


@router.get("/timeline", response_model=list[HistoricalEvent])
async def get_timeline(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the reconstructed cluster timeline.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of HistoricalEvent objects sorted by timestamp.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_timeline_list(session.analysis.timeline)


@router.get("/predictions", response_model=list[PredictedFailure])
async def get_predictions(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return predicted failures from trend analysis.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of PredictedFailure objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_predictions_list(session.analysis.predictions)


@router.get("/uncertainty", response_model=list[UncertaintyGap])
async def get_uncertainty(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return explicit uncertainty gaps in the analysis.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        List of UncertaintyGap objects.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return scrub_uncertainty_list(session.analysis.uncertainty)


def _build_graph_data(analysis: AnalysisResult) -> dict[str, Any]:
    """Build a dependency graph from analysis findings and causal chains.

    Extracts nodes (resources) and edges (relationships) from findings
    and causal chains to create a visualization-friendly graph structure.

    Args:
        analysis: The completed analysis result.

    Returns:
        Dict with nodes, edges, and causal_chains keys.
    """
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    # Map raw resource IDs to canonical IDs for deduplication
    canonical_map: dict[str, str] = {}

    def _canonical_id(resource_str: str) -> str:
        """Normalize resource strings to a canonical form for deduplication.

        Handles formats like 'pod/default/foo', 'Pod/default/foo', 'default/foo'.
        Returns lowercase 'type/namespace/name' or 'type/name' if no namespace.
        """
        if resource_str in canonical_map:
            return canonical_map[resource_str]
        parts = resource_str.split("/")
        rtype = _resource_type(resource_str)
        if len(parts) >= 3:
            canonical = f"{rtype}/{parts[1]}/{parts[2]}".lower()
        elif len(parts) == 2:
            canonical = f"{rtype}/{parts[0]}/{parts[1]}".lower()
        else:
            canonical = resource_str.lower()
        canonical_map[resource_str] = canonical
        return canonical

    def _resource_type(resource_str: str) -> str:
        """Infer resource type from a resource string like 'Pod/default/my-pod'."""
        parts = resource_str.split("/")
        if len(parts) >= 1:
            kind = parts[0].lower()
            kind_map = {
                "pod": "pod",
                "deployment": "deployment",
                "replicaset": "replicaset",
                "statefulset": "statefulset",
                "service": "service",
                "configmap": "configmap",
                "secret": "secret",
                "node": "node",
                "ingress": "ingress",
                "persistentvolumeclaim": "pvc",
                "pvc": "pvc",
                "namespace": "namespace",
                "daemonset": "daemonset",
                "job": "job",
                "cronjob": "cronjob",
            }
            return kind_map.get(kind, kind)
        return "unknown"

    def _resource_name(resource_str: str) -> str:
        """Extract the name portion from a resource key."""
        parts = resource_str.split("/")
        if len(parts) >= 3:
            return parts[2]
        if len(parts) == 2:
            return parts[1]
        return resource_str

    def _resource_namespace(resource_str: str) -> str:
        """Extract the namespace from a resource key."""
        parts = resource_str.split("/")
        if len(parts) >= 3:
            return parts[1]
        return ""

    def _ensure_node(
        resource_id: str,
        status: str = "unknown",
        severity: str | None = None,
        symptom: str | None = None,
    ) -> None:
        """Add a node if not already present, or upgrade severity."""
        if resource_id not in nodes:
            nodes[resource_id] = {
                "id": resource_id,
                "type": _resource_type(resource_id),
                "name": _resource_name(resource_id),
                "namespace": _resource_namespace(resource_id),
                "status": status,
                "severity": severity,
                "symptom": symptom,
            }
        elif severity is not None:
            existing = nodes[resource_id]
            severity_rank = {"critical": 3, "warning": 2, "info": 1}
            old_rank = severity_rank.get(existing.get("severity", ""), 0)
            new_rank = severity_rank.get(severity, 0)
            if new_rank > old_rank:
                existing["severity"] = severity
                existing["status"] = status
                existing["symptom"] = symptom

    def _add_edge(source: str, target: str, relationship: str) -> None:
        """Add an edge if not already present."""
        key = (source, target, relationship)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({
                "source": source,
                "target": target,
                "relationship": relationship,
            })

    # Build nodes from findings
    for finding in analysis.findings:
        rid = _canonical_id(finding.resource)
        status = "critical" if finding.severity == "critical" else (
            "warning" if finding.severity == "warning" else "info"
        )
        _ensure_node(
            rid,
            status=status,
            severity=finding.severity,
            symptom=finding.symptom,
        )

        # Add affected resources as nodes too
        affected = getattr(finding, "affected_resources", None)
        if affected:
            for res in affected:
                cres = _canonical_id(res)
                _ensure_node(cres, status="warning", severity="warning")
                _add_edge(rid, cres, "cascades_to")

    # Build nodes and edges from causal chains
    for chain in analysis.causal_chains:
        # Symptom resource
        csym = _canonical_id(chain.symptom_resource)
        _ensure_node(
            csym,
            status="critical",
            severity="critical",
            symptom=chain.symptom,
        )

        # Walk chain steps: each consecutive pair forms an edge
        prev_resource: str | None = None
        prev_observation: str = ""
        for step in chain.steps:
            cstep = _canonical_id(step.resource)
            _ensure_node(cstep, status="warning", severity="warning",
                         symptom=step.observation)
            if prev_resource is not None and prev_resource != cstep:
                # Use observation as edge label (truncated)
                label = step.observation[:50] if step.observation else "cascades_to"
                _add_edge(prev_resource, cstep, label)
            prev_resource = cstep
            prev_observation = step.observation

        # Related resources — filter out generic K8s plumbing
        noise_patterns = {"kube-root-ca.crt", "kube-proxy", "coredns", "kube-dns"}
        for related in chain.related_resources:
            crel = _canonical_id(related)
            # Skip noisy auto-mounted resources
            rname = _resource_name(related).lower()
            if any(noise in rname for noise in noise_patterns):
                continue
            _ensure_node(crel, status="unknown")
            _add_edge(csym, crel, "references")

    # Mark healthy nodes (nodes without severity)
    for node in nodes.values():
        if node["severity"] is None:
            node["status"] = "healthy"

    # Serialize causal chains
    serialized_chains = [
        chain.model_dump(mode="json") for chain in analysis.causal_chains
    ]

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "causal_chains": serialized_chains,
    }


@router.get("/graph")
async def get_dependency_graph(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return the resource dependency graph for visualization.

    Builds a graph of nodes (K8s resources) and edges (dependency relationships)
    from the analysis findings and causal chains. Used by the frontend to render
    the dependency graph page.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        Dict with nodes, edges, and causal_chains.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None
    return _build_graph_data(session.analysis)


def _collect_troubleshootai_issues(triage: TriageResult) -> list[dict[str, Any]]:
    """Collect all unique issues from TroubleShootAI triage scanners.

    Iterates every scanner category in the TriageResult and normalizes
    each issue into a flat dict with type, resource, severity, and description.

    Args:
        triage: The completed TriageResult from all scanners.

    Returns:
        List of dicts, each representing one unique issue found.
    """
    issues: list[dict[str, Any]] = []

    # Critical pods
    for p in triage.critical_pods:
        issues.append({
            "type": "pod_issue",
            "resource": f"{p.namespace}/{p.pod_name}",
            "severity": "critical",
            "description": f"{p.issue_type}: {p.message}" if p.message else p.issue_type,
        })

    # Warning pods
    for p in triage.warning_pods:
        issues.append({
            "type": "pod_issue",
            "resource": f"{p.namespace}/{p.pod_name}",
            "severity": "warning",
            "description": f"{p.issue_type}: {p.message}" if p.message else p.issue_type,
        })

    # Node issues
    for n in triage.node_issues:
        issues.append({
            "type": "node_issue",
            "resource": n.node_name,
            "severity": "warning",
            "description": f"{n.condition}: {n.message}" if n.message else n.condition,
        })

    # Deployment issues
    for d in triage.deployment_issues:
        issues.append({
            "type": "deployment_issue",
            "resource": f"{d.namespace}/{d.name}",
            "severity": "warning",
            "description": d.issue,
        })

    # Config issues
    for c in triage.config_issues:
        issues.append({
            "type": "config_issue",
            "resource": f"{c.namespace}/{c.resource_name}",
            "severity": "warning",
            "description": f"{c.issue} {c.resource_type} referenced by {c.referenced_by}",
        })

    # Drift issues
    for dr in triage.drift_issues:
        issues.append({
            "type": "drift_issue",
            "resource": f"{dr.namespace}/{dr.name}",
            "severity": "warning",
            "description": dr.description,
        })

    # Silence signals
    for s in triage.silence_signals:
        issues.append({
            "type": "silence_signal",
            "resource": f"{s.namespace}/{s.pod_name}",
            "severity": s.severity,
            "description": f"{s.signal_type}: {s.note}" if s.note else s.signal_type,
        })

    # Warning events
    for e in triage.warning_events:
        issues.append({
            "type": "event",
            "resource": f"{e.namespace}/{e.involved_object_name}",
            "severity": "warning",
            "description": f"{e.reason}: {e.message}",
        })

    # Probe issues
    for pr in triage.probe_issues:
        issues.append({
            "type": "probe_issue",
            "resource": f"{pr.namespace}/{pr.pod_name}",
            "severity": pr.severity,
            "description": pr.message,
        })

    # Resource issues
    for r in triage.resource_issues:
        issues.append({
            "type": "resource_issue",
            "resource": f"{r.namespace}/{r.pod_name}",
            "severity": r.severity,
            "description": r.message,
        })

    # Ingress issues
    for ing in triage.ingress_issues:
        issues.append({
            "type": "ingress_issue",
            "resource": f"{ing.namespace}/{ing.ingress_name}",
            "severity": ing.severity,
            "description": ing.message,
        })

    # Storage issues
    for st in triage.storage_issues:
        issues.append({
            "type": "storage_issue",
            "resource": f"{st.namespace}/{st.resource_name}",
            "severity": st.severity,
            "description": st.message,
        })

    # RBAC issues
    for rb in triage.rbac_issues:
        issues.append({
            "type": "rbac_issue",
            "resource": f"{rb.namespace}/{rb.resource_type}",
            "severity": rb.severity,
            "description": rb.error_message,
        })

    # Quota issues
    for q in triage.quota_issues:
        issues.append({
            "type": "quota_issue",
            "resource": f"{q.namespace}/{q.resource_name}",
            "severity": q.severity,
            "description": q.message,
        })

    # Network policy issues
    for np_issue in triage.network_policy_issues:
        issues.append({
            "type": "network_policy_issue",
            "resource": f"{np_issue.namespace}/{np_issue.policy_name}",
            "severity": np_issue.severity,
            "description": np_issue.message,
        })

    # DNS issues
    for dns in triage.dns_issues:
        issues.append({
            "type": "dns_issue",
            "resource": f"{dns.namespace}/{dns.resource_name}",
            "severity": dns.severity,
            "description": dns.message,
        })

    # TLS issues
    for tls in triage.tls_issues:
        issues.append({
            "type": "tls_issue",
            "resource": f"{tls.namespace}/{tls.resource_name}",
            "severity": tls.severity,
            "description": tls.message,
        })

    # Scheduling issues
    for sched in triage.scheduling_issues:
        issues.append({
            "type": "scheduling_issue",
            "resource": f"{sched.namespace}/{sched.pod_name}",
            "severity": sched.severity,
            "description": sched.message,
        })

    # Crash contexts
    for cc in triage.crash_contexts:
        issues.append({
            "type": "crash_context",
            "resource": f"{cc.namespace}/{cc.pod_name}",
            "severity": cc.severity,
            "description": cc.message,
        })

    # Event escalations
    for esc in triage.event_escalations:
        issues.append({
            "type": "event_escalation",
            "resource": f"{esc.namespace}/{esc.involved_object_name}",
            "severity": esc.severity,
            "description": esc.message,
        })

    return issues


@router.get("/coverage-comparison")
async def get_coverage_comparison(
    bundle_id: str,
    session: BundleSession = Depends(get_session),
) -> Any:
    """Return a side-by-side comparison of Troubleshoot.sh vs TroubleShootAI findings.

    Builds the comparison from:
    - analysis.triage.troubleshoot_analysis (what Troubleshoot.sh found)
    - analysis.triage (all issues TroubleShootAI scanners found)

    The 'missed_by_troubleshoot' list contains every TroubleShootAI issue
    that does not have a corresponding Troubleshoot.sh result covering
    the same analyzer category.

    Args:
        bundle_id: The bundle identifier from the URL path.
        session: The bundle session.

    Returns:
        Dict with troubleshoot_found, troubleshootai_found,
        missed_by_troubleshoot, and counts.
    """
    await _ensure_analysis(bundle_id, session)
    assert session.analysis is not None

    triage = session.analysis.triage

    # 1. Collect what Troubleshoot.sh found (non-passing results)
    ts_analysis = triage.troubleshoot_analysis
    troubleshoot_found: list[dict[str, Any]] = []
    if ts_analysis and ts_analysis.has_results:
        for r in ts_analysis.results:
            if r.is_pass:
                continue
            severity = "critical" if r.is_fail else "warning" if r.is_warn else "info"
            troubleshoot_found.append({
                "name": r.name,
                "analyzer_type": r.analyzer_type,
                "severity": severity,
                "title": r.title,
                "detail": r.message,
            })

    # 2. Collect all TroubleShootAI issues
    troubleshootai_found = _collect_troubleshootai_issues(triage)

    # 3. Determine which TroubleShootAI issues Troubleshoot.sh missed.
    # Build a set of analyzer categories that Troubleshoot.sh covered
    # (both passing and non-passing -- a PASS means it checked but found nothing).
    ts_covered_categories: set[str] = set()
    if ts_analysis and ts_analysis.has_results:
        for r in ts_analysis.results:
            ts_covered_categories.add(r.analyzer_type)

    # Map TroubleShootAI issue types to troubleshoot.sh analyzer types
    tsai_to_ts_map: dict[str, set[str]] = {
        "pod_issue": {"clusterPodStatuses", "clusterContainerStatuses"},
        "node_issue": {"nodeResources"},
        "deployment_issue": {"deploymentStatus", "statefulsetStatus"},
        "storage_issue": {"storageClass"},
        "ingress_issue": {"ingress"},
        "event": {"event"},
    }

    missed_by_troubleshoot: list[dict[str, Any]] = []
    for issue in troubleshootai_found:
        issue_type = issue["type"]
        ts_analyzer_types = tsai_to_ts_map.get(issue_type, set())

        # If there are no overlapping analyzer types, Troubleshoot.sh
        # simply does not have a scanner for this category -- it is missed.
        if not ts_analyzer_types or not ts_analyzer_types.intersection(ts_covered_categories):
            missed_by_troubleshoot.append(issue)
        else:
            # Troubleshoot.sh covers this category. Check if it actually
            # found the specific issue. If not in troubleshoot_found, it missed it.
            resource_lower = issue["resource"].lower()
            found_match = False
            for tf in troubleshoot_found:
                msg_lower = tf.get("detail", "").lower()
                name_lower = tf.get("name", "").lower()
                if (
                    resource_lower in msg_lower
                    or resource_lower in name_lower
                    or any(
                        word in msg_lower
                        for word in resource_lower.split("/")
                        if len(word) > 3
                    )
                ):
                    found_match = True
                    break
            if not found_match:
                missed_by_troubleshoot.append(issue)

    return {
        "troubleshoot_found": troubleshoot_found,
        "troubleshootai_found": troubleshootai_found,
        "missed_by_troubleshoot": missed_by_troubleshoot,
        "troubleshoot_count": len(troubleshoot_found),
        "troubleshootai_count": len(troubleshootai_found),
        "gap_count": len(missed_by_troubleshoot),
    }
