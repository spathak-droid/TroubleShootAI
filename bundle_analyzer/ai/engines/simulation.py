"""Fix simulation engine -- counterfactual reasoning about proposed fixes.

Given a proposed fix, uses AI to simulate what would happen if the fix
were applied: what resolves, what might break, residual issues, recovery
timeline, and manual steps remaining afterward.
"""

from __future__ import annotations

import json
import re

from loguru import logger

from bundle_analyzer.ai.client import BundleAnalyzerClient
from bundle_analyzer.models import Finding, Fix, SimulationResult

_SYSTEM_PROMPT = """\
You are a senior Kubernetes SRE reasoning about the cascade effects of \
applying a proposed fix to a cluster issue.

Given:
1. A finding (the detected issue with root cause and evidence)
2. A proposed fix (description, optional YAML patch, commands, risk level)
3. A summary of the overall cluster analysis

Your task: simulate what would happen if the fix were applied RIGHT NOW.

Think carefully about:
- Which symptoms the fix directly resolves
- What NEW issues the fix might introduce (e.g. pod restarts, brief downtime, \
resource contention, broken dependent services)
- What residual issues would remain even after the fix
- How long recovery would take (e.g. "30 seconds for pod restart", \
"5-10 minutes for rollout", "requires manual DNS propagation ~15 min")
- What manual steps an engineer must perform after applying the fix

You must respond with valid JSON only. Use this exact schema:
{
  "fix_resolves": ["<issue that gets resolved>", ...],
  "fix_creates": ["<new issue the fix might introduce>", ...],
  "residual_issues": ["<issue that remains even after the fix>", ...],
  "recovery_timeline": "<human-readable estimate of time to full recovery>",
  "manual_steps_after": ["<step an engineer must do after applying the fix>", ...],
  "confidence": <float 0.0-1.0 representing how confident you are in this simulation>
}

Do NOT include any text outside the JSON object. No markdown fences, \
no explanations before or after."""

_USER_PROMPT_TEMPLATE = """\
## Finding

- **ID**: {finding_id}
- **Severity**: {severity}
- **Type**: {finding_type}
- **Resource**: {resource}
- **Symptom**: {symptom}
- **Root Cause**: {root_cause}
- **Confidence**: {finding_confidence}

## Proposed Fix

- **Description**: {fix_description}
- **Risk Level**: {fix_risk}
{yaml_patch_section}\
{commands_section}\

## Cluster Analysis Summary

{analysis_summary}

---

Simulate the effects of applying this fix. Return JSON only."""


