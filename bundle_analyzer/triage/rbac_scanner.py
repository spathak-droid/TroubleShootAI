"""RBAC scanner -- detects permission and collection errors in the bundle.

Parses auth-cani-list files, collection error files, and RBAC errors
from the bundle index to identify permission gaps that may have prevented
full data collection or indicate cluster access control issues.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import RBACIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Standard K8s auth resources that most service accounts can't access.
# These are not real diagnostic issues and generate excessive noise.
_IGNORED_RESOURCES = frozenset({
    "selfsubjectaccessreviews",
    "selfsubjectrulesreviews",
    "selfsubjectreviews",
    "tokenreviews",
    "localsubjectaccessreviews",
})

# Patterns that indicate specific permission issues in error messages.
_PERMISSION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"cannot\s+(list|get|watch)\s+resource\s+\"(\w+)\"", re.IGNORECASE),
        "forbidden",
        "{verb} {resource}",
    ),
    (
        re.compile(r"is\s+forbidden.*?User.*?cannot\s+(\w+)\s+.*?\"(\w+)\"", re.IGNORECASE),
        "forbidden",
        "{verb} {resource}",
    ),
    (
        re.compile(r"Forbidden.*?(\w+)\s+on\s+(\w+)", re.IGNORECASE),
        "forbidden",
        "{verb} {resource}",
    ),
    (
        re.compile(r"unauthorized", re.IGNORECASE),
        "unauthorized",
        "",
    ),
]


def _classify_error(error_msg: str) -> tuple[str, str]:
    """Classify an error message and extract a suggested permission.

    Args:
        error_msg: The raw error message string.

    Returns:
        Tuple of (resource_type, suggested_permission).
    """
    for pattern, _category, suggestion_tpl in _PERMISSION_PATTERNS:
        match = pattern.search(error_msg)
        if match:
            groups = match.groups()
            verb = groups[0] if len(groups) > 0 else ""
            resource = groups[1] if len(groups) > 1 else ""
            suggested = suggestion_tpl.format(verb=verb, resource=resource) if suggestion_tpl else ""
            return resource or "unknown", suggested

    # Fallback: try to extract resource type from common error patterns
    resource_match = re.search(r"\"(\w+)\"", error_msg)
    resource_type = resource_match.group(1) if resource_match else "unknown"
    return resource_type, ""


class RBACScanner:
    """Scans for RBAC and permission errors in the support bundle.

    Examines:
    - auth-cani-list files for denied permissions
    - *-errors.json files in cluster-resources for collection failures
    - RBAC errors from the bundle index
    """

    async def scan(self, index: "BundleIndex") -> list[RBACIssue]:
        """Scan for RBAC and permission issues.

        Args:
            index: The bundle index providing access to bundle data.

        Returns:
            A list of RBACIssue objects for every permission problem found.
        """
        issues: list[RBACIssue] = []

        self._scan_auth_cani_list(index, issues)
        self._scan_error_files(index, issues)
        self._scan_index_rbac_errors(index, issues)

        logger.info("RBACScanner found {} issues", len(issues))
        return issues

    def _scan_auth_cani_list(
        self, index: "BundleIndex", issues: list[RBACIssue],
    ) -> None:
        """Parse auth-cani-list files for denied permissions.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        auth_dir = index.root / "cluster-resources" / "auth-cani-list"
        if not auth_dir.is_dir():
            return

        for ns_file in sorted(auth_dir.glob("*.json")):
            namespace = ns_file.stem
            try:
                data = index.read_json(str(ns_file.relative_to(index.root)))
                if data is None:
                    continue
                self._parse_cani_data(namespace, data, issues)
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning(
                    "Error parsing auth-cani-list for namespace {}: {}",
                    namespace, exc,
                )

    def _parse_cani_data(
        self,
        namespace: str,
        data: dict | list,
        issues: list[RBACIssue],
    ) -> None:
        """Parse a single auth-cani-list JSON file.

        Args:
            namespace: The namespace this file represents.
            data: Parsed JSON data (dict with status.resourceRules or list of rules).
            issues: List to append findings to.
        """
        rules: list[dict] = []
        if isinstance(data, dict):
            # Standard k8s SelfSubjectRulesReview format
            status = data.get("status", {})
            rules = status.get("resourceRules", [])
            if not rules:
                # Maybe it's a list of SubjectAccessReview results
                items = data.get("items", [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and not item.get("status", {}).get("allowed", True):
                            resource = item.get("spec", {}).get("resourceAttributes", {}).get("resource", "unknown")
                            verb = item.get("spec", {}).get("resourceAttributes", {}).get("verb", "")
                            issues.append(RBACIssue(
                                namespace=namespace,
                                resource_type=resource,
                                error_message=f"Permission denied: {verb} {resource}",
                                severity="warning",
                                suggested_permission=f"{verb} {resource}",
                            ))
        elif isinstance(data, list):
            rules = data

        # Check resource rules for denied verbs
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            verbs = rule.get("verbs", [])
            resources = rule.get("resources", [])
            # If the rule is explicitly non-resource or has restricted verbs
            # we look for missing critical verbs
            if isinstance(verbs, list) and isinstance(resources, list):
                # If verbs don't include "*" and miss critical ones
                if "*" not in verbs:
                    for resource in resources:
                        # Skip standard auth resources that are noisy
                        if resource.lower() in _IGNORED_RESOURCES:
                            continue
                        for needed_verb in ("get", "list"):
                            if needed_verb not in verbs:
                                issues.append(RBACIssue(
                                    namespace=namespace,
                                    resource_type=resource,
                                    error_message=(
                                        f"Missing '{needed_verb}' permission for "
                                        f"'{resource}' in namespace '{namespace}'"
                                    ),
                                    severity="info",
                                    suggested_permission=f"{needed_verb} {resource}",
                                ))

    def _scan_error_files(
        self, index: "BundleIndex", issues: list[RBACIssue],
    ) -> None:
        """Scan *-errors.json files in cluster-resources for collection failures.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        cr_dir = index.root / "cluster-resources"
        if not cr_dir.is_dir():
            return

        for error_file in sorted(cr_dir.glob("*-errors.json")):
            try:
                data = index.read_json(str(error_file.relative_to(index.root)))
                if data is None:
                    continue
                self._parse_error_json(error_file.stem, data, issues)
            except (ValueError, TypeError) as exc:
                logger.warning("Error parsing {}: {}", error_file.name, exc)

    def _parse_error_json(
        self,
        file_stem: str,
        data: dict | list,
        issues: list[RBACIssue],
    ) -> None:
        """Parse a single errors JSON file.

        Args:
            file_stem: The filename stem (e.g. "pods-errors").
            data: Parsed JSON data.
            issues: List to append findings to.
        """
        errors: list[str] = []
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, str):
                    errors.append(entry)
                elif isinstance(entry, dict):
                    errors.append(entry.get("error", entry.get("message", str(entry))))
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    errors.append(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            errors.append(item)
                        elif isinstance(item, dict):
                            errors.append(item.get("error", item.get("message", str(item))))

        # Extract resource type from filename (e.g. "pods-errors" -> "pods")
        resource_from_file = file_stem.replace("-errors", "").replace("_errors", "")

        for error_msg in errors:
            resource_type, suggested = _classify_error(error_msg)
            if resource_type == "unknown":
                resource_type = resource_from_file

            # Determine namespace from the error message if possible
            ns_match = re.search(r'namespace[s]?\s*[=:"\s]+(\S+)', error_msg, re.IGNORECASE)
            namespace = ns_match.group(1).strip('"\'') if ns_match else "cluster"

            severity: str = "critical" if "forbidden" in error_msg.lower() else "warning"

            issues.append(RBACIssue(
                namespace=namespace,
                resource_type=resource_type,
                error_message=error_msg,
                severity=severity,
                suggested_permission=suggested,
            ))

    def _scan_index_rbac_errors(
        self, index: "BundleIndex", issues: list[RBACIssue],
    ) -> None:
        """Process RBAC errors already collected by the bundle index.

        Args:
            index: The bundle index.
            issues: List to append findings to.
        """
        for error_msg in index.rbac_errors:
            resource_type, suggested = _classify_error(error_msg)

            # Try to extract namespace
            ns_match = re.search(r'namespace[s]?\s*[=:"\s]+(\S+)', error_msg, re.IGNORECASE)
            namespace = ns_match.group(1).strip('"\'') if ns_match else "cluster"

            severity: str = "critical" if "forbidden" in error_msg.lower() else "warning"

            issues.append(RBACIssue(
                namespace=namespace,
                resource_type=resource_type,
                error_message=error_msg,
                severity=severity,
                suggested_permission=suggested,
            ))
