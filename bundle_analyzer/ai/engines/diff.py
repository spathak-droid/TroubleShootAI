"""Multi-bundle diff engine -- before/after comparison analysis.

Compares two support bundles to identify what changed between them,
useful for debugging regressions or verifying fixes.
"""

from __future__ import annotations

from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field

from bundle_analyzer.bundle.extractor import BundleExtractor
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import PodIssue, TriageResult
from bundle_analyzer.triage.engine import TriageEngine


class DiffFinding(BaseModel):
    """A single finding from bundle comparison."""

    status: Literal["new", "resolved", "worsened", "unchanged"]
    category: str
    resource: str
    description: str
    before_detail: str = ""
    after_detail: str = ""


class DiffResult(BaseModel):
    """Complete diff output comparing two bundles."""

    summary: str
    new_findings: list[DiffFinding] = Field(default_factory=list)
    resolved_findings: list[DiffFinding] = Field(default_factory=list)
    worsened_findings: list[DiffFinding] = Field(default_factory=list)
    unchanged_findings: list[DiffFinding] = Field(default_factory=list)
    resource_delta: dict[str, Any] = Field(default_factory=dict)


class DiffEngine:
    """Compares two support bundles by running triage on each and diffing results.

    Identifies new findings, resolved findings, and worsened conditions
    between a 'before' and 'after' bundle from the same cluster.
    """

    async def compare(
        self,
        before_index: BundleIndex,
        after_index: BundleIndex,
        before_triage: TriageResult,
        after_triage: TriageResult,
    ) -> DiffResult:
        """Compare triage results from two bundles.

        Args:
            before_index: Bundle index for the 'before' bundle.
            after_index: Bundle index for the 'after' bundle.
            before_triage: Triage results from the 'before' bundle.
            after_triage: Triage results from the 'after' bundle.

        Returns:
            DiffResult with categorized findings.
        """
        new: list[DiffFinding] = []
        resolved: list[DiffFinding] = []
        worsened: list[DiffFinding] = []
        unchanged: list[DiffFinding] = []

        # Compare pod issues
        self._compare_pods(
            before_triage.critical_pods + before_triage.warning_pods,
            after_triage.critical_pods + after_triage.warning_pods,
            new, resolved, worsened, unchanged,
        )

        # Compare node issues
        before_nodes = {ni.node_name: ni for ni in before_triage.node_issues}
        after_nodes = {ni.node_name: ni for ni in after_triage.node_issues}

        for name, issue in after_nodes.items():
            if name not in before_nodes:
                new.append(DiffFinding(
                    status="new",
                    category="node",
                    resource=name,
                    description=f"New node issue: {issue.condition}",
                    after_detail=issue.message,
                ))
            else:
                unchanged.append(DiffFinding(
                    status="unchanged",
                    category="node",
                    resource=name,
                    description=f"Node issue persists: {issue.condition}",
                    before_detail=before_nodes[name].message,
                    after_detail=issue.message,
                ))

        for name, issue in before_nodes.items():
            if name not in after_nodes:
                resolved.append(DiffFinding(
                    status="resolved",
                    category="node",
                    resource=name,
                    description=f"Node issue resolved: {issue.condition}",
                    before_detail=issue.message,
                ))

        # Compare deployment issues
        before_deploys = {
            f"{d.namespace}/{d.name}": d for d in before_triage.deployment_issues
        }
        after_deploys = {
            f"{d.namespace}/{d.name}": d for d in after_triage.deployment_issues
        }

        for key, dep in after_deploys.items():
            if key not in before_deploys:
                new.append(DiffFinding(
                    status="new",
                    category="deployment",
                    resource=key,
                    description=f"New deployment issue: {dep.issue}",
                    after_detail=dep.issue,
                ))
            else:
                old = before_deploys[key]
                if dep.ready_replicas < old.ready_replicas:
                    worsened.append(DiffFinding(
                        status="worsened",
                        category="deployment",
                        resource=key,
                        description=f"Deployment degraded: {old.ready_replicas}/{old.desired_replicas} -> {dep.ready_replicas}/{dep.desired_replicas}",
                        before_detail=old.issue,
                        after_detail=dep.issue,
                    ))

        for key, dep in before_deploys.items():
            if key not in after_deploys:
                resolved.append(DiffFinding(
                    status="resolved",
                    category="deployment",
                    resource=key,
                    description=f"Deployment issue resolved: {dep.issue}",
                    before_detail=dep.issue,
                ))

        # Compare config issues
        before_configs = {
            f"{c.namespace}/{c.resource_type}/{c.resource_name}": c
            for c in before_triage.config_issues
        }
        after_configs = {
            f"{c.namespace}/{c.resource_type}/{c.resource_name}": c
            for c in after_triage.config_issues
        }

        for key, cfg in after_configs.items():
            if key not in before_configs:
                new.append(DiffFinding(
                    status="new",
                    category="config",
                    resource=key,
                    description=f"New config issue: {cfg.issue} (referenced by {cfg.referenced_by})",
                ))
        for key, cfg in before_configs.items():
            if key not in after_configs:
                resolved.append(DiffFinding(
                    status="resolved",
                    category="config",
                    resource=key,
                    description=f"Config issue resolved: {cfg.issue}",
                ))

        # Resource delta summary
        resource_delta = {
            "namespaces_before": len(before_index.namespaces),
            "namespaces_after": len(after_index.namespaces),
            "critical_pods_before": len(before_triage.critical_pods),
            "critical_pods_after": len(after_triage.critical_pods),
            "warning_pods_before": len(before_triage.warning_pods),
            "warning_pods_after": len(after_triage.warning_pods),
            "node_issues_before": len(before_triage.node_issues),
            "node_issues_after": len(after_triage.node_issues),
        }

        # Build summary
        parts: list[str] = []
        if new:
            parts.append(f"{len(new)} new finding(s)")
        if resolved:
            parts.append(f"{len(resolved)} resolved finding(s)")
        if worsened:
            parts.append(f"{len(worsened)} worsened finding(s)")
        if unchanged:
            parts.append(f"{len(unchanged)} unchanged finding(s)")
        summary = "Bundle diff: " + ", ".join(parts) if parts else "No differences found."

        logger.info(
            "Diff complete: {} new, {} resolved, {} worsened, {} unchanged",
            len(new), len(resolved), len(worsened), len(unchanged),
        )

        return DiffResult(
            summary=summary,
            new_findings=new,
            resolved_findings=resolved,
            worsened_findings=worsened,
            unchanged_findings=unchanged,
            resource_delta=resource_delta,
        )

    def _compare_pods(
        self,
        before_pods: list[PodIssue],
        after_pods: list[PodIssue],
        new: list[DiffFinding],
        resolved: list[DiffFinding],
        worsened: list[DiffFinding],
        unchanged: list[DiffFinding],
    ) -> None:
        """Compare pod issues between bundles.

        Args:
            before_pods: Pod issues from the before bundle.
            after_pods: Pod issues from the after bundle.
            new: List to append new findings to.
            resolved: List to append resolved findings to.
            worsened: List to append worsened findings to.
            unchanged: List to append unchanged findings to.
        """
        before_map = {
            f"{p.namespace}/{p.pod_name}": p for p in before_pods
        }
        after_map = {
            f"{p.namespace}/{p.pod_name}": p for p in after_pods
        }

        for key, pod in after_map.items():
            if key not in before_map:
                new.append(DiffFinding(
                    status="new",
                    category="pod",
                    resource=key,
                    description=f"New pod issue: {pod.issue_type}",
                    after_detail=pod.message,
                ))
            else:
                old = before_map[key]
                if pod.restart_count > old.restart_count:
                    worsened.append(DiffFinding(
                        status="worsened",
                        category="pod",
                        resource=key,
                        description=f"Pod worsened: {pod.issue_type} (restarts {old.restart_count} -> {pod.restart_count})",
                        before_detail=old.message,
                        after_detail=pod.message,
                    ))
                else:
                    unchanged.append(DiffFinding(
                        status="unchanged",
                        category="pod",
                        resource=key,
                        description=f"Pod issue persists: {pod.issue_type}",
                        before_detail=old.message,
                        after_detail=pod.message,
                    ))

        for key, pod in before_map.items():
            if key not in after_map:
                resolved.append(DiffFinding(
                    status="resolved",
                    category="pod",
                    resource=key,
                    description=f"Pod issue resolved: {pod.issue_type}",
                    before_detail=pod.message,
                ))
