"""Uncertainty report generator -- 'what I can't tell you' analysis.

Explicitly identifies gaps in the bundle data and analysis,
helping engineers understand the limits of the automated findings.
"""

from __future__ import annotations

from loguru import logger

from bundle_analyzer.models import (
    AnalystOutput,
    TriageResult,
    UncertaintyGap,
)


class UncertaintyReporter:
    """Collects and categorizes gaps from all analysts and engines.

    Produces a prioritized list of UncertaintyGap objects that explicitly
    describe what the analysis does NOT know, what additional data to collect,
    and how impactful each gap might be.
    """

    def collect(
        self,
        analyst_outputs: list[AnalystOutput] | None = None,
        triage: TriageResult | None = None,
        synthesis: dict | None = None,
        has_api_key: bool = True,
    ) -> list[UncertaintyGap]:
        """Collect uncertainty gaps from all analysis stages.

        Args:
            analyst_outputs: Individual analyst outputs with uncertainty lists.
            triage: Triage data for RBAC/silence signals.
            synthesis: Synthesis result with uncertainty_report.
            has_api_key: Whether the AI API key was available.

        Returns:
            Sorted list of UncertaintyGap objects (HIGH impact first).
        """
        gaps: list[UncertaintyGap] = []

        if not has_api_key:
            gaps.append(UncertaintyGap(
                question="AI analysis was not performed",
                reason="No AI provider key set -- only deterministic triage was run",
                to_investigate="Set OPEN_ROUTER_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY to enable AI analysis",
                impact="HIGH",
            ))

        # Analyst-reported gaps
        if analyst_outputs:
            gaps.extend(self._from_analysts(analyst_outputs))

        # Synthesis-reported gaps
        if synthesis:
            gaps.extend(self._from_synthesis(synthesis))

        # Data collection gaps from triage
        if triage:
            gaps.extend(self._from_triage(triage))

        # Deduplicate by question text
        seen: set[str] = set()
        deduped: list[UncertaintyGap] = []
        for gap in gaps:
            key = gap.question.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(gap)

        # Sort by impact: HIGH first, then MEDIUM, then LOW
        impact_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        deduped.sort(key=lambda g: impact_order.get(g.impact, 99))

        logger.info(
            "Uncertainty report: {} gaps ({} HIGH, {} MEDIUM, {} LOW)",
            len(deduped),
            sum(1 for g in deduped if g.impact == "HIGH"),
            sum(1 for g in deduped if g.impact == "MEDIUM"),
            sum(1 for g in deduped if g.impact == "LOW"),
        )
        return deduped

    def _from_analysts(
        self,
        analyst_outputs: list[AnalystOutput],
    ) -> list[UncertaintyGap]:
        """Extract gaps from individual analyst uncertainty lists.

        Args:
            analyst_outputs: Structured outputs from each analyst.

        Returns:
            List of UncertaintyGap objects.
        """
        gaps: list[UncertaintyGap] = []
        for output in analyst_outputs:
            for gap_text in output.uncertainty:
                gaps.append(UncertaintyGap(
                    question=gap_text,
                    reason=f"Reported by {output.analyst} analyst",
                    impact="MEDIUM",
                ))
        return gaps

    def _from_synthesis(
        self,
        synthesis: dict,
    ) -> list[UncertaintyGap]:
        """Extract gaps from the synthesis uncertainty report.

        Args:
            synthesis: Synthesis result dictionary.

        Returns:
            List of UncertaintyGap objects.
        """
        gaps: list[UncertaintyGap] = []
        uncertainty_report = synthesis.get("uncertainty_report", {})

        for item in uncertainty_report.get("what_i_cant_determine", []):
            gaps.append(UncertaintyGap(
                question=item,
                reason="Identified during synthesis cross-correlation",
                impact="HIGH",
            ))

        for item in uncertainty_report.get("what_i_suspect", []):
            gaps.append(UncertaintyGap(
                question=item,
                reason="Suspected but not confirmed during synthesis",
                impact="MEDIUM",
            ))

        return gaps

    def _from_triage(
        self,
        triage: TriageResult,
    ) -> list[UncertaintyGap]:
        """Extract gaps from triage RBAC errors and silence signals.

        Args:
            triage: Triage scan results.

        Returns:
            List of UncertaintyGap objects.
        """
        gaps: list[UncertaintyGap] = []

        # RBAC collection errors indicate missing data
        for rbac_error in triage.rbac_errors[:5]:
            gaps.append(UncertaintyGap(
                question="Data may be incomplete due to collection error",
                reason=rbac_error[:200],
                collect_command="kubectl auth can-i --list",
                impact="HIGH",
            ))

        # Silence signals indicate missing or absent data
        for signal in triage.silence_signals:
            gaps.append(UncertaintyGap(
                question=f"Missing data for {signal.namespace}/{signal.pod_name}",
                reason=(
                    f"{signal.signal_type}: {signal.note}"
                    if signal.note
                    else signal.signal_type
                ),
                collect_command=(
                    f"kubectl logs {signal.pod_name} -n {signal.namespace} --previous"
                ),
                impact="MEDIUM" if signal.severity == "warning" else "HIGH",
            ))

        # Check for common data gaps
        if not triage.warning_events:
            gaps.append(UncertaintyGap(
                question="No Kubernetes events found in bundle",
                reason="Events provide critical timing information; bundle may not have collected them",
                collect_command="kubectl get events -A --sort-by=.lastTimestamp",
                impact="MEDIUM",
            ))

        return gaps
