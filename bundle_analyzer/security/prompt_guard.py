"""Prompt injection detection and neutralization.

Log files and bundle data are UNTRUSTED INPUT that gets inserted into
LLM prompts. Attackers could embed instructions in logs, configmaps,
or annotations designed to manipulate the AI's analysis.

This guard detects and neutralizes such attempts while preserving
the diagnostic value of the content.
"""

from __future__ import annotations

import re

from loguru import logger

from bundle_analyzer.security.models import RedactionEntry


class PromptInjectionGuard:
    """Detect and neutralize prompt injection attempts in untrusted data."""

    # Each pattern: (name, compiled_regex, severity)
    # severity: "high" = very likely injection, "medium" = suspicious, "low" = might be benign
    INJECTION_PATTERNS: list[tuple[str, re.Pattern, str]] = [
        (
            "instruction_override",
            re.compile(r"(?i)(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|earlier|system)\s+(?:instructions|rules|prompts|guidelines)", re.MULTILINE),
            "high",
        ),
        (
            "role_switch",
            re.compile(r"(?i)(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|switch\s+(?:to|into)\s+(?:a\s+)?(?:different|new)\s+(?:role|mode|persona))", re.MULTILINE),
            "high",
        ),
        (
            "system_prompt_inject",
            re.compile(r"(?i)(?:^|\n)\s*(?:system|assistant|human)\s*:\s*", re.MULTILINE),
            "medium",
        ),
        (
            "prompt_leak_request",
            re.compile(r"(?i)(?:show|reveal|output|print|display|repeat)\s+(?:your|the|system)\s+(?:prompt|instructions|rules|system\s+message)", re.MULTILINE),
            "high",
        ),
        (
            "delimiter_escape",
            re.compile(r"```\s*(?:system|assistant|instructions|prompt)", re.MULTILINE),
            "high",
        ),
        (
            "xml_tag_inject",
            re.compile(r"<\s*(?:system|instructions|prompt|rules|assistant)[^>]*>", re.MULTILINE | re.IGNORECASE),
            "high",
        ),
        (
            "jailbreak_keywords",
            re.compile(r"(?i)\b(?:DAN|do\s+anything\s+now|developer\s+mode|unrestricted\s+mode|jailbreak|STAN|anti-AI)\b", re.MULTILINE),
            "medium",
        ),
        (
            "output_manipulation",
            re.compile(r"(?i)(?:always\s+respond\s+with|your\s+(?:response|output|answer)\s+(?:must|should|shall)\s+(?:be|start|contain|include))", re.MULTILINE),
            "medium",
        ),
        (
            "context_poisoning",
            re.compile(r"(?i)(?:the\s+(?:correct|real|true|actual)\s+(?:answer|analysis|root\s+cause|finding)\s+is)", re.MULTILINE),
            "low",
        ),
        (
            "encoding_evasion",
            re.compile(r"(?i)(?:base64\s*(?:decode|encoded)|eval\s*\(|exec\s*\()", re.MULTILINE),
            "medium",
        ),
    ]

    def scan(self, text: str) -> list[dict]:
        """Scan text for prompt injection patterns.

        Args:
            text: Text to scan (typically log content or bundle data).

        Returns:
            List of detection dicts: {name, severity, start, end, matched_text}.
        """
        detections: list[dict] = []
        for name, pattern, severity in self.INJECTION_PATTERNS:
            for match in pattern.finditer(text):
                detections.append({
                    "name": name,
                    "severity": severity,
                    "start": match.start(),
                    "end": match.end(),
                    "matched_text": match.group()[:100],  # truncate for safety
                })
        return detections

    def neutralize(self, text: str) -> tuple[str, list[RedactionEntry]]:
        """Neutralize detected injections by wrapping them in markers.

        Does NOT silently remove content — the pattern itself may be
        diagnostic (e.g., a log line that happens to contain "ignore previous").
        Instead, wraps detected patterns in [UNTRUSTED-INJECTION: ...] markers
        so the LLM sees the content but knows it's flagged.

        Args:
            text: Text to neutralize.

        Returns:
            Tuple of (neutralized_text, list_of_redaction_entries).
        """
        detections = self.scan(text)
        if not detections:
            return text, []

        entries: list[RedactionEntry] = []
        # Sort by position descending to preserve indices
        detections.sort(key=lambda d: d["start"], reverse=True)

        result = text
        for det in detections:
            start, end = det["start"], det["end"]
            original = result[start:end]
            wrapped = f"[UNTRUSTED-INJECTION({det['name']}): {original}]"
            result = result[:start] + wrapped + result[end:]

            entries.append(RedactionEntry(
                pattern_name=f"prompt-injection:{det['name']}",
                replacement=wrapped,
                detector="prompt_guard",
                category="prompt_injection",
                confidence={"high": 0.95, "medium": 0.7, "low": 0.4}.get(det["severity"], 0.5),
            ))
            logger.warning(
                "Prompt injection detected: type={} severity={} preview={}",
                det["name"],
                det["severity"],
                det["matched_text"][:50],
            )

        return result, entries

    def wrap_untrusted_content(self, content: str, source: str) -> str:
        """Wrap untrusted content with boundary markers for the LLM.

        This clearly separates system instructions from user-provided data
        in the prompt, making injection attempts less effective.

        Args:
            content: The untrusted content to wrap.
            source: Description of where this content came from.

        Returns:
            Content wrapped in boundary markers.
        """
        # First neutralize any injections
        neutralized, _ = self.neutralize(content)
        return (
            f"---BEGIN UNTRUSTED BUNDLE DATA ({source})---\n"
            f"{neutralized}\n"
            f"---END UNTRUSTED BUNDLE DATA---"
        )

    def is_suspicious(self, text: str) -> bool:
        """Quick check: does this text contain any injection patterns?"""
        return len(self.scan(text)) > 0
