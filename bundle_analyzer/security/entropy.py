"""Entropy-based secret detection for unknown credential patterns.

Uses Shannon entropy to identify high-randomness strings that are likely
secrets but don't match any known regex pattern. Calibrated to minimize
false positives on common K8s data like UUIDs, SHA digests, and resource UIDs.
"""

from __future__ import annotations

import math
import re
import string

from bundle_analyzer.security.models import RedactionEntry

# Known false positive patterns — high entropy but NOT secrets
_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
_SHA_DIGEST_RE = re.compile(r'sha256:[0-9a-f]{64}')
_K8S_UID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_DOCKER_IMAGE_DIGEST_RE = re.compile(r'@sha256:[0-9a-f]{64}')
_RESOURCE_VERSION_RE = re.compile(r'"resourceVersion"\s*:\s*"\d+"')
_HIDDEN_MARKER = "***HIDDEN***"

# Token boundary pattern — splits on whitespace, quotes, commas, colons, equals
_TOKEN_SPLIT_RE = re.compile(r'[\s"\',:=\[\]{}()]+')


class EntropyDetector:
    """Detect high-entropy strings that are likely secrets."""

    DEFAULT_THRESHOLD: float = 4.0
    DEFAULT_MIN_LENGTH: int = 16
    HEX_THRESHOLD: float = 3.5
    BASE64_THRESHOLD: float = 4.5

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        min_length: int = DEFAULT_MIN_LENGTH,
    ) -> None:
        """Initialize entropy detector with configurable thresholds."""
        self.threshold = threshold
        self.min_length = min_length

    @staticmethod
    def shannon_entropy(data: str) -> float:
        """Calculate Shannon entropy of a string.

        Returns bits of entropy per character. Higher = more random.
        English text ~= 1.5-3.5, random base64 ~= 5.0-6.0.
        """
        if not data:
            return 0.0
        length = len(data)
        freq: dict[str, int] = {}
        for char in data:
            freq[char] = freq.get(char, 0) + 1
        entropy = 0.0
        for count in freq.values():
            prob = count / length
            if prob > 0:
                entropy -= prob * math.log2(prob)
        return entropy

    def _is_known_false_positive(self, token: str) -> bool:
        """Check if a high-entropy token is a known non-secret pattern."""
        # UUIDs
        if _UUID_RE.fullmatch(token):
            return True
        # SHA digests (docker image references)
        if _SHA_DIGEST_RE.search(token):
            return True
        if _DOCKER_IMAGE_DIGEST_RE.search(token):
            return True
        # K8s UIDs
        if _K8S_UID_RE.fullmatch(token):
            return True
        # Pure numeric strings (resource versions, timestamps)
        if token.isdigit():
            return True
        # ***HIDDEN*** marker
        if _HIDDEN_MARKER in token:
            return True
        # Hex-only strings that are exactly 32 or 40 chars (MD5, SHA1 hashes — common in K8s)
        stripped = token.lower()
        if all(c in '0123456789abcdef' for c in stripped) and len(stripped) in (32, 40, 64):
            return True
        return False

    def _is_base64_like(self, token: str) -> bool:
        """Check if string looks like base64 encoding."""
        b64_chars = set(string.ascii_letters + string.digits + '+/=')
        if len(token) < self.min_length:
            return False
        return sum(1 for c in token if c in b64_chars) / len(token) > 0.9

    def _is_hex_like(self, token: str) -> bool:
        """Check if string looks like hex encoding."""
        hex_chars = set('0123456789abcdefABCDEF')
        if len(token) < self.min_length:
            return False
        return all(c in hex_chars for c in token)

    def detect_in_text(self, text: str, context: str = "") -> list[tuple[int, int, float]]:
        """Find high-entropy substrings in text.

        Args:
            text: Input text to scan.
            context: Optional context hint (e.g., nearby key name).

        Returns:
            List of (start_pos, end_pos, entropy_value) for suspicious tokens.
        """
        detections: list[tuple[int, int, float]] = []

        # Split text into tokens and track positions
        for match in re.finditer(r'[^\s"\',:=\[\]{}()]+', text):
            token = match.group()
            start = match.start()
            end = match.end()

            if len(token) < self.min_length:
                continue
            if self._is_known_false_positive(token):
                continue

            entropy = self.shannon_entropy(token)

            # Use appropriate threshold based on encoding
            threshold = self.threshold
            if self._is_base64_like(token):
                threshold = self.BASE64_THRESHOLD
            elif self._is_hex_like(token):
                threshold = self.HEX_THRESHOLD

            # Lower threshold if context suggests a secret
            if context:
                secret_hints = ("key", "secret", "token", "password", "credential", "auth")
                if any(hint in context.lower() for hint in secret_hints):
                    threshold -= 0.5

            if entropy >= threshold:
                detections.append((start, end, entropy))

        return detections

    def redact_high_entropy(self, text: str, context: str = "") -> tuple[str, list[RedactionEntry]]:
        """Find and redact high-entropy tokens in text.

        Args:
            text: Input text to scan and redact.
            context: Optional context hint.

        Returns:
            Tuple of (redacted_text, list_of_redaction_entries).
        """
        detections = self.detect_in_text(text, context)
        if not detections:
            return text, []

        entries: list[RedactionEntry] = []
        # Process from right to left to preserve indices
        result = text
        for start, end, entropy in sorted(detections, key=lambda d: d[0], reverse=True):
            text[start:end]
            replacement = "[REDACTED:high-entropy]"
            result = result[:start] + replacement + result[end:]
            entries.append(RedactionEntry(
                pattern_name=f"high-entropy-string (H={entropy:.2f})",
                replacement=replacement,
                detector="entropy",
                category="high_entropy",
                confidence=min(0.5 + (entropy - self.threshold) * 0.2, 0.95),
            ))

        return result, entries

    def is_likely_secret(self, value: str, key_name: str = "") -> bool:
        """Heuristic: is this value likely a secret?

        Combines entropy with key name context.
        """
        if len(value) < 8:
            return False
        if _HIDDEN_MARKER in value:
            return False
        if self._is_known_false_positive(value):
            return False

        entropy = self.shannon_entropy(value)

        # Key name strongly suggests secret
        secret_keys = ("password", "passwd", "pwd", "secret", "token", "key", "credential", "auth")
        if any(hint in key_name.lower() for hint in secret_keys):
            return entropy > 2.5 or len(value) > 20

        # Pure entropy check
        return entropy >= self.threshold and len(value) >= self.min_length
