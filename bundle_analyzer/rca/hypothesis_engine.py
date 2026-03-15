"""Hypothesis engine for root cause analysis of Kubernetes support bundles.

Takes triage findings, clusters related symptoms, applies deterministic rules,
scores candidate hypotheses by evidence strength, resolves conflicts, and
returns a ranked list of root cause hypotheses.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from bundle_analyzer.models.troubleshoot import TriageResult
from bundle_analyzer.rca.rules import RCA_RULES, RCARule


class Hypothesis(BaseModel):
    """A candidate root cause hypothesis with evidence scoring.

    Each hypothesis represents a potential root cause for one or more
    observed symptoms in the support bundle. Hypotheses are ranked by
    a composite score derived from evidence count and average confidence.
    """

    id: str
    title: str
    description: str
    category: str  # "resource_exhaustion", "config_error", "image_error", "dependency_failure", "scheduling", "dns", "tls", "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)  # overwritten by scoring
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    is_validated: bool = False  # True if deterministic rule confirmed it


class HypothesisEngine:
    """Generates, scores, and ranks root cause hypotheses from triage data.

    The engine operates in three phases:
    1. Rule evaluation — each RCA rule is tested against the triage result
    2. Scoring — hypotheses are scored by evidence count * avg confidence
    3. Conflict resolution — if two hypotheses explain the same symptom,
       the one with more evidence wins

    Usage::

        engine = HypothesisEngine()
        hypotheses = await engine.analyze(triage_result)
    """

    def __init__(self, rules: list[RCARule] | None = None) -> None:
        """Initialize the engine with an optional custom rule set.

        Args:
            rules: List of RCA rules to evaluate. Defaults to the built-in
                ``RCA_RULES`` if not provided.
        """
        self._rules = rules if rules is not None else RCA_RULES

    async def analyze(
        self, triage: TriageResult, resource_graph: Any | None = None
    ) -> list[Hypothesis]:
        """Generate and rank hypotheses from triage findings.

        Args:
            triage: Aggregated output from all triage scanners.
            resource_graph: Optional ResourceGraph for dependency cascade analysis.

        Returns:
            A list of Hypothesis objects sorted by score (highest first).
        """
        raw_hypotheses = self._evaluate_rules(triage)

        # Check for dependency cascades if graph is available
        if resource_graph is not None:
            cascade_hypotheses = self._check_cascades(resource_graph, triage)
            raw_hypotheses.extend(cascade_hypotheses)

        if not raw_hypotheses:
            logger.info("No RCA rules matched — no hypotheses generated")
            return []

        with_contradictions = self._detect_contradictions(raw_hypotheses, triage)
        scored = self._score_hypotheses(with_contradictions, triage)
        resolved = self._resolve_conflicts(scored)
        ranked = sorted(resolved, key=lambda h: h.confidence, reverse=True)

        logger.info(
            "RCA engine produced {} hypotheses from {} rules",
            len(ranked),
            len(self._rules),
        )
        return ranked

    def _evaluate_rules(self, triage: TriageResult) -> list[Hypothesis]:
        """Run all rules against the triage result and collect hypotheses.

        Args:
            triage: The triage result to evaluate.

        Returns:
            A list of unscored Hypothesis objects from all matching rules.
        """
        hypotheses: list[Hypothesis] = []

        for rule in self._rules:
            try:
                match_groups = rule.match(triage)
                if not match_groups:
                    continue

                hyp_dict = rule.hypothesis_template(match_groups)
                hypothesis = Hypothesis(**hyp_dict)
                hypotheses.append(hypothesis)
                logger.debug(
                    "Rule '{}' fired — hypothesis: {}",
                    rule.name,
                    hypothesis.title,
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Rule '{}' failed during evaluation: {}", rule.name, exc
                )

        return hypotheses

    def _detect_contradictions(
        self, hypotheses: list[Hypothesis], triage: TriageResult
    ) -> list[Hypothesis]:
        """Add contradicting evidence to hypotheses where applicable.

        Checks for logical contradictions between hypothesis claims and
        actual cluster state, such as OOM hypotheses when no node reports
        memory pressure, or dependency failure hypotheses when all
        deployments are healthy.

        Args:
            hypotheses: List of hypotheses to check for contradictions.
            triage: The triage result providing cluster state context.

        Returns:
            The same hypotheses with contradicting_evidence updated.
        """
        # Build quick lookups
        {n.node_name for n in triage.node_issues}
        has_memory_pressure = any(n.condition == "MemoryPressure" for n in triage.node_issues)
        all_deps_healthy = all(d.ready_replicas >= d.desired_replicas for d in triage.deployment_issues) if triage.deployment_issues else True

        for hyp in hypotheses:
            # OOM but no memory pressure on any node
            if hyp.category == "resource_exhaustion" and "OOM" in hyp.title:
                if not has_memory_pressure and triage.node_issues:
                    hyp.contradicting_evidence.append(
                        "No node reports MemoryPressure — OOM may be container-level, not node-level"
                    )

            # Dependency failure but all deployments healthy
            if hyp.category == "dependency_failure":
                if all_deps_healthy and not triage.deployment_issues:
                    hyp.contradicting_evidence.append(
                        "No deployment issues detected — dependency may be external to cluster"
                    )

        return hypotheses

    def _score_hypotheses(
        self, hypotheses: list[Hypothesis], triage: TriageResult
    ) -> list[Hypothesis]:
        """Score each hypothesis by evidence count * average confidence.

        The scoring formula:
            score = evidence_count * avg_finding_confidence

        The score is normalized to [0.0, 1.0] and written back to the
        hypothesis ``confidence`` field.

        Args:
            hypotheses: List of hypotheses to score.
            triage: The triage result (used to look up finding confidences).

        Returns:
            The same hypotheses with updated confidence scores.
        """
        if not hypotheses:
            return hypotheses

        # Compute raw scores
        raw_scores: list[float] = []
        for hyp in hypotheses:
            evidence_count = len(hyp.supporting_evidence)
            # Look up average confidence of affected resources from triage
            avg_conf = self._avg_confidence_for_resources(
                hyp.affected_resources, triage
            )
            raw_score = evidence_count * avg_conf
            raw_scores.append(raw_score)

        # Normalize to [0.0, 1.0]
        max_score = max(raw_scores) if raw_scores else 1.0
        if max_score == 0:
            max_score = 1.0

        for hyp, raw in zip(hypotheses, raw_scores):
            hyp.confidence = round(min(raw / max_score, 1.0), 3)

        return hypotheses

    def _avg_confidence_for_resources(
        self, resources: list[str], triage: TriageResult
    ) -> float:
        """Compute average confidence of triage findings for given resources.

        Args:
            resources: List of resource identifiers (e.g. "namespace/pod").
            triage: The triage result to search.

        Returns:
            Average confidence value, or 0.8 as a default if no matches found.
        """
        confidences: list[float] = []

        # Build a lookup of resource -> confidence from all pod issues
        all_pods = list(triage.critical_pods) + list(triage.warning_pods)
        for pod in all_pods:
            resource_key = f"{pod.namespace}/{pod.pod_name}"
            if resource_key in resources:
                confidences.append(pod.confidence)

        # Check node issues
        for node in triage.node_issues:
            if node.node_name in resources:
                confidences.append(node.confidence)

        # Check deployment issues
        for dep in triage.deployment_issues:
            dep_key = f"{dep.namespace}/{dep.name}"
            if dep_key in resources:
                confidences.append(dep.confidence)

        if not confidences:
            return 0.8  # reasonable default when we can't look up directly

        return sum(confidences) / len(confidences)

    def _check_cascades(self, resource_graph: Any, triage: TriageResult) -> list[Hypothesis]:
        """Generate hypotheses from dependency cascade analysis.

        Collects failing resources from triage findings and uses the resource
        graph to detect multi-hop dependency cascades that explain how a root
        failure propagates through the cluster.

        Args:
            resource_graph: A ResourceGraph instance with find_dependency_cascades.
            triage: The triage result providing failing resource context.

        Returns:
            List of Hypothesis objects for significant cascades (depth >= 2).
        """
        # Collect failing resources from triage
        failing: set[str] = set()
        for p in list(triage.critical_pods) + list(triage.warning_pods):
            failing.add(f"{p.namespace}/{p.pod_name}")
        for d in triage.deployment_issues:
            if d.ready_replicas < d.desired_replicas:
                failing.add(f"{d.namespace}/{d.name}")

        if not failing or not hasattr(resource_graph, "find_dependency_cascades"):
            return []

        cascades = resource_graph.find_dependency_cascades(failing)
        hypotheses: list[Hypothesis] = []

        for cascade in cascades:
            if cascade["depth"] < 2:
                continue  # Only report multi-hop cascades
            hypotheses.append(Hypothesis(
                id=f"cascade-{cascade['root_cause'][:12]}",
                title=f"Cascading Failure from {cascade['root_cause']}",
                description=(
                    f"A failure in {cascade['root_cause']} is cascading through "
                    f"{cascade['depth']} dependent resources: {cascade['chain']}"
                ),
                category="dependency_failure",
                confidence=0.7,
                supporting_evidence=[f"Dependency chain: {cascade['chain']}"],
                affected_resources=[cascade['root_cause']] + cascade['affected'],
                suggested_fixes=[
                    f"Investigate root cause: {cascade['root_cause']}",
                    "Fix the root resource first — dependents may recover automatically",
                ],
                is_validated=False,
            ))

        return hypotheses

    def _resolve_conflicts(
        self, hypotheses: list[Hypothesis]
    ) -> list[Hypothesis]:
        """Resolve conflicts when multiple hypotheses explain the same symptom.

        If two hypotheses share affected resources (i.e., they explain the
        same symptom), the hypothesis with more supporting evidence is kept
        and the weaker one is demoted (confidence halved).

        Args:
            hypotheses: Scored hypotheses to check for conflicts.

        Returns:
            The hypotheses list with conflicts resolved via demotion.
        """
        if len(hypotheses) <= 1:
            return hypotheses

        # Build resource -> hypothesis index
        resource_to_hyps: dict[str, list[int]] = defaultdict(list)
        for idx, hyp in enumerate(hypotheses):
            for res in hyp.affected_resources:
                resource_to_hyps[res].append(idx)

        # Find conflicts: resources claimed by multiple hypotheses
        demoted: set[int] = set()
        for resource, hyp_indices in resource_to_hyps.items():
            if len(hyp_indices) <= 1:
                continue

            # Among conflicting hypotheses, keep the one with most evidence
            best_idx = max(
                hyp_indices,
                key=lambda i: len(hypotheses[i].supporting_evidence),
            )
            for idx in hyp_indices:
                if idx != best_idx and idx not in demoted:
                    demoted.add(idx)
                    hypotheses[idx].confidence = round(
                        hypotheses[idx].confidence * 0.5, 3
                    )
                    logger.debug(
                        "Demoted hypothesis '{}' — conflicts with '{}' on resource '{}'",
                        hypotheses[idx].title,
                        hypotheses[best_idx].title,
                        resource,
                    )

        return hypotheses
