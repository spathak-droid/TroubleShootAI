"""Regex-based pattern detector for sensitive data in support bundles.

Compiles all patterns at module load time for performance.
Handles ***HIDDEN*** redaction markers — never flags them as secrets.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from loguru import logger

from bundle_analyzer.security.models import RedactionEntry

# ---------------------------------------------------------------------------
# Pattern definition helpers
# ---------------------------------------------------------------------------


class _PatternRule(NamedTuple):
    """A single compiled pattern rule."""

    name: str
    regex: re.Pattern[str]
    replacement: str
    category: str
    confidence: float


def _compile(
    name: str,
    pattern: str,
    replacement: str,
    category: str,
    confidence: float = 1.0,
    flags: int = 0,
) -> _PatternRule:
    """Compile a single pattern rule at import time."""
    return _PatternRule(
        name=name,
        regex=re.compile(pattern, flags),
        replacement=replacement,
        category=category,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# CREDENTIAL_PATTERNS
# ---------------------------------------------------------------------------

CREDENTIAL_PATTERNS: list[_PatternRule] = [
    _compile(
        "JWT token",
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.?[A-Za-z0-9_-]*",
        "[REDACTED:jwt]",
        "credential",
    ),
    _compile(
        "Bearer token",
        r"[Bb]earer\s+[A-Za-z0-9_\-.~+/]+=*",
        "[REDACTED:bearer]",
        "credential",
    ),
    _compile(
        "Authorization header",
        r"[Aa]uthorization:\s*\S+",
        "[REDACTED:auth-header]",
        "credential",
    ),
    _compile(
        "AWS access key",
        r"AKIA[0-9A-Z]{16}",
        "[REDACTED:aws-key]",
        "credential",
    ),
    _compile(
        "AWS secret",
        r"(aws_secret_access_key|aws_secret)\s*[=:]\s*\S+",
        "[REDACTED:aws-secret]",
        "credential",
        flags=re.IGNORECASE,
    ),
    _compile(
        "GitHub token",
        r"gh[ps]_[A-Za-z0-9_]{36,}",
        "[REDACTED:github-token]",
        "credential",
    ),
    _compile(
        "GitLab token",
        r"glpat-[A-Za-z0-9_\-]{20,}",
        "[REDACTED:gitlab-token]",
        "credential",
    ),
    _compile(
        "Generic API key",
        r"(api[_-]?key|apikey|api[_-]?secret)\s*[=:]\s*[\"']?\S+",
        "[REDACTED:api-key]",
        "credential",
        confidence=0.85,
        flags=re.IGNORECASE,
    ),
    _compile(
        "Private key",
        r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)?\s*PRIVATE\s+KEY-----[\s\S]*?-----END",
        "[REDACTED:private-key]",
        "credential",
        flags=re.DOTALL,
    ),
    _compile(
        "SSH public key",
        r"ssh-(rsa|ed25519|ecdsa)\s+[A-Za-z0-9+/=]{20,}",
        "[REDACTED:ssh-pubkey]",
        "credential",
        confidence=0.9,
    ),
    _compile(
        "Connection string",
        r"(postgres|mysql|mongodb|redis|amqp|mssql)://[^\s\"']+",
        "[REDACTED:connection-string]",
        "credential",
    ),
    _compile(
        "Generic password",
        r"(password|passwd|pwd|secret|token)\s*[=:]\s*[\"']?[^\s\"',;]{4,}",
        "[REDACTED:password]",
        "credential",
        confidence=0.8,
        flags=re.IGNORECASE,
    ),
    _compile(
        "Session cookie",
        r"(session[_-]?id|sessiontoken|csrf[_-]?token)\s*[=:]\s*\S+",
        "[REDACTED:session]",
        "credential",
        confidence=0.9,
        flags=re.IGNORECASE,
    ),
    _compile(
        "OAuth token",
        r"(access[_-]?token|refresh[_-]?token|oauth[_-]?token)\s*[=:]\s*\S+",
        "[REDACTED:oauth]",
        "credential",
        confidence=0.9,
        flags=re.IGNORECASE,
    ),
    _compile(
        "Docker auth",
        r"\"auth\"\s*:\s*\"[A-Za-z0-9+/=]{20,}\"",
        '"auth": "[REDACTED:docker-auth]"',
        "credential",
        flags=re.IGNORECASE,
    ),
    _compile(
        "npm/pypi token",
        r"(npm_token|_authToken|pypi[_-]?token)\s*[=:]\s*\S+",
        "[REDACTED:package-token]",
        "credential",
        flags=re.IGNORECASE,
    ),
    _compile(
        "Kubeconfig token",
        r"(client-certificate-data|client-key-data|token)\s*:\s*[A-Za-z0-9+/=]{20,}",
        "[REDACTED:kubeconfig]",
        "credential",
        flags=re.IGNORECASE,
    ),
    _compile(
        "Webhook URL",
        r"https?://hooks\.(slack\.com|discord\.com|teams\.microsoft\.com)/\S+",
        "[REDACTED:webhook-url]",
        "credential",
    ),
    _compile(
        "Presigned URL",
        r"https?://\S+[?&](X-Amz-Signature|Signature|sig|token)=[^\s&\"']+",
        "[REDACTED:presigned-url]",
        "credential",
    ),
    _compile(
        "CI token",
        r"(CIRCLE_TOKEN|TRAVIS_TOKEN|JENKINS_TOKEN|GITHUB_TOKEN)\s*[=:]\s*\S+",
        "[REDACTED:ci-token]",
        "credential",
        flags=re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# PII_PATTERNS
# ---------------------------------------------------------------------------

PII_PATTERNS: list[_PatternRule] = [
    _compile(
        "Email address",
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "[REDACTED:email]",
        "pii",
        confidence=0.9,
    ),
    _compile(
        "Phone number",
        r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
        "[REDACTED:phone]",
        "pii",
        confidence=0.7,
    ),
    _compile(
        "SSN",
        r"\b\d{3}-\d{2}-\d{4}\b",
        "[REDACTED:ssn]",
        "pii",
    ),
]

# ---------------------------------------------------------------------------
# INFRASTRUCTURE_PATTERNS
# ---------------------------------------------------------------------------

INFRASTRUCTURE_PATTERNS: list[_PatternRule] = [
    _compile(
        "Internal/private IP",
        r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b",
        "[REDACTED:ip]",
        "infrastructure",
        confidence=0.85,
    ),
    _compile(
        "AWS ARN",
        r"arn:aws[a-z-]*:[a-z0-9-]+:\S+",
        "[REDACTED:arn]",
        "infrastructure",
    ),
    _compile(
        "S3 bucket URL",
        r"s3://[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]",
        "[REDACTED:s3-bucket]",
        "infrastructure",
    ),
    _compile(
        "Internal hostname",
        r"\b[a-z][a-z0-9-]+\.(internal|local|corp|lan|priv)\b",
        "[REDACTED:hostname]",
        "infrastructure",
        confidence=0.8,
        flags=re.IGNORECASE,
    ),
    _compile(
        "Cluster name ref",
        r"(cluster[_-]?name|CLUSTER_NAME)\s*[=:]\s*\S+",
        "[REDACTED:cluster-name]",
        "infrastructure",
        confidence=0.9,
        flags=re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# PROPRIETARY_CODE_PATTERNS
# ---------------------------------------------------------------------------

PROPRIETARY_CODE_PATTERNS: list[_PatternRule] = [
    _compile(
        "File path with username",
        r"/(?:home|Users)/[a-zA-Z][a-zA-Z0-9._-]*/",
        "[REDACTED:user-path]/",
        "proprietary_code",
        confidence=0.75,
    ),
    _compile(
        "Git repo URL",
        r"git@[a-zA-Z0-9.-]+:[^\s]+\.git",
        "[REDACTED:git-repo]",
        "proprietary_code",
    ),
    _compile(
        "Internal repo ref",
        r"(?:github|gitlab|bitbucket)\.(?:com|internal)/[^\s\"']+",
        "[REDACTED:repo-ref]",
        "proprietary_code",
        confidence=0.85,
        flags=re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Combined lookup: category → patterns
# ---------------------------------------------------------------------------

ALL_PATTERNS: dict[str, list[_PatternRule]] = {
    "credential": CREDENTIAL_PATTERNS,
    "pii": PII_PATTERNS,
    "infrastructure": INFRASTRUCTURE_PATTERNS,
    "proprietary_code": PROPRIETARY_CODE_PATTERNS,
}

# Flat list for convenience (order: credentials first for priority)
_ALL_FLAT: list[_PatternRule] = (
    CREDENTIAL_PATTERNS
    + PII_PATTERNS
    + INFRASTRUCTURE_PATTERNS
    + PROPRIETARY_CODE_PATTERNS
)

# Pre-compiled regex for the HIDDEN marker
_HIDDEN_RE: re.Pattern[str] = re.compile(re.escape("***HIDDEN***"))


# ---------------------------------------------------------------------------
# PatternDetector
# ---------------------------------------------------------------------------


class PatternDetector:
    """Detects sensitive patterns in text using compiled regex rules."""

    HIDDEN_MARKER: str = "***HIDDEN***"

    def __init__(self) -> None:
        """Initialise the detector with all compiled pattern rules."""
        self._patterns: list[_PatternRule] = _ALL_FLAT
        logger.debug(
            "PatternDetector initialised with {} rules across {} categories",
            len(self._patterns),
            len(ALL_PATTERNS),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hidden_spans(text: str) -> list[tuple[int, int]]:
        """Return (start, end) spans of all ***HIDDEN*** markers in *text*."""
        return [(m.start(), m.end()) for m in _HIDDEN_RE.finditer(text)]

    @staticmethod
    def _overlaps_hidden(
        start: int, end: int, hidden_spans: list[tuple[int, int]]
    ) -> bool:
        """Return True if [start, end) overlaps any HIDDEN marker span."""
        for hs, he in hidden_spans:
            if start < he and end > hs:
                return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(
        self, text: str
    ) -> list[tuple[int, int, str, str, str, float]]:
        """Find all sensitive patterns in *text*.

        Returns a list of tuples:
            ``(start, end, pattern_name, category, replacement, confidence)``

        Matches that overlap with ``***HIDDEN***`` markers are skipped —
        those are intentional redactions, not secrets.
        """
        hidden_spans = self._hidden_spans(text)
        results: list[tuple[int, int, str, str, str, float]] = []
        seen_spans: set[tuple[int, int]] = set()

        for rule in self._patterns:
            for m in rule.regex.finditer(text):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                if self._overlaps_hidden(span[0], span[1], hidden_spans):
                    continue
                seen_spans.add(span)
                results.append((
                    span[0],
                    span[1],
                    rule.name,
                    rule.category,
                    rule.replacement,
                    rule.confidence,
                ))

        # Sort by start position
        results.sort(key=lambda r: r[0])
        return results

    def redact_all(
        self, text: str
    ) -> tuple[str, list[RedactionEntry]]:
        """Find and replace all sensitive patterns in *text*.

        Returns ``(redacted_text, list_of_redaction_entries)``.

        Processes matches from right to left so that earlier indices remain
        valid after each substitution.
        """
        detections = self.detect_all(text)
        entries: list[RedactionEntry] = []
        redacted = text

        # Process right-to-left to preserve character offsets
        for start, end, name, category, replacement, confidence in reversed(detections):
            redacted = redacted[:start] + replacement + redacted[end:]
            entries.append(
                RedactionEntry(
                    pattern_name=name,
                    replacement=replacement,
                    detector="pattern",
                    category=category,  # type: ignore[arg-type]
                    confidence=confidence,
                )
            )

        # Reverse entries so they are in forward order
        entries.reverse()

        if entries:
            logger.info(
                "PatternDetector redacted {} sensitive patterns", len(entries)
            )

        return redacted, entries

    def detect_category(
        self, text: str, category: str
    ) -> list[tuple[int, int, str, str, str, float]]:
        """Detect only patterns of a specific *category*.

        Valid categories: ``credential``, ``pii``, ``infrastructure``,
        ``proprietary_code``.

        Returns the same tuple format as :meth:`detect_all`.
        """
        if category not in ALL_PATTERNS:
            logger.warning(
                "Unknown category '{}'; valid categories: {}",
                category,
                list(ALL_PATTERNS.keys()),
            )
            return []

        hidden_spans = self._hidden_spans(text)
        results: list[tuple[int, int, str, str, str, float]] = []
        seen_spans: set[tuple[int, int]] = set()

        for rule in ALL_PATTERNS[category]:
            for m in rule.regex.finditer(text):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                if self._overlaps_hidden(span[0], span[1], hidden_spans):
                    continue
                seen_spans.add(span)
                results.append((
                    span[0],
                    span[1],
                    rule.name,
                    rule.category,
                    rule.replacement,
                    rule.confidence,
                ))

        results.sort(key=lambda r: r[0])
        return results