class FixSimulationEngine:
    """Simulates the cascade effects of applying a proposed fix.

    Uses AI to reason about what a fix would resolve, what new issues it
    might create, residual problems, recovery timeline, and manual steps
    remaining. Falls back to a degraded result when the AI call fails.
    """

    def __init__(self, client: BundleAnalyzerClient | None = None) -> None:
        """Initialise the simulation engine.

        Args:
            client: AI client instance. If not provided, one is created
                on first use.
        """
        self._client = client

    def _get_client(self) -> BundleAnalyzerClient:
        """Lazily initialise the AI client.

        Returns:
            The BundleAnalyzerClient instance.
        """
        if self._client is None:
            self._client = BundleAnalyzerClient()
        return self._client

    async def simulate(
        self,
        fix: Fix,
        finding: Finding,
        analysis_summary: str,
    ) -> SimulationResult:
        """Simulate the effects of applying a fix to a finding.

        Builds a prompt describing the finding and proposed fix, sends it
        to the AI for counterfactual reasoning, and parses the structured
        JSON response into a SimulationResult.

        Args:
            fix: The proposed fix to simulate.
            finding: The finding the fix addresses.
            analysis_summary: A textual summary of the overall cluster
                analysis for additional context.

        Returns:
            SimulationResult with predicted outcomes of applying the fix.
        """
        user_prompt = self._build_prompt(fix, finding, analysis_summary)

        logger.info(
            "Simulating fix for finding {id} | resource={resource} risk={risk}",
            id=finding.id,
            resource=finding.resource,
            risk=fix.risk,
        )

        try:
            client = self._get_client()
            raw = await client.complete(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=2048,
                temperature=0.4,
            )

            result = self._parse_response(raw)
            logger.info(
                "Simulation complete for {id} | resolves={resolves} "
                "creates={creates} residual={residual} confidence={conf:.2f}",
                id=finding.id,
                resolves=len(result.fix_resolves),
                creates=len(result.fix_creates),
                residual=len(result.residual_issues),
                conf=result.confidence,
            )
            return result

        except Exception as exc:
            logger.warning(
                "Simulation AI call failed for finding {id}: {err}. "
                "Returning degraded result.",
                id=finding.id,
                err=str(exc),
            )
            return self._degraded_result(fix, finding)

    def _build_prompt(
        self,
        fix: Fix,
        finding: Finding,
        analysis_summary: str,
    ) -> str:
        """Build the user prompt from the fix, finding, and summary.

        Args:
            fix: The proposed fix.
            finding: The finding being addressed.
            analysis_summary: Overall cluster analysis summary.

        Returns:
            Formatted user prompt string.
        """
        yaml_section = ""
        if fix.yaml_patch:
            yaml_section = f"- **YAML Patch**:\n```yaml\n{fix.yaml_patch}\n```\n"

        commands_section = ""
        if fix.commands:
            cmds = "\n".join(f"  - `{c}`" for c in fix.commands)
            commands_section = f"- **Commands**:\n{cmds}\n"

        return _USER_PROMPT_TEMPLATE.format(
            finding_id=finding.id,
            severity=finding.severity,
            finding_type=finding.type,
            resource=finding.resource,
            symptom=finding.symptom,
            root_cause=finding.root_cause,
            finding_confidence=finding.confidence,
            fix_description=fix.description,
            fix_risk=fix.risk,
            yaml_patch_section=yaml_section,
            commands_section=commands_section,
            analysis_summary=analysis_summary or "No additional context available.",
        )

    def _parse_response(self, raw: str) -> SimulationResult:
        """Parse the AI response into a SimulationResult.

        Handles responses that may be wrapped in markdown code fences
        or contain extraneous whitespace.

        Args:
            raw: Raw text response from the AI.

        Returns:
            Validated SimulationResult.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON
                matching the SimulationResult schema.
        """
        text = raw.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AI returned invalid JSON for simulation: {exc}"
            ) from exc

        # Clamp confidence to [0, 1]
        if "confidence" in data:
            data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))

        return SimulationResult.model_validate(data)

    def _degraded_result(self, fix: Fix, finding: Finding) -> SimulationResult:
        """Return a conservative fallback when AI simulation fails.

        Provides a safe, low-confidence result based on heuristics
        derived from the fix risk level and finding severity.

        Args:
            fix: The proposed fix.
            finding: The finding being addressed.

        Returns:
            A conservative SimulationResult with low confidence.
        """
        resolves = [f"May resolve: {finding.symptom}"]

        creates: list[str] = []
        if fix.risk == "disruptive":
            creates.append(
                "Fix is marked disruptive -- expect brief service "
                "interruption during application"
            )
        elif fix.risk == "needs-verification":
            creates.append(
                "Fix requires verification -- test in staging "
                "before applying to production"
            )

        residual: list[str] = []
        if finding.severity == "critical":
            residual.append(
                "Critical finding -- monitor closely after applying fix "
                "to confirm full resolution"
            )

        manual_steps = ["Verify the fix resolved the issue by re-collecting a support bundle"]
        if fix.commands:
            manual_steps.insert(0, "Review and execute the suggested commands")
        if fix.yaml_patch:
            manual_steps.insert(0, "Review the YAML patch before applying")

        return SimulationResult(
            fix_resolves=resolves,
            fix_creates=creates,
            residual_issues=residual,
            recovery_timeline="Unknown -- AI simulation unavailable",
            manual_steps_after=manual_steps,
            confidence=0.2,
        )
