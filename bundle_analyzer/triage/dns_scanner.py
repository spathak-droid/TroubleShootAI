"""DNS/CoreDNS scanner — detects DNS resolution failures, CoreDNS pod issues,
missing service endpoints, and CoreDNS configuration errors.

Examines CoreDNS pods in kube-system, pod logs for DNS lookup failures,
service/endpoint resources, and CoreDNS Corefile logs to produce findings
without requiring AI analysis.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import DNSIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex

# Regex patterns for DNS resolution errors in pod logs
_DNS_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"dial tcp: lookup .* on .*: no such host"),
    re.compile(r"could not resolve", re.IGNORECASE),
    re.compile(r"Name or service not known", re.IGNORECASE),
]

# Regex patterns for CoreDNS Corefile configuration errors
_COREFILE_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)error.*corefile"),
    re.compile(r"(?i)plugin/errors"),
    re.compile(r"(?i)failed to load corefile"),
    re.compile(r"(?i)no such plugin"),
    re.compile(r"(?i)syntax error"),
    re.compile(r"(?i)parse error"),
]

# Maximum log lines to scan per pod to avoid unbounded reads
_MAX_LOG_LINES = 500


class DNSScanner:
    """Scans a support bundle for DNS and CoreDNS issues.

    Detection rules:
    - CoreDNS pod failures (CrashLoopBackOff, not Ready) in kube-system
    - DNS resolution errors in pod logs across all namespaces
    - Services with missing or empty endpoints
    - CoreDNS Corefile configuration errors in coredns pod logs
    """

    async def scan(self, index: BundleIndex) -> list[DNSIssue]:
        """Scan the bundle for DNS-related issues.

        Args:
            index: The bundle index providing access to bundle resources.

        Returns:
            A list of DNSIssue objects for every DNS problem detected.
        """
        issues: list[DNSIssue] = []

        issues.extend(await self._scan_coredns_pods(index))
        issues.extend(await self._scan_dns_resolution_errors(index))
        issues.extend(await self._scan_missing_endpoints(index))
        issues.extend(await self._scan_coredns_config(index))

        logger.info("DNSScanner found {} issues", len(issues))
        return issues

    async def _scan_coredns_pods(self, index: BundleIndex) -> list[DNSIssue]:
        """Detect CoreDNS pods in kube-system that are failing or not ready."""
        issues: list[DNSIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for CoreDNS check: {}", exc)
            return issues

        for pod in pods:
            try:
                metadata = pod.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                pod_name = metadata.get("name", "unknown")

                # Only check kube-system coredns pods
                if namespace != "kube-system":
                    continue
                if "coredns" not in pod_name.lower():
                    continue

                status = pod.get("status", {})
                source_file = metadata.get("selfLink") or f"pods/{namespace}/{pod_name}"

                # Check for CrashLoopBackOff in container statuses
                for cs in status.get("containerStatuses", []):
                    waiting = cs.get("state", {}).get("waiting", {})
                    reason = waiting.get("reason", "")
                    if reason == "CrashLoopBackOff":
                        issues.append(DNSIssue(
                            namespace=namespace,
                            resource_name=pod_name,
                            issue_type="coredns_pod_failure",
                            message=f"CoreDNS pod {pod_name} is in CrashLoopBackOff",
                            severity="critical",
                            source_file=source_file,
                            evidence_excerpt=waiting.get("message", reason),
                            confidence=1.0,
                        ))

                    # Check if container is not ready
                    if not cs.get("ready", True):
                        restart_count = cs.get("restartCount", 0)
                        # Avoid duplicate if already caught as CrashLoopBackOff
                        if reason != "CrashLoopBackOff":
                            issues.append(DNSIssue(
                                namespace=namespace,
                                resource_name=pod_name,
                                issue_type="coredns_pod_failure",
                                message=(
                                    f"CoreDNS pod {pod_name} container "
                                    f"'{cs.get('name', 'unknown')}' is not Ready "
                                    f"(restarts: {restart_count})"
                                ),
                                severity="critical" if restart_count > 3 else "warning",
                                source_file=source_file,
                                evidence_excerpt=f"ready=false, restartCount={restart_count}",
                                confidence=0.95,
                            ))

                # Check pod phase for non-Running
                phase = status.get("phase", "")
                if phase not in ("Running", "Succeeded", ""):
                    issues.append(DNSIssue(
                        namespace=namespace,
                        resource_name=pod_name,
                        issue_type="coredns_pod_failure",
                        message=f"CoreDNS pod {pod_name} is in phase '{phase}'",
                        severity="critical" if phase == "Failed" else "warning",
                        source_file=source_file,
                        evidence_excerpt=f"phase={phase}",
                        confidence=0.9,
                    ))

            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.warning("Error checking CoreDNS pod {}: {}", pod_name, exc)

        return issues

    async def _scan_dns_resolution_errors(self, index: BundleIndex) -> list[DNSIssue]:
        """Scan pod logs across all namespaces for DNS resolution errors."""
        issues: list[DNSIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for DNS log scan: {}", exc)
            return issues

        for pod in pods:
            try:
                metadata = pod.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                pod_name = metadata.get("name", "unknown")
                status = pod.get("status", {})

                containers = [
                    cs.get("name", "unknown")
                    for cs in status.get("containerStatuses", [])
                ]
                if not containers:
                    # Fall back to spec containers
                    containers = [
                        c.get("name", "unknown")
                        for c in pod.get("spec", {}).get("containers", [])
                    ]

                for container_name in containers:
                    dns_errors = await self._check_log_for_dns_errors(
                        index, namespace, pod_name, container_name,
                    )
                    issues.extend(dns_errors)

            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.debug("Error scanning logs for pod {}: {}", pod_name, exc)

        return issues

    async def _check_log_for_dns_errors(
        self,
        index: BundleIndex,
        namespace: str,
        pod_name: str,
        container_name: str,
    ) -> list[DNSIssue]:
        """Check a specific container's logs for DNS resolution errors.

        Args:
            index: The bundle index.
            namespace: Pod namespace.
            pod_name: Pod name.
            container_name: Container name within the pod.

        Returns:
            List of DNSIssue for each distinct DNS error pattern found.
        """
        issues: list[DNSIssue] = []
        seen_patterns: set[str] = set()

        try:
            line_count = 0
            for line in index.stream_log(namespace, pod_name, container_name):
                line_count += 1
                if line_count > _MAX_LOG_LINES:
                    break

                for pattern in _DNS_ERROR_PATTERNS:
                    match = pattern.search(line)
                    if match and pattern.pattern not in seen_patterns:
                        seen_patterns.add(pattern.pattern)
                        log_path = f"pod-logs/{namespace}/{pod_name}/{container_name}.log"
                        excerpt = line.strip()[:300]
                        issues.append(DNSIssue(
                            namespace=namespace,
                            resource_name=pod_name,
                            issue_type="dns_resolution_error",
                            message=(
                                f"DNS resolution error in {pod_name}/{container_name}: "
                                f"{excerpt[:100]}"
                            ),
                            severity="warning",
                            source_file=log_path,
                            evidence_excerpt=excerpt,
                            confidence=0.9,
                        ))

        except (FileNotFoundError, OSError):
            # No logs available for this container — not an error
            pass
        except Exception as exc:
            logger.debug(
                "Could not read logs for {}/{}/{}: {}",
                namespace, pod_name, container_name, exc,
            )

        return issues

    async def _scan_missing_endpoints(self, index: BundleIndex) -> list[DNSIssue]:
        """Find services with empty endpoint lists indicating DNS will resolve but traffic fails."""
        issues: list[DNSIssue] = []

        for namespace in index.namespaces:
            # Check endpoints directory
            endpoints_dir = Path(index.root) / "cluster-resources" / "endpoints" / namespace
            services_dir = Path(index.root) / "cluster-resources" / "services" / namespace

            # Scan endpoints files for empty subsets
            try:
                if endpoints_dir.is_dir():
                    for ep_file in endpoints_dir.glob("*.json"):
                        try:
                            ep_data = index.read_json(
                                str(ep_file.relative_to(index.root))
                            )
                            ep_name = ep_data.get("metadata", {}).get("name", ep_file.stem)
                            subsets = ep_data.get("subsets", [])

                            if not subsets:
                                rel_path = str(ep_file.relative_to(index.root))
                                issues.append(DNSIssue(
                                    namespace=namespace,
                                    resource_name=ep_name,
                                    issue_type="missing_endpoints",
                                    message=(
                                        f"Service '{ep_name}' in namespace '{namespace}' "
                                        f"has no endpoints (empty subsets)"
                                    ),
                                    severity="warning",
                                    source_file=rel_path,
                                    evidence_excerpt="subsets: []",
                                    confidence=0.85,
                                ))
                        except Exception as exc:
                            logger.debug("Error reading endpoint file {}: {}", ep_file, exc)
            except Exception as exc:
                logger.debug("Error scanning endpoints in namespace {}: {}", namespace, exc)

            # Also check service JSON files for ClusterIP services without endpoints
            try:
                if services_dir.is_dir() and not endpoints_dir.is_dir():
                    for svc_file in services_dir.glob("*.json"):
                        try:
                            svc_data = index.read_json(
                                str(svc_file.relative_to(index.root))
                            )
                            svc_name = svc_data.get("metadata", {}).get("name", svc_file.stem)
                            svc_type = svc_data.get("spec", {}).get("type", "ClusterIP")
                            selector = svc_data.get("spec", {}).get("selector", {})

                            # Only flag services with selectors (headless and ExternalName are fine)
                            if svc_type == "ClusterIP" and selector:
                                # We already checked endpoints above; only flag here
                                # if no endpoints directory exists at all
                                rel_path = str(svc_file.relative_to(index.root))
                                issues.append(DNSIssue(
                                    namespace=namespace,
                                    resource_name=svc_name,
                                    issue_type="missing_endpoints",
                                    message=(
                                        f"Service '{svc_name}' in namespace '{namespace}' "
                                        f"has a selector but no endpoints data found in bundle"
                                    ),
                                    severity="info",
                                    source_file=rel_path,
                                    evidence_excerpt=f"selector={selector}, no endpoints dir",
                                    confidence=0.6,
                                ))
                        except Exception as exc:
                            logger.debug("Error reading service file {}: {}", svc_file, exc)
            except Exception as exc:
                logger.debug("Error scanning services in namespace {}: {}", namespace, exc)

        return issues

    async def _scan_coredns_config(self, index: BundleIndex) -> list[DNSIssue]:
        """Look for CoreDNS configuration errors in coredns pod logs."""
        issues: list[DNSIssue] = []

        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for CoreDNS config check: {}", exc)
            return issues

        for pod in pods:
            try:
                metadata = pod.get("metadata", {})
                namespace = metadata.get("namespace", "default")
                pod_name = metadata.get("name", "unknown")

                if namespace != "kube-system":
                    continue
                if "coredns" not in pod_name.lower():
                    continue

                status = pod.get("status", {})
                containers = [
                    cs.get("name", "unknown")
                    for cs in status.get("containerStatuses", [])
                ]
                if not containers:
                    containers = [
                        c.get("name", "unknown")
                        for c in pod.get("spec", {}).get("containers", [])
                    ]

                for container_name in containers:
                    config_issues = await self._check_coredns_log_for_config_errors(
                        index, namespace, pod_name, container_name,
                    )
                    issues.extend(config_issues)

            except Exception as exc:
                pod_name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.debug("Error checking CoreDNS config for {}: {}", pod_name, exc)

        return issues

    async def _check_coredns_log_for_config_errors(
        self,
        index: BundleIndex,
        namespace: str,
        pod_name: str,
        container_name: str,
    ) -> list[DNSIssue]:
        """Check CoreDNS container logs for Corefile configuration errors.

        Args:
            index: The bundle index.
            namespace: Pod namespace (expected kube-system).
            pod_name: CoreDNS pod name.
            container_name: Container name.

        Returns:
            List of DNSIssue for each config error pattern found.
        """
        issues: list[DNSIssue] = []
        seen_patterns: set[str] = set()

        try:
            line_count = 0
            for line in index.stream_log(namespace, pod_name, container_name):
                line_count += 1
                if line_count > _MAX_LOG_LINES:
                    break

                for pattern in _COREFILE_ERROR_PATTERNS:
                    match = pattern.search(line)
                    if match and pattern.pattern not in seen_patterns:
                        seen_patterns.add(pattern.pattern)
                        log_path = f"pod-logs/{namespace}/{pod_name}/{container_name}.log"
                        excerpt = line.strip()[:300]
                        issues.append(DNSIssue(
                            namespace=namespace,
                            resource_name=pod_name,
                            issue_type="coredns_config_error",
                            message=(
                                f"CoreDNS configuration error detected in {pod_name}: "
                                f"{excerpt[:100]}"
                            ),
                            severity="critical",
                            source_file=log_path,
                            evidence_excerpt=excerpt,
                            confidence=0.85,
                        ))

        except (FileNotFoundError, OSError):
            pass
        except Exception as exc:
            logger.debug(
                "Could not read CoreDNS logs for {}/{}/{}: {}",
                namespace, pod_name, container_name, exc,
            )

        return issues
