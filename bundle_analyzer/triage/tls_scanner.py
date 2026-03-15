"""TLS/Certificate scanner -- detects certificate errors and missing TLS secrets.

Scans pod logs for TLS handshake and certificate validation errors,
and cross-references ingress TLS secret references against existing secrets
in the bundle to detect missing TLS secrets.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import TLSIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Compiled patterns for TLS error detection in pod logs
_TLS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"x509:\s*certificate has expired", re.IGNORECASE),
        "cert_expired",
    ),
    (
        re.compile(r"tls:\s*bad certificate", re.IGNORECASE),
        "bad_certificate",
    ),
    (
        re.compile(r"certificate signed by unknown authority", re.IGNORECASE),
        "unknown_authority",
    ),
]

# Maximum number of log lines to scan per container to avoid excessive I/O
_MAX_LOG_LINES = 5000

# Truncate evidence excerpts to this length
_MAX_EVIDENCE_LENGTH = 200


class TLSScanner:
    """Scans pod logs for TLS/certificate errors and validates ingress TLS secrets.

    Detection covers:
    - Expired certificates (x509 errors in logs)
    - Bad certificate handshake failures
    - Certificates signed by unknown authorities
    - Missing TLS secrets referenced by Ingress resources
    """

    async def scan(self, index: "BundleIndex") -> list[TLSIssue]:
        """Scan the bundle for TLS-related issues.

        Examines pod logs for certificate error patterns and cross-references
        ingress TLS secret references against available secrets.

        Args:
            index: The bundle index providing access to pod, ingress,
                   secret, and log data.

        Returns:
            A list of TLSIssue objects for every TLS problem detected.
        """
        issues: list[TLSIssue] = []

        log_issues = await self._scan_pod_logs(index)
        issues.extend(log_issues)

        ingress_issues = await self._scan_ingress_tls_secrets(index)
        issues.extend(ingress_issues)

        logger.info("TLSScanner found {} issues", len(issues))
        return issues

    async def _scan_pod_logs(self, index: "BundleIndex") -> list[TLSIssue]:
        """Scan all pod logs for TLS error patterns.

        Iterates through every pod's containers and streams their logs,
        checking each line against known TLS error patterns.

        Args:
            index: The bundle index for accessing pods and logs.

        Returns:
            A list of TLSIssue objects from log-based detection.
        """
        issues: list[TLSIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for TLS log scan: {}", exc)
            return issues

        for pod in pods:
            try:
                pod_issues = self._scan_single_pod_logs(pod, index)
                issues.extend(pod_issues)
            except Exception as exc:
                pod_name = _safe_nested_get(pod, "metadata", "name") or "<unknown>"
                logger.warning("Error scanning TLS in pod {}: {}", pod_name, exc)

        return issues

    def _scan_single_pod_logs(
        self, pod: dict, index: "BundleIndex",
    ) -> list[TLSIssue]:
        """Scan logs of a single pod for TLS error patterns.

        Args:
            pod: The pod JSON dict from the bundle.
            index: The bundle index for streaming logs.

        Returns:
            A list of TLSIssue objects found in this pod's logs.
        """
        issues: list[TLSIssue] = []
        metadata = pod.get("metadata", {})
        status = pod.get("status", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")

        # Collect container names from containerStatuses and initContainerStatuses
        container_names: list[str] = []
        for cs in status.get("containerStatuses", []):
            name = cs.get("name")
            if name:
                container_names.append(name)
        for cs in status.get("initContainerStatuses", []):
            name = cs.get("name")
            if name:
                container_names.append(name)

        # Also check spec.containers if status is missing container info
        if not container_names:
            spec = pod.get("spec", {})
            for container in spec.get("containers", []):
                name = container.get("name")
                if name:
                    container_names.append(name)
            for container in spec.get("initContainers", []):
                name = container.get("name")
                if name:
                    container_names.append(name)

        # Track which issue types we already found per container to avoid duplicates
        seen: set[tuple[str, str]] = set()

        for container_name in container_names:
            try:
                line_count = 0
                for line in index.stream_log(namespace, pod_name, container_name):
                    line_count += 1
                    if line_count > _MAX_LOG_LINES:
                        break

                    for pattern, issue_type in _TLS_PATTERNS:
                        dedup_key = (container_name, issue_type)
                        if dedup_key in seen:
                            continue

                        if pattern.search(line):
                            seen.add(dedup_key)
                            excerpt = line.strip()[:_MAX_EVIDENCE_LENGTH]
                            severity = _severity_for_issue(issue_type)
                            source = f"pod-logs/{namespace}/{pod_name}/{container_name}"

                            issues.append(TLSIssue(
                                namespace=namespace,
                                resource_name=pod_name,
                                issue_type=issue_type,
                                message=_message_for_issue(
                                    issue_type, pod_name, container_name,
                                ),
                                severity=severity,
                                source_file=source,
                                evidence_excerpt=excerpt,
                                confidence=0.95,
                            ))
            except Exception as exc:
                logger.debug(
                    "Could not stream logs for {}/{}/{}: {}",
                    namespace, pod_name, container_name, exc,
                )

        return issues

    async def _scan_ingress_tls_secrets(
        self, index: "BundleIndex",
    ) -> list[TLSIssue]:
        """Check that TLS secrets referenced by Ingress resources exist.

        For each namespace, reads ingress resources and their spec.tls entries,
        then verifies the referenced secretName exists in the namespace.

        Args:
            index: The bundle index for accessing ingress and secret data.

        Returns:
            A list of TLSIssue objects for missing TLS secrets.
        """
        issues: list[TLSIssue] = []
        namespaces: list[str] = getattr(index, "namespaces", []) or []

        for ns in namespaces:
            try:
                ns_issues = self._check_namespace_ingress_tls(index, ns)
                issues.extend(ns_issues)
            except Exception as exc:
                logger.warning(
                    "Error checking ingress TLS secrets in namespace {}: {}", ns, exc,
                )

        return issues

    def _check_namespace_ingress_tls(
        self, index: "BundleIndex", namespace: str,
    ) -> list[TLSIssue]:
        """Check ingress TLS secret references in a single namespace.

        Args:
            index: The bundle index for reading resources.
            namespace: The namespace to scan.

        Returns:
            A list of TLSIssue objects for missing TLS secrets.
        """
        issues: list[TLSIssue] = []

        ingresses = self._read_resources(index, namespace, "ingress")
        if not ingresses:
            return issues

        # Build set of available secret names in this namespace
        secrets = self._read_resources(index, namespace, "secrets")
        secret_names: set[str] = set()
        for secret in secrets:
            name = _safe_nested_get(secret, "metadata", "name")
            if name:
                secret_names.add(name)

        for ingress in ingresses:
            ingress_name = _safe_nested_get(ingress, "metadata", "name") or "unknown"
            spec = ingress.get("spec", {})

            for tls_entry in spec.get("tls", []):
                secret_name = tls_entry.get("secretName")
                if not secret_name:
                    continue

                if secret_name not in secret_names:
                    hosts = tls_entry.get("hosts", [])
                    host_info = f" (hosts: {', '.join(hosts)})" if hosts else ""

                    issues.append(TLSIssue(
                        namespace=namespace,
                        resource_name=ingress_name,
                        issue_type="missing_tls_secret",
                        message=(
                            f"Ingress '{ingress_name}' references TLS secret "
                            f"'{secret_name}' which does not exist in namespace "
                            f"'{namespace}'{host_info}."
                        ),
                        severity="critical",
                        source_file=f"cluster-resources/ingress/{namespace}.json",
                        evidence_excerpt=f"spec.tls[].secretName: {secret_name}",
                        confidence=1.0,
                    ))

        return issues

    def _read_resources(
        self, index: "BundleIndex", namespace: str, resource_type: str,
    ) -> list[dict]:
        """Read a list of Kubernetes resources from the bundle.

        Tries common bundle path conventions and returns the items list.

        Args:
            index: The bundle index for reading JSON resources.
            namespace: The namespace to read from.
            resource_type: The resource kind directory name (e.g. 'ingress').

        Returns:
            A list of resource dicts, or an empty list if not found.
        """
        candidates = [
            f"cluster-resources/{resource_type}/{namespace}.json",
            f"{namespace}/{resource_type}.json",
        ]
        for path in candidates:
            try:
                data = index.read_json(path)
                if data is None:
                    continue
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "items" in data:
                    return data["items"] or []
            except Exception as exc:
                logger.debug(
                    "Could not read {} for {}: {}", resource_type, namespace, exc,
                )
        return []


def _severity_for_issue(issue_type: str) -> str:
    """Return the severity level for a given TLS issue type.

    Args:
        issue_type: One of the TLSIssue issue_type literals.

    Returns:
        A severity string: 'critical' or 'warning'.
    """
    if issue_type in ("cert_expired", "missing_tls_secret"):
        return "critical"
    return "warning"


def _message_for_issue(
    issue_type: str, pod_name: str, container_name: str,
) -> str:
    """Generate a human-readable message for a TLS log issue.

    Args:
        issue_type: The detected issue type.
        pod_name: Name of the affected pod.
        container_name: Name of the container where the error was found.

    Returns:
        A descriptive message string.
    """
    descriptions: dict[str, str] = {
        "cert_expired": "x509 certificate has expired",
        "bad_certificate": "TLS bad certificate during handshake",
        "unknown_authority": "certificate signed by unknown authority",
    }
    desc = descriptions.get(issue_type, "TLS error")
    return f"Pod '{pod_name}' container '{container_name}': {desc}"


def _safe_nested_get(d: dict, *keys: str) -> str | None:
    """Safely traverse nested dicts, returning None if any key is missing.

    Args:
        d: The root dict to traverse.
        *keys: Sequence of keys to follow.

    Returns:
        The string value at the nested path, or None.
    """
    current: object = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return str(current) if current is not None else None
