"""Pass 5: Verdict assembly.

Builds final EvaluationVerdict objects with recalculated confidence scores
based on evidence verification, chain consistency, and signal corroboration.
"""

from __future__ import annotations

from typing import Any

from bundle_analyzer.models import EvaluationVerdict, Finding


def assemble_verdicts(
    verdicts: list[dict[str, Any]],
) -> list[EvaluationVerdict]:
    """Build final EvaluationVerdict objects with recalculated confidence.

    Args:
        verdicts: Per-finding accumulator dicts from all passes.

    Returns:
        List of assembled EvaluationVerdict objects.
    """
    results: list[EvaluationVerdict] = []

    for v in verdicts:
        finding: Finding = v["finding"]

        # Recalculate confidence
        evidence_factor = v["evidence_score"]
        chain_factor = v["chain_factor"]
        n_signals = len(v["signals"])
        corroboration_factor = min(1.0, 0.5 + 0.1 * n_signals)
        n_contradictions = len(v["contradicting"])
        contradiction_penalty = 0.15 * min(n_contradictions, 3)

        recalculated = (
            evidence_factor * 0.4
            + chain_factor * 0.3
            + corroboration_factor * 0.3
        ) - contradiction_penalty
        confidence_score = max(0.0, min(1.0, recalculated))

        # Determine correctness
        correctness = v["chain_match"] or (
            "Correct" if evidence_factor >= 0.7 and n_contradictions == 0
            else "Partially Correct" if evidence_factor >= 0.3
            else "Inconclusive"
        )

        # Build notes
        notes_parts = []
        if v["evidence_score"] < 1.0:
            pct = round(v["evidence_score"] * 100)
            notes_parts.append(f"{pct}% of evidence citations verified")
        if n_signals > 0:
            notes_parts.append(f"{n_signals} correlated triage signals found")
        if v["chain_match"]:
            notes_parts.append(f"ChainWalker assessment: {v['chain_match']}")

        results.append(EvaluationVerdict(
            failure_point=finding.symptom or finding.resource or "Unknown",
            resource=finding.resource or "",
            app_claimed_cause=finding.root_cause or "",
            true_likely_cause=(
                v["stronger_alternative"] or finding.root_cause or ""
            ),
            correctness=correctness,
            dependency_chain=v["dep_chain"],
            correlated_signals=v["signals"],
            supporting_evidence=v["supporting"],
            contradicting_evidence=v["contradicting"],
            missed=v["missed"],
            misinterpreted=[],
            stronger_alternative=v["stronger_alternative"],
            alternative_hypotheses=[],
            blast_radius=[],
            remediation_assessment=(
                "Fix suggested by pipeline appears valid"
                if correctness == "Correct"
                else "Review suggested fix — analysis may be incomplete"
            ),
            confidence_score=confidence_score,
            notes=". ".join(notes_parts) if notes_parts else "",
        ))

    return results
