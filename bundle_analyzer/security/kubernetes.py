"""Kubernetes-aware structural scrubbers for the Bundle Analyzer security layer.

Provides deep-structure-aware redaction for Kubernetes resource types (pods, nodes,
events, configmaps) and container log lines. Understands which fields are diagnostic
and must be preserved, and which may leak secrets or PII.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from loguru import logger

from bundle_analyzer.security.models import RedactionEntry

# PatternDetector may not be implemented yet — provide a minimal fallback.
try:
    from bundle_analyzer.security.patterns import PatternDetector  # type: ignore[import-untyped]

    _HAS_PATTERN_DETECTOR = True
except ImportError:
    _HAS_PATTERN_DETECTOR = False

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_HIDDEN_MARKER = "***HIDDEN***"

# Patterns that suggest a string contains a secret / credential
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)passwd\s*[:=]\s*\S+"),
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)token\s*[:=]\s*\S+"),
    re.compile(r"(?i)auth\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)connection[-_]?string\s*[:=]\s*\S+"),
    # Connection-string-style URIs
    re.compile(r"\w+://\S+:\S+@\S+"),
    # High-entropy base64 blobs (>=32 chars)
    re.compile(r"[A-Za-z0-9+/]{32,}={0,2}"),
    # JWTs
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Generic hex secrets (>=32 hex chars)
    re.compile(r"(?<![A-Fa-f0-9])[0-9a-fA-F]{32,}(?![A-Fa-f0-9])"),
]

# Internal registry hostname patterns
_INTERNAL_REGISTRY_RE = re.compile(
    r"^(?P<registry>"
    r"(?:\d{1,3}\.){3}\d{1,3}"              # private IP
    r"|[\w.-]+\.internal"                     # *.internal
    r"|[\w.-]+\.local"                        # *.local
    r"|[\w.-]+\.corp"                         # *.corp
    r")(?::\d+)?/"                            # optional port + slash
)

# File-path patterns for stack-trace redaction
_FILE_PATH_RE = re.compile(r"(/home/\S+|/Users/\S+|/app/\S+|/opt/\S+|/var/\S+\.py|/src/\S+)")


def _contains_hidden(value: Any) -> bool:
    """Return True if *value* is or contains the ***HIDDEN*** marker."""
    if isinstance(value, str):
        return _HIDDEN_MARKER in value
    return False


def _matches_secret_pattern(text: str) -> bool:
    """Return True if *text* matches any known secret pattern."""
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def _redact_secret_in_string(text: str, replacement: str = "[REDACTED]") -> tuple[str, bool]:
    """Replace secret-like substrings in *text*.  Returns (new_text, was_redacted)."""
    changed = False
    result = text
    for pat in _SECRET_PATTERNS:
        new_result = pat.sub(replacement, result)
        if new_result != result:
            changed = True
            result = new_result
    return result, changed


class KubernetesStructuralScrubber:
    """Kubernetes-aware structural scrubber.

    Walks Kubernetes resource dicts and redacts fields that may contain secrets,
    while carefully preserving fields that are diagnostically important.
    """

    # ------------------------------------------------------------------
    # Pod spec scrubbing
    # ------------------------------------------------------------------

    def scrub_pod_spec(self, pod_data: dict[str, Any]) -> tuple[dict[str, Any], list[RedactionEntry]]:
        """Scrub a pod spec, redacting env values, secret refs, command args, etc.

        Deep-copies the input so the caller's data is never mutated.

        Returns:
            A tuple of (scrubbed_pod, list_of_redaction_entries).
        """
        data = copy.deepcopy(pod_data)
        entries: list[RedactionEntry] = []

        spec = data.get("spec", {})

        # --- containers + initContainers ---
        for container_key in ("containers", "initContainers"):
            for container in spec.get(container_key, []):
                container_name = container.get("name", "<unknown>")

                # env values
                for env_item in container.get("env", []):
                    self._scrub_env_item(env_item, container_name, container_key, entries)

                # command / args
                for field in ("command", "args"):
                    items: list[str] | None = container.get(field)
                    if items is not None:
                        self._scrub_string_list(items, f"spec.{container_key}[{container_name}].{field}", entries)

                # image — internal registries
                image: str | None = container.get("image")
                if image and not _contains_hidden(image):
                    m = _INTERNAL_REGISTRY_RE.match(image)
                    if m:
                        registry = m.group("registry")
                        rest = image[m.end():]
                        container["image"] = f"[REDACTED:registry]/{rest}"
                        entries.append(RedactionEntry(
                            pattern_name="internal-registry-hostname",
                            replacement="[REDACTED:registry]",
                            detector="structural",
                            category="infrastructure",
                            location=f"spec.{container_key}[{container_name}].image",
                            confidence=1.0,
                        ))

        # --- volumes ---
        for vol in spec.get("volumes", []):
            secret_block = vol.get("secret", {})
            for item in secret_block.get("items", []):
                # Preserve key name; remove any embedded value
                if "value" in item and not _contains_hidden(item["value"]):
                    item.pop("value", None)

        # --- metadata.annotations ---
        annotations = data.get("metadata", {}).get("annotations")
        if annotations:
            self._scrub_annotation_values(annotations, "metadata.annotations", entries)

        # --- status.containers[].state.terminated.message ---
        status = data.get("status", {})
        for cs in status.get("containerStatuses", []):
            state = cs.get("state", {})
            terminated = state.get("terminated", {})
            msg = terminated.get("message")
            if msg and not _contains_hidden(msg) and _matches_secret_pattern(msg):
                terminated["message"] = "[REDACTED:terminated-message]"
                entries.append(RedactionEntry(
                    pattern_name="secret-in-terminated-message",
                    replacement="[REDACTED:terminated-message]",
                    detector="structural",
                    category="credential",
                    location="status.containerStatuses[].state.terminated.message",
                    confidence=0.9,
                ))

        logger.debug("Pod spec scrubbed: {} redactions", len(entries))
        return data, entries

    # ------------------------------------------------------------------
    # Node JSON scrubbing
    # ------------------------------------------------------------------

    def scrub_node_json(self, node_data: dict[str, Any]) -> tuple[dict[str, Any], list[RedactionEntry]]:
        """Scrub a Kubernetes node JSON resource.

        Redacts IP addresses, machine IDs, and annotation secrets while preserving
        conditions, capacity, allocatable, taints, and diagnostic nodeInfo fields.

        Returns:
            A tuple of (scrubbed_node, list_of_redaction_entries).
        """
        data = copy.deepcopy(node_data)
        entries: list[RedactionEntry] = []
        status = data.get("status", {})

        # --- addresses ---
        for addr in status.get("addresses", []):
            addr_type = addr.get("type", "")
            if addr_type in ("InternalIP", "ExternalIP"):
                original = addr.get("address", "")
                if original and not _contains_hidden(original):
                    addr["address"] = "[REDACTED:node-ip]"
                    entries.append(RedactionEntry(
                        pattern_name=f"node-{addr_type}",
                        replacement="[REDACTED:node-ip]",
                        detector="structural",
                        category="infrastructure",
                        location=f"status.addresses[{addr_type}]",
                        confidence=1.0,
                    ))

        # --- nodeInfo IDs ---
        node_info = status.get("nodeInfo", {})
        for id_field in ("machineID", "systemUUID", "bootID"):
            val = node_info.get(id_field)
            if val and not _contains_hidden(val):
                node_info[id_field] = f"[REDACTED:{id_field}]"
                entries.append(RedactionEntry(
                    pattern_name=f"node-{id_field}",
                    replacement=f"[REDACTED:{id_field}]",
                    detector="structural",
                    category="infrastructure",
                    location=f"status.nodeInfo.{id_field}",
                    confidence=1.0,
                ))

        # --- metadata.annotations ---
        annotations = data.get("metadata", {}).get("annotations")
        if annotations:
            self._scrub_annotation_values(annotations, "metadata.annotations", entries)

        logger.debug("Node JSON scrubbed: {} redactions", len(entries))
        return data, entries

    # ------------------------------------------------------------------
    # Event scrubbing
    # ------------------------------------------------------------------

    def scrub_event(self, event_data: dict[str, Any]) -> tuple[dict[str, Any], list[RedactionEntry]]:
        """Scrub a Kubernetes event resource.

        Scans the ``message`` field for embedded secrets/PII. Preserves reason,
        type, involvedObject, count, timestamps, and source.

        Returns:
            A tuple of (scrubbed_event, list_of_redaction_entries).
        """
        data = copy.deepcopy(event_data)
        entries: list[RedactionEntry] = []

        # --- message ---
        msg = data.get("message")
        if msg and not _contains_hidden(msg):
            new_msg, changed = _redact_secret_in_string(msg, "[REDACTED:event-secret]")
            if changed:
                data["message"] = new_msg
                entries.append(RedactionEntry(
                    pattern_name="secret-in-event-message",
                    replacement="[REDACTED:event-secret]",
                    detector="structural",
                    category="credential",
                    location="message",
                    confidence=0.8,
                ))

        # --- metadata.annotations ---
        annotations = data.get("metadata", {}).get("annotations")
        if annotations:
            self._scrub_annotation_values(annotations, "metadata.annotations", entries)

        logger.debug("Event scrubbed: {} redactions", len(entries))
        return data, entries

    # ------------------------------------------------------------------
    # ConfigMap scrubbing
    # ------------------------------------------------------------------

    def scrub_configmap_data(self, cm_data: dict[str, Any]) -> tuple[dict[str, Any], list[RedactionEntry]]:
        """Scrub a ConfigMap resource.

        Replaces ALL values in ``data`` with ``[REDACTED:configmap-value]`` while
        preserving key names and metadata.

        Returns:
            A tuple of (scrubbed_configmap, list_of_redaction_entries).
        """
        data = copy.deepcopy(cm_data)
        entries: list[RedactionEntry] = []

        cm_section = data.get("data")
        if cm_section and isinstance(cm_section, dict):
            for key in list(cm_section.keys()):
                val = cm_section[key]
                if _contains_hidden(val) if isinstance(val, str) else False:
                    continue  # preserve ***HIDDEN*** markers
                cm_section[key] = "[REDACTED:configmap-value]"
                entries.append(RedactionEntry(
                    pattern_name="configmap-value",
                    replacement="[REDACTED:configmap-value]",
                    detector="structural",
                    category="credential",
                    location=f"data.{key}",
                    confidence=1.0,
                ))

        logger.debug("ConfigMap scrubbed: {} redactions", len(entries))
        return data, entries

    # ------------------------------------------------------------------
    # Log-line scrubbing
    # ------------------------------------------------------------------

    def scrub_log_lines(
        self,
        lines: list[str],
        source: str = "",
    ) -> tuple[list[str], list[RedactionEntry]]:
        """Scrub a list of log lines, redacting secrets and internal file paths.

        Uses ``PatternDetector`` when available; falls back to built-in regex
        patterns otherwise. Lines containing ``***HIDDEN***`` pass through unchanged.

        Args:
            lines: Raw log lines.
            source: Optional source identifier for redaction entries.

        Returns:
            A tuple of (scrubbed_lines, list_of_redaction_entries).
        """
        scrubbed: list[str] = []
        entries: list[RedactionEntry] = []

        detector: Any = None
        if _HAS_PATTERN_DETECTOR:
            try:
                detector = PatternDetector()
            except Exception:
                logger.warning("Failed to instantiate PatternDetector; using fallback patterns")

        for idx, line in enumerate(lines):
            # Preserve ***HIDDEN*** lines untouched
            if _HIDDEN_MARKER in line:
                scrubbed.append(line)
                continue

            current = line

            # Pattern detection (via PatternDetector or fallback)
            if detector is not None:
                try:
                    result = detector.scan(current)
                    if hasattr(result, "redacted") and result.redacted != current:
                        current = result.redacted
                        for finding in getattr(result, "findings", []):
                            entries.append(RedactionEntry(
                                pattern_name=getattr(finding, "pattern_name", "pattern-match"),
                                replacement=getattr(finding, "replacement", "[REDACTED]"),
                                detector="pattern",
                                category=getattr(finding, "category", "credential"),
                                location=f"{source}:line-{idx + 1}" if source else f"line-{idx + 1}",
                                confidence=getattr(finding, "confidence", 0.9),
                            ))
                except Exception:
                    # Fall through to regex fallback
                    pass

            # Regex fallback / additional pass
            new_line, changed = _redact_secret_in_string(current, "[REDACTED:log-secret]")
            if changed:
                current = new_line
                entries.append(RedactionEntry(
                    pattern_name="secret-in-log-line",
                    replacement="[REDACTED:log-secret]",
                    detector="structural",
                    category="credential",
                    location=f"{source}:line-{idx + 1}" if source else f"line-{idx + 1}",
                    confidence=0.8,
                ))

            # Stack-trace file path redaction
            is_stack_trace = (
                current.lstrip().startswith("at ")
                or current.lstrip().startswith('File "')
                or current.lstrip().startswith("Traceback")
                or "/home/" in current
                or "/Users/" in current
            )
            if is_stack_trace:
                new_line = _FILE_PATH_RE.sub("[REDACTED:path]", current)
                if new_line != current:
                    current = new_line
                    entries.append(RedactionEntry(
                        pattern_name="internal-file-path",
                        replacement="[REDACTED:path]",
                        detector="structural",
                        category="infrastructure",
                        location=f"{source}:line-{idx + 1}" if source else f"line-{idx + 1}",
                        confidence=0.9,
                    ))

            scrubbed.append(current)

        logger.debug("Log lines scrubbed: {} lines, {} redactions", len(lines), len(entries))
        return scrubbed, entries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scrub_env_item(
        self,
        env_item: dict[str, Any],
        container_name: str,
        container_key: str,
        entries: list[RedactionEntry],
    ) -> None:
        """Scrub a single env var entry in-place."""
        env_name = env_item.get("name", "<unknown>")

        # Plain value
        val = env_item.get("value")
        if val is not None and not _contains_hidden(val):
            env_item["value"] = "[REDACTED:env-value]"
            entries.append(RedactionEntry(
                pattern_name="env-value",
                replacement="[REDACTED:env-value]",
                detector="structural",
                category="credential",
                location=f"spec.{container_key}[{container_name}].env[{env_name}].value",
                confidence=1.0,
            ))

        # valueFrom.secretKeyRef — keep .key, redact any embedded value
        value_from = env_item.get("valueFrom", {})
        secret_ref = value_from.get("secretKeyRef", {})
        if secret_ref:
            for subfield in list(secret_ref.keys()):
                if subfield not in ("name", "key", "optional"):
                    if not _contains_hidden(secret_ref.get(subfield, "")):
                        secret_ref[subfield] = "[REDACTED:secret-ref]"
                        entries.append(RedactionEntry(
                            pattern_name="secret-key-ref-value",
                            replacement="[REDACTED:secret-ref]",
                            detector="structural",
                            category="credential",
                            location=f"spec.{container_key}[{container_name}].env[{env_name}].valueFrom.secretKeyRef.{subfield}",
                            confidence=1.0,
                        ))

    def _scrub_string_list(
        self,
        items: list[str],
        location: str,
        entries: list[RedactionEntry],
    ) -> None:
        """Scan a list of strings (command/args) and redact secret patterns in-place."""
        for i, item in enumerate(items):
            if _contains_hidden(item):
                continue
            new_item, changed = _redact_secret_in_string(item, "[REDACTED:arg]")
            if changed:
                items[i] = new_item
                entries.append(RedactionEntry(
                    pattern_name="secret-in-command-arg",
                    replacement="[REDACTED:arg]",
                    detector="structural",
                    category="credential",
                    location=f"{location}[{i}]",
                    confidence=0.8,
                ))

    def _scrub_annotation_values(
        self,
        annotations: dict[str, str],
        location: str,
        entries: list[RedactionEntry],
    ) -> None:
        """Scan annotation values for secret patterns and redact matches in-place."""
        for key in list(annotations.keys()):
            val = annotations[key]
            if not isinstance(val, str) or _contains_hidden(val):
                continue
            if _matches_secret_pattern(val):
                annotations[key] = "[REDACTED:annotation-value]"
                entries.append(RedactionEntry(
                    pattern_name="secret-in-annotation",
                    replacement="[REDACTED:annotation-value]",
                    detector="structural",
                    category="credential",
                    location=f"{location}.{key}",
                    confidence=0.85,
                ))
