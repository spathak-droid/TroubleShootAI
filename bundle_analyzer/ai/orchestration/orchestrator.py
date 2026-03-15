"""AI orchestrator — coordinates all AI analysts in parallel.

Reads the triage report, builds a dynamic work tree of analysts
to dispatch, runs them concurrently, and collects results for synthesis.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.context_injector import ContextInjector
from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import (
    AnalysisResult,
    Finding,
    TriageResult,
    UncertaintyGap,
)

from bundle_analyzer.ai.orchestration.helpers import (
    build_cluster_summary,
    build_uncertainty_report,
    confidence_to_float,
    report_progress,
)
from bundle_analyzer.ai.orchestration.steps.archaeology import run_archaeology
from bundle_analyzer.ai.orchestration.steps.analysts import run_analysts_parallel
from bundle_analyzer.ai.orchestration.steps.causal import run_causal_analysis
from bundle_analyzer.ai.orchestration.steps.log_analysis import run_log_analysis
from bundle_analyzer.ai.orchestration.steps.prediction import run_prediction
from bundle_analyzer.ai.orchestration.steps.synthesis import run_synthesis
from bundle_analyzer.ai.validation.claim_validator import ClaimValidator
from bundle_analyzer.rca.hypothesis_engine import HypothesisEngine


class AnalysisOrchestrator:
    """Coordinates all AI analysts in parallel, then runs synthesis.

    Reports progress via an async callback for the TUI progress screen.
    Handles the case where no API key is set by returning triage-only results.
    """

    async def run(
        self,
        triage: TriageResult,
        index: BundleIndex,
        context_injector: ContextInjector,
        progress_callback: Optional[Callable[..., Any]] = None,
    ) -> AnalysisResult:
        """Execute the full AI analysis pipeline.

        Steps:
            1. Run archaeology engine (fast, deterministic)
            2. Run pod/node/config analysts in parallel (asyncio.gather)
            3. Run prediction engine
            4. Run silence engine
            5. Synthesis pass
            6. Build uncertainty report
            7. Return AnalysisResult

        Args:
            triage: The triage scan results from Phase 1.
            index: The bundle index for reading bundle files.
            context_injector: ISV context injector for prompt augmentation.
            progress_callback: Optional ``callback(stage, pct, message)``
                for progress reporting to the TUI.

        Returns:
            Complete :class:`AnalysisResult` combining triage and AI findings.
        """
        start_time = time.monotonic()

        # Check for any AI provider key — if missing, return triage-only results
        has_ai_key = any(os.environ.get(k) for k in (
            "OPEN_ROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"
        ))
        if not has_ai_key:
            logger.warning(
                "No AI provider key set — returning triage-only results"
            )
            await report_progress(progress_callback, "complete", 1.0, "Triage-only mode (no API key)")
            return await self._triage_only_result(triage, index, start_time)

        try:
            client = BundleAnalyzerClient()
        except RuntimeError as exc:
            logger.error("Failed to create API client: {}", exc)
            return await self._triage_only_result(triage, index, start_time)

        # Step 0.5: Hypothesis generation (deterministic, before AI)
        await report_progress(progress_callback, "hypotheses", 0.03, "Generating root-cause hypotheses...")
        hypothesis_engine = HypothesisEngine()
        hypotheses = await hypothesis_engine.analyze(triage)
        logger.info("Generated {} hypotheses from triage findings", len(hypotheses))

        # Step 1: Archaeology (deterministic timeline reconstruction)
        await report_progress(progress_callback, "archaeology", 0.05, "Reconstructing cluster timeline...")
        timeline = await self._run_archaeology(triage, index)

        # Step 1.5: Build resource graph & walk causal chains
        await report_progress(progress_callback, "causal_analysis", 0.10, "Building resource graph and tracing causal chains...")
        causal_chains = await self._run_causal_analysis(triage, index)

        # Step 2: Run analysts in parallel (only for ambiguous chains)
        await report_progress(progress_callback, "analysts", 0.15, "Running AI analysts in parallel...")
        analyst_outputs = await self._run_analysts_parallel(
            client, triage, index, context_injector
        )

        # Step 2.5: AI Log Analysis (for crash-looping pods)
        if triage.crash_contexts:
            await report_progress(progress_callback, "log_analysis", 0.45, "AI analyzing container logs...")
            log_diagnoses = await self._run_log_analysis(client, triage, index)
        else:
            log_diagnoses = []

        # Step 3: Prediction engine
        await report_progress(progress_callback, "prediction", 0.55, "Running prediction engine...")
        predictions = await self._run_prediction(triage, index)

        # Step 4: Silence engine
        await report_progress(progress_callback, "silence", 0.65, "Detecting silence signals...")
        # Silence signals are already in triage from Phase 1 scanners

        # Step 5: Synthesis pass
        await report_progress(progress_callback, "synthesis", 0.75, "Cross-correlating analyst findings...")
        synthesis = await self._run_synthesis(client, analyst_outputs, triage)

        # Step 6: Build uncertainty report
        await report_progress(progress_callback, "uncertainty", 0.90, "Building uncertainty report...")
        uncertainty_gaps = build_uncertainty_report(
            analyst_outputs, synthesis, triage
        )

        # Step 7: Assemble final result
        await report_progress(progress_callback, "complete", 1.0, "Analysis complete")
        elapsed = time.monotonic() - start_time

        # Collect all findings from analyst outputs
        all_findings: list[Finding] = []
        for output in analyst_outputs:
            all_findings.extend(output.findings)

        # Step 7.5: Validate AI claims against evidence
        if all_findings:
            try:
                claim_validator = ClaimValidator()
                validation_result = await claim_validator.validate(all_findings, index)
                all_findings = validation_result.findings
                logger.info(
                    "Claim validation: {}/{} evidence verified, {} hypotheses",
                    validation_result.total_verified,
                    validation_result.total_verified + validation_result.total_unverified,
                    validation_result.hypothesis_count,
                )
            except Exception as exc:
                logger.warning("Claim validation failed, using unvalidated findings: {}", exc)

        # Sort findings by severity (critical first)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 99))

        # Serialize hypotheses for the result
        hypotheses_dicts = [h.model_dump() for h in hypotheses]

        result = AnalysisResult(
            bundle_metadata=index.metadata,
            triage=triage,
            findings=all_findings,
            causal_chains=causal_chains,
            root_cause=synthesis.get("root_cause"),
            confidence=confidence_to_float(synthesis.get("confidence", "low")),
            timeline=timeline,
            predictions=predictions,
            uncertainty=uncertainty_gaps,
            log_diagnoses=log_diagnoses,
            preflight_report=triage.preflight_report,
            cluster_summary=build_cluster_summary(triage, index),
            analysis_duration_seconds=elapsed,
            hypotheses=hypotheses_dicts,
        )

        logger.info(
            "Analysis complete in {:.1f}s: {} findings, {} predictions, {} gaps",
            elapsed,
            len(all_findings),
            len(predictions),
            len(uncertainty_gaps),
        )
        return result

    # ------------------------------------------------------------------
    # Delegate methods — thin wrappers around module-level step functions.
    # These exist so that tests can use ``patch.object(orchestrator, "_run_*")``
    # to mock individual pipeline stages.
    # ------------------------------------------------------------------

    async def _run_archaeology(
        self, triage: TriageResult, index: BundleIndex,
    ) -> list:
        """Delegate to :func:`steps.archaeology.run_archaeology`."""
        return await run_archaeology(triage, index)

    async def _run_causal_analysis(
        self, triage: TriageResult, index: BundleIndex,
    ) -> list:
        """Delegate to :func:`steps.causal.run_causal_analysis`."""
        return await run_causal_analysis(triage, index)

    async def _run_analysts_parallel(
        self,
        client: BundleAnalyzerClient,
        triage: TriageResult,
        index: BundleIndex,
        context_injector: ContextInjector,
    ) -> list:
        """Delegate to :func:`steps.analysts.run_analysts_parallel`."""
        return await run_analysts_parallel(client, triage, index, context_injector)

    async def _run_log_analysis(
        self,
        client: BundleAnalyzerClient,
        triage: TriageResult,
        index: BundleIndex,
    ) -> list:
        """Delegate to :func:`steps.log_analysis.run_log_analysis`."""
        return await run_log_analysis(client, triage, index)

    async def _run_prediction(
        self, triage: TriageResult, index: BundleIndex,
    ) -> list:
        """Delegate to :func:`steps.prediction.run_prediction`."""
        return await run_prediction(triage, index)

    async def _run_synthesis(
        self,
        client: BundleAnalyzerClient,
        analyst_outputs: list,
        triage: TriageResult,
    ) -> dict:
        """Delegate to :func:`steps.synthesis.run_synthesis`."""
        return await run_synthesis(client, analyst_outputs, triage)

    async def _triage_only_result(
        self,
        triage: TriageResult,
        index: BundleIndex,
        start_time: float,
    ) -> AnalysisResult:
        """Build a result with only triage data (no AI analysis).

        Still runs deterministic engines (archaeology, prediction, hypotheses)
        since they don't require API keys.

        Args:
            triage: The triage scan results.
            index: The bundle index with metadata.
            start_time: Monotonic start time for duration calculation.

        Returns:
            AnalysisResult with empty AI fields but populated timeline/predictions.
        """
        # Run deterministic engines even without AI key
        timeline = await self._run_archaeology(triage, index)
        predictions = await self._run_prediction(triage, index)

        # Generate hypotheses even without AI
        try:
            hypothesis_engine = HypothesisEngine()
            hypotheses = await hypothesis_engine.analyze(triage)
            hypotheses_dicts = [h.model_dump() for h in hypotheses]
        except Exception as exc:
            logger.warning("Hypothesis generation failed: {}", exc)
            hypotheses_dicts = []

        elapsed = time.monotonic() - start_time
        return AnalysisResult(
            bundle_metadata=index.metadata,
            triage=triage,
            findings=[],
            causal_chains=[],
            root_cause=None,
            confidence=0.0,
            timeline=timeline,
            predictions=predictions,
            uncertainty=[
                UncertaintyGap(
                    question="AI analysis was not performed",
                    reason="No AI provider key set",
                    to_investigate="Set OPEN_ROUTER_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY",
                    impact="HIGH",
                )
            ],
            log_diagnoses=[],
            preflight_report=triage.preflight_report,
            cluster_summary=build_cluster_summary(triage, index),
            analysis_duration_seconds=elapsed,
            hypotheses=hypotheses_dicts,
        )
