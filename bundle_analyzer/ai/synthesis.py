"""Synthesis engine — cross-correlates analyst outputs into root causes.

Takes individual analyst findings and produces a unified causal chain,
root cause identification, and confidence-scored recommendations.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.ai.prompts.synthesis import (
    SYNTHESIS_SYSTEM_PROMPT,
    build_synthesis_user_prompt,
)
from bundle_analyzer.models import AnalystOutput, TriageResult


class SynthesisEngine:
    """Cross-correlates multiple analyst outputs into a unified root cause analysis.

    Takes findings from pod, node, and config analysts plus the raw triage report
    and uses Claude to identify causal chains, blast radius, and prioritized fixes.
    """

    async def synthesize(
        self,
        client: BundleAnalyzerClient,
        analyst_outputs: list[AnalystOutput],
        triage: TriageResult,
    ) -> dict[str, Any]:
        """Run the synthesis pass across all analyst outputs.

        Args:
            client: The Anthropic API client with retry logic.
            analyst_outputs: Structured outputs from each analyst.
            triage: Raw triage scan results for additional context.

        Returns:
            Dictionary with root_cause, confidence, causal_chain, blast_radius,
            recommended_fixes, and uncertainty_report keys.
        """
        if not analyst_outputs:
            logger.warning("No analyst outputs to synthesize — returning empty result")
            return self._empty_result()

        user_prompt = build_synthesis_user_prompt(analyst_outputs, triage)
        logger.debug(
            "Synthesis prompt built: {} analyst outputs, {} chars",
            len(analyst_outputs),
            len(user_prompt),
        )

        try:
            raw_response = await client.complete(
                system=SYNTHESIS_SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=4096,
                temperature=0.3,
            )
            result = self._parse_response(raw_response)
            logger.info(
                "Synthesis complete: root_cause='{}', confidence={}",
                result.get("root_cause", "unknown")[:80],
                result.get("confidence", "unknown"),
            )
            return result
        except json.JSONDecodeError as exc:
            logger.error("Synthesis response was not valid JSON: {}", exc)
            return self._fallback_result(analyst_outputs)
        except RuntimeError as exc:
            logger.error("Synthesis API call failed: {}", exc)
            return self._fallback_result(analyst_outputs)

    def _parse_response(self, raw: str) -> dict[str, Any]:
        """Parse the JSON response from Claude, stripping any markdown fencing.

        Args:
            raw: Raw text response from the API.

        Returns:
            Parsed dictionary matching the synthesis schema.

        Raises:
            json.JSONDecodeError: If the response cannot be parsed as JSON.
        """
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        result: dict[str, Any] = json.loads(text)

        # Validate required keys with defaults
        result.setdefault("root_cause", "Unable to determine root cause")
        result.setdefault("confidence", "low")
        result.setdefault("causal_chain", [])
        result.setdefault("blast_radius", "Unknown")
        result.setdefault("recommended_fixes", [])
        result.setdefault("uncertainty_report", {
            "what_i_know": [],
            "what_i_suspect": [],
            "what_i_cant_determine": [],
        })
        return result

    def _empty_result(self) -> dict[str, Any]:
        """Return an empty synthesis result when no analyst outputs are available."""
        return {
            "root_cause": "No analyst outputs available for synthesis",
            "confidence": "low",
            "causal_chain": [],
            "blast_radius": "Unknown — no analysis performed",
            "recommended_fixes": [],
            "uncertainty_report": {
                "what_i_know": [],
                "what_i_suspect": [],
                "what_i_cant_determine": [
                    "No AI analysis was performed — only triage data is available"
                ],
            },
        }

    def _fallback_result(
        self, analyst_outputs: list[AnalystOutput]
    ) -> dict[str, Any]:
        """Build a best-effort result from analyst outputs when synthesis fails.

        Args:
            analyst_outputs: The individual analyst outputs to aggregate.

        Returns:
            Dictionary with aggregated findings as a fallback.
        """
        # Pick the highest-confidence analyst's root cause
        best = max(analyst_outputs, key=lambda o: o.confidence, default=None)
        root_cause = best.root_cause if best and best.root_cause else "Synthesis failed"
        confidence = "low"

        all_findings: list[str] = []
        for output in analyst_outputs:
            for finding in output.findings:
                all_findings.append(f"[{finding.severity}] {finding.resource}: {finding.root_cause}")

        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "causal_chain": [],
            "blast_radius": "Unable to determine — synthesis failed",
            "recommended_fixes": [],
            "uncertainty_report": {
                "what_i_know": all_findings[:10],
                "what_i_suspect": [],
                "what_i_cant_determine": ["Synthesis pass failed — individual findings only"],
            },
        }
