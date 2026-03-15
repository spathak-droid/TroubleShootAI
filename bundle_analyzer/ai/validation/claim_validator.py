"""Post-synthesis claim validator.

Checks AI-generated findings against deterministic bundle evidence.
For each finding, verifies that cited evidence files exist and that
excerpts actually appear in those files. Downgrades confidence for
unverifiable claims and flags pure hypotheses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from pydantic import BaseModel, Field

from bundle_analyzer.models import Evidence, Finding

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


class ClaimValidationResult(BaseModel):
    """Aggregated result of validating all findings against bundle evidence."""

    findings: list[Finding]
    validations: list[ClaimValidation] = Field(default_factory=list)
    total_verified: int = 0
    total_unverified: int = 0
    hypothesis_count: int = 0


class ClaimValidator:
    """Validates AI claims against deterministic bundle evidence.

    After the AI pipeline produces findings, this validator checks each
    finding's evidence citations against the actual bundle contents.
    Findings with unverifiable evidence get their confidence reduced;
    findings with zero verifiable evidence are marked as hypotheses.
    """

    async def validate(
        self,
        findings: list[Finding],
        index: BundleIndex,
    ) -> ClaimValidationResult:
        """Validate all findings against bundle evidence.

        For each finding:
        - Checks if evidence files exist in the bundle.
        - Verifies that cited excerpts appear in the file content (fuzzy match).
        - Adjusts confidence downward for unverifiable claims.

        Args:
            findings: List of AI-generated findings to validate.
            index: The bundle index for reading raw files.

        Returns:
            ClaimValidationResult with adjusted findings and validation metadata.
        """
        validations: list[ClaimValidation] = []
        adjusted_findings: list[Finding] = []
        total_verified = 0
        total_unverified = 0
        hypothesis_count = 0

        for finding in findings:
            validation = await self._validate_finding(finding, index)
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

        logger.info(
            "Claim validation complete: {} findings, {} evidence verified, "
            "{} unverified, {} hypotheses",
            len(findings),
            total_verified,
            total_unverified,
            hypothesis_count,
        )

        return ClaimValidationResult(
            findings=adjusted_findings,
            validations=validations,
            total_verified=total_verified,
            total_unverified=total_unverified,
            hypothesis_count=hypothesis_count,
        )

    async def _validate_finding(
        self,
        finding: Finding,
        index: BundleIndex,
    ) -> ClaimValidation:
        """Validate a single finding's evidence against the bundle.

        Args:
            finding: The finding to validate.
            index: The bundle index for reading raw files.

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

        # Compute adjusted confidence
        validated_confidence = original_confidence
        is_hypothesis = False

        if evidence_total == 0 or evidence_verified == 0:
            # No evidence could be verified -- treat as hypothesis
            validated_confidence = original_confidence * 0.3
            is_hypothesis = True
            logger.debug(
                "Finding {} has no verifiable evidence, marking as hypothesis "
                "(confidence {:.2f} -> {:.2f})",
                finding.id,
                original_confidence,
                validated_confidence,
            )
        elif evidence_verified < evidence_total:
            # Some evidence verified, some not -- partial penalty
            unverified_count = evidence_total - evidence_verified
            # Apply 0.5 penalty per unverified evidence item, proportionally
            penalty_factor = 1.0 - (0.5 * unverified_count / evidence_total)
            validated_confidence = original_confidence * max(penalty_factor, 0.3)
            logger.debug(
                "Finding {} has {}/{} evidence verified "
                "(confidence {:.2f} -> {:.2f})",
                finding.id,
                evidence_verified,
                evidence_total,
                original_confidence,
                validated_confidence,
            )

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
        )

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

        # File exists -- if no excerpt provided, count as verified
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
