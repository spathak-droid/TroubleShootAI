"""Post-synthesis claim validator.

Checks AI-generated findings against deterministic bundle evidence.
For each finding, verifies that cited evidence files exist, excerpts
match actual content, and AI claims are corroborated by triage data.
Downgrades confidence for unverifiable claims and flags pure hypotheses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, Field

from bundle_analyzer.models import Evidence, Finding, TriageResult

from .helpers import fuzzy_match
from .pass_evidence import resolve_evidence_path

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class ClaimValidation(BaseModel):
    """Validation result for a single finding's evidence claims."""

    finding_id: str
    original_confidence: float
    validated_confidence: float
    evidence_verified: int = 0
    evidence_total: int = 0
    unverified_evidence: list[str] = Field(default_factory=list)
    is_hypothesis: bool = False
    triage_corroborated: bool = False
    corroboration_details: list[str] = Field(default_factory=list)


class ClaimValidationResult(BaseModel):
    """Aggregated result of validating all findings against bundle evidence."""

    findings: list[Finding]
    validations: list[ClaimValidation] = Field(default_factory=list)
    total_verified: int = 0
    total_unverified: int = 0
    hypothesis_count: int = 0
    triage_corroborated_count: int = 0


class ClaimValidator:
    """Validates AI claims against deterministic bundle evidence and triage data.

    After the AI pipeline produces findings, this validator:
    1. Checks evidence citations against actual bundle contents.
    2. Cross-references AI claims against triage scanner findings.
    3. Boosts confidence for triage-corroborated findings.
    4. Downgrades confidence for unverifiable claims.
    """

    async def validate(
        self,
        findings: list[Finding],
        index: BundleIndex,
        triage: TriageResult | None = None,
    ) -> ClaimValidationResult:
        """Validate all findings against bundle evidence and triage data.

        Args:
            findings: List of AI-generated findings to validate.
            index: The bundle index for reading raw files.
            triage: Optional triage results for cross-referencing.

        Returns:
            ClaimValidationResult with adjusted findings and validation metadata.
        """
        validations: list[ClaimValidation] = []
        adjusted_findings: list[Finding] = []
        total_verified = 0
        total_unverified = 0
        hypothesis_count = 0
        triage_corroborated_count = 0

        for finding in findings:
            validation = await self._validate_finding(finding, index, triage)
            validations.append(validation)

            # Build adjusted finding with new confidence
            adjusted = finding.model_copy(
                update={"confidence": validation.validated_confidence},
            )
            adjusted_findings.append(adjusted)

            total_verified += validation.evidence_verified
            total_unverified += (
                validation.evidence_total - validation.evidence_verified
            )
            if validation.is_hypothesis:
                hypothesis_count += 1
            if validation.triage_corroborated:
                triage_corroborated_count += 1

        logger.info(
            "Claim validation complete: {} findings, {} evidence verified, "
            "{} unverified, {} hypotheses, {} triage-corroborated",
            len(findings),
            total_verified,
            total_unverified,
            hypothesis_count,
            triage_corroborated_count,
        )

        return ClaimValidationResult(
            findings=adjusted_findings,
            validations=validations,
            total_verified=total_verified,
            total_unverified=total_unverified,
            hypothesis_count=hypothesis_count,
            triage_corroborated_count=triage_corroborated_count,
        )

    async def _validate_finding(
        self,
        finding: Finding,
        index: BundleIndex,
        triage: TriageResult | None = None,
    ) -> ClaimValidation:
        """Validate a single finding's evidence against the bundle and triage.

        Args:
            finding: The finding to validate.
            index: The bundle index for reading raw files.
            triage: Optional triage data for corroboration.

        Returns:
            ClaimValidation with verification counts and adjusted confidence.
        """
        original_confidence = finding.confidence
        evidence_items = finding.evidence
        evidence_total = len(evidence_items)
        evidence_verified = 0
        unverified_paths: list[str] = []

        for ev in evidence_items:
            verified = await self._verify_evidence(ev, index)
            if verified:
                evidence_verified += 1
            else:
                unverified_paths.append(ev.file)

        # Cross-reference with triage data
        triage_corroborated = False
        corroboration_details: list[str] = []
        if triage is not None:
            triage_corroborated, corroboration_details = self._cross_reference_triage(
                finding, triage
            )

        # Compute adjusted confidence
        validated_confidence = original_confidence
        is_hypothesis = False

        if evidence_total == 0 or evidence_verified == 0:
            if triage_corroborated:
                # No direct evidence but triage confirms the issue — partial trust
                validated_confidence = original_confidence * 0.6
                logger.debug(
                    "Finding {} has no verifiable evidence but is triage-corroborated "
                    "(confidence {:.2f} -> {:.2f})",
                    finding.id, original_confidence, validated_confidence,
                )
            else:
                # No evidence AND no triage corroboration — hypothesis
                validated_confidence = original_confidence * 0.3
                is_hypothesis = True
                logger.debug(
                    "Finding {} has no verifiable evidence, marking as hypothesis "
                    "(confidence {:.2f} -> {:.2f})",
                    finding.id, original_confidence, validated_confidence,
                )
        elif evidence_verified < evidence_total:
            # Some evidence verified, some not — partial penalty
            unverified_count = evidence_total - evidence_verified
            penalty_factor = 1.0 - (0.5 * unverified_count / evidence_total)
            validated_confidence = original_confidence * max(penalty_factor, 0.3)
            # Boost if triage corroborates
            if triage_corroborated:
                validated_confidence = min(1.0, validated_confidence * 1.15)
            logger.debug(
                "Finding {} has {}/{} evidence verified "
                "(confidence {:.2f} -> {:.2f})",
                finding.id, evidence_verified, evidence_total,
                original_confidence, validated_confidence,
            )
        else:
            # All evidence verified
            if triage_corroborated:
                # Both evidence AND triage confirm — boost confidence
                validated_confidence = min(1.0, original_confidence * 1.1)

        # Clamp to [0.0, 1.0]
        validated_confidence = max(0.0, min(1.0, validated_confidence))

        return ClaimValidation(
            finding_id=finding.id,
            original_confidence=original_confidence,
            validated_confidence=validated_confidence,
            evidence_verified=evidence_verified,
            evidence_total=evidence_total,
            unverified_evidence=unverified_paths,
            is_hypothesis=is_hypothesis,
            triage_corroborated=triage_corroborated,
            corroboration_details=corroboration_details,
        )

    def _cross_reference_triage(
        self,
        finding: Finding,
        triage: TriageResult,
    ) -> tuple[bool, list[str]]:
        """Check if a finding is corroborated by triage scanner data.

        Looks for matching resource names, issue types, and symptoms
        in the deterministic triage results.

        Args:
            finding: The AI-generated finding to check.
            triage: The triage results from deterministic scanners.

        Returns:
            Tuple of (is_corroborated, list_of_corroboration_details).
        """
        details: list[str] = []
        resource = (finding.resource or "").lower()
        symptom = (finding.symptom or "").lower()
        root_cause = (finding.root_cause or "").lower()
        combined_text = f"{symptom} {root_cause}"

        # Check against critical/warning pods
        for pod in list(triage.critical_pods) + list(triage.warning_pods):
            pod_key = f"{pod.namespace}/{pod.pod_name}".lower()
            if pod_key in resource or resource.endswith(pod.pod_name.lower()):
                details.append(
                    f"Triage confirms pod issue: {pod.issue_type} "
                    f"({pod.namespace}/{pod.pod_name}, restarts={pod.restart_count})"
                )
                break

        # Check against node issues
        for node in triage.node_issues:
            if node.node_name.lower() in resource:
                details.append(
                    f"Triage confirms node issue: {node.condition} on {node.node_name}"
                )
                break

        # Check against config issues
        for cfg in triage.config_issues:
            cfg_key = f"{cfg.resource_type}/{cfg.resource_name}".lower()
            if cfg_key in combined_text or cfg.resource_name.lower() in combined_text:
                details.append(
                    f"Triage confirms config issue: {cfg.issue} "
                    f"({cfg.resource_type}/{cfg.resource_name})"
                )
                break

        # Check for OOM-related findings against exit codes
        if "oom" in combined_text or "137" in combined_text:
            for pod in triage.critical_pods:
                if pod.exit_code == 137:
                    details.append(
                        f"Triage confirms OOM: {pod.namespace}/{pod.pod_name} exit_code=137"
                    )
                    break

        # Check against crash contexts (most valuable)
        for ctx in triage.crash_contexts:
            ctx_key = f"{ctx.namespace}/{ctx.pod_name}".lower()
            if ctx_key in resource:
                details.append(
                    f"Triage crash context confirms: {ctx.crash_pattern} "
                    f"({ctx.namespace}/{ctx.pod_name}, restarts={ctx.restart_count})"
                )
                break

        # Check against broken dependencies
        if triage.dependency_map and hasattr(triage.dependency_map, "broken_dependencies"):
            for dep in triage.dependency_map.broken_dependencies:
                if dep.target_service.lower() in combined_text:
                    details.append(
                        f"Triage confirms broken dependency: {dep.source_pod} → {dep.target_service}"
                    )
                    break

        return bool(details), details

    async def _verify_evidence(
        self,
        evidence: Evidence,
        index: BundleIndex,
    ) -> bool:
        """Verify a single evidence citation against the bundle.

        Checks that the file exists and that the excerpt appears in
        the file content using fuzzy whitespace-normalized matching.

        Args:
            evidence: The evidence citation to verify.
            index: The bundle index for reading raw files.

        Returns:
            True if the evidence could be verified, False otherwise.
        """
        file_path = evidence.file
        excerpt = evidence.excerpt or ""

        # Resolve the evidence path (handles resource-key-style paths)
        content = resolve_evidence_path(file_path, index)

        if content is None:
            logger.trace("Evidence file not found: {}", file_path)
            return False

        # File exists — if no excerpt provided, count as verified
        if not excerpt:
            return True

        # Check if excerpt appears in content (fuzzy match)
        if fuzzy_match(excerpt, content):
            return True

        # File exists but excerpt doesn't match
        logger.trace(
            "Evidence file {} exists but excerpt not found (first 60 chars: {})",
            file_path,
            excerpt[:60],
        )
        return False
