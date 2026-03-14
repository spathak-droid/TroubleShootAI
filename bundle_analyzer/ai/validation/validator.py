"""Deterministic validator — public facade.

Orchestrates five validation passes to verify AI analysis against hard evidence.
No API calls. Fast, free, and trustworthy.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalysisResult, EvaluationResult

from .pass_consistency import check_chain_consistency
from .pass_coverage import analyze_coverage
from .pass_cross_ref import cross_reference_signals
from .pass_evidence import validate_evidence
from .pass_verdict import assemble_verdicts
from .scoring import avg_confidence, compute_overall, detect_cross_cutting


class DeterministicValidator:
    """Validates AI analysis results against hard bundle evidence.

    No LLM calls — purely deterministic checks that produce
    EvaluationResult compatible with the existing frontend.
    """

    def validate(
        self,
        analysis: AnalysisResult,
        index: BundleIndex,
    ) -> EvaluationResult:
        """Run all five validation passes and assemble the result.

        Args:
            analysis: The completed analysis from the main pipeline.
            index: The bundle index for reading raw files.

        Returns:
            EvaluationResult with deterministic verdicts.
        """
        start = time.monotonic()

        # Build per-finding verdict accumulators
        verdicts: list[dict[str, Any]] = []
        for finding in analysis.findings:
            verdicts.append({
                "finding": finding,
                "supporting": [],
                "contradicting": [],
                "missed": [],
                "dep_chain": [],
                "signals": [],
                "chain_match": None,
                "chain_factor": 0.5,
                "evidence_score": 0.0,
                "stronger_alternative": None,
            })

        # Pass 1: Evidence validation
        validate_evidence(verdicts, index)

        # Pass 2: Coverage analysis
        missed_points = analyze_coverage(analysis)

        # Pass 3: Chain consistency
        check_chain_consistency(verdicts, analysis.causal_chains)

        # Pass 4: Signal cross-referencing
        cross_reference_signals(verdicts, analysis)

        # Pass 5: Confidence recalculation + assemble verdicts
        eval_verdicts = assemble_verdicts(verdicts)

        # Compute overall
        elapsed = time.monotonic() - start
        overall = compute_overall(eval_verdicts, missed_points)

        # Cross-cutting concerns
        cross_cutting = detect_cross_cutting(verdicts, analysis)

        # Summary
        n_correct = sum(1 for v in eval_verdicts if v.correctness == "Correct")
        n_partial = sum(1 for v in eval_verdicts if v.correctness == "Partially Correct")
        n_incorrect = sum(1 for v in eval_verdicts if v.correctness == "Incorrect")
        summary = (
            f"Validated {len(eval_verdicts)} findings: "
            f"{n_correct} correct, {n_partial} partially correct, {n_incorrect} incorrect. "
            f"{len(missed_points)} critical signals not covered by any finding."
        )

        result = EvaluationResult(
            verdicts=eval_verdicts,
            overall_correctness=overall,
            overall_confidence=avg_confidence(eval_verdicts),
            missed_failure_points=missed_points,
            cross_cutting_concerns=cross_cutting,
            evaluation_summary=summary,
            evaluation_duration_seconds=elapsed,
        )

        logger.info(
            "Deterministic validation complete: overall={}, confidence={:.2f}, "
            "{} verdicts, {} missed, duration={:.3f}s",
            result.overall_correctness,
            result.overall_confidence,
            len(result.verdicts),
            len(result.missed_failure_points),
            elapsed,
        )
        return result
