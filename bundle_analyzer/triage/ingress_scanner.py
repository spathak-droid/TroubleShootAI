"""Ingress scanner -- detects ingress misconfigurations.

Cross-references ingress backends against existing services,
checks port alignment, and validates TLS secret references.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import IngressIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class IngressScanner:
    """Scans ingress resources for misconfigurations.

    Detects backends referencing missing services, port mismatches
    between ingress and target services, and missing TLS secrets.
    """

    async def scan(self, index: "BundleIndex") -> list[IngressIssue]:
        """Scan all ingresses and return detected issues.

        Args:
            index: The bundle index providing access to ingress, service,
                   and secret data.

        Returns:
            A list of IngressIssue objects for every misconfiguration found.
        """
        issues: list[IngressIssue] = []
        namespaces = getattr(index, "namespaces", []) or []

        for ns in namespaces:
            try:
                ns_issues = self._scan_namespace(index, ns)
                issues.extend(ns_issues)
            except Exception as exc:
                logger.warning("Error scanning ingresses in namespace {}: {}", ns, exc)

        logger.info("IngressScanner found {} issues", len(issues))
        return issues

    def _scan_namespace(
        self, index: "BundleIndex", namespace: str,
    ) -> list[IngressIssue]:
        """Scan all ingresses in a single namespace."""
        issues: list[IngressIssue] = []

        ingresses = self._read_resources(index, namespace, "ingress")
        if not ingresses:
            return issues

        # Build lookup maps for services and secrets in this namespace
        services = self._read_resources(index, namespace, "services")
        secrets = self._read_resources(index, namespace, "secrets")

        service_map: dict[str, dict] = {}
        for svc in services:
            name = svc.get("metadata", {}).get("name", "")
            if name:
                service_map[name] = svc

        secret_names: set[str] = set()
        for secret in secrets:
            name = secret.get("metadata", {}).get("name", "")
            if name:
                secret_names.add(name)

        for ingress in ingresses:
            ingress_name = ingress.get("metadata", {}).get("name", "unknown")
            spec = ingress.get("spec", {})

            # Check default backend
            default_backend = spec.get("defaultBackend") or spec.get("backend")
            if default_backend:
                issues.extend(
                    self._check_backend(
                        default_backend, ingress_name, namespace,
                        service_map, "default backend",
                    )
                )

            # Check rules
            for rule in spec.get("rules", []):
                http = rule.get("http", {})
                for path_entry in http.get("paths", []):
                    backend = path_entry.get("backend", {})
                    path_str = path_entry.get("path", "/")
                    issues.extend(
                        self._check_backend(
                            backend, ingress_name, namespace,
                            service_map, f"path '{path_str}'",
                        )
                    )

            # Check TLS secrets
            for tls in spec.get("tls", []):
                secret_name = tls.get("secretName")
                if secret_name and secret_name not in secret_names:
                    issues.append(IngressIssue(
                        namespace=namespace,
                        ingress_name=ingress_name,
                        issue="missing_tls_secret",
                        message=(
                            f"Ingress '{ingress_name}' references TLS secret "
                            f"'{secret_name}' which does not exist in namespace "
                            f"'{namespace}'."
                        ),
                        severity="critical",
                    ))

        return issues

    def _check_backend(
        self,
        backend: dict,
        ingress_name: str,
        namespace: str,
        service_map: dict[str, dict],
        context: str,
    ) -> list[IngressIssue]:
        """Check a single backend reference for issues."""
        issues: list[IngressIssue] = []

        # networking.k8s.io/v1 format: backend.service.name / backend.service.port
        service_ref = backend.get("service", {})
        svc_name = service_ref.get("name") or backend.get("serviceName")
        svc_port = service_ref.get("port", {})
        port_number = svc_port.get("number") if isinstance(svc_port, dict) else None
        port_name = svc_port.get("name") if isinstance(svc_port, dict) else None

        # Legacy format
        if port_number is None and not port_name:
            port_number = backend.get("servicePort")
            if isinstance(port_number, str):
                port_name = port_number
                port_number = None

        if not svc_name:
            return issues

        if svc_name not in service_map:
            issues.append(IngressIssue(
                namespace=namespace,
                ingress_name=ingress_name,
                issue="missing_service",
                message=(
                    f"Ingress '{ingress_name}' {context} references service "
                    f"'{svc_name}' which does not exist in namespace '{namespace}'."
                ),
                severity="critical",
            ))
            return issues

        # Check port match
        svc = service_map[svc_name]
        svc_ports = svc.get("spec", {}).get("ports", [])
        if svc_ports and (port_number is not None or port_name is not None):
            port_found = False
            for sp in svc_ports:
                if port_number is not None and sp.get("port") == port_number:
                    port_found = True
                    break
                if port_name is not None and sp.get("name") == port_name:
                    port_found = True
                    break
            if not port_found:
                available = [
                    f"{sp.get('name', 'unnamed')}:{sp.get('port')}"
                    for sp in svc_ports
                ]
                issues.append(IngressIssue(
                    namespace=namespace,
                    ingress_name=ingress_name,
                    issue="port_mismatch",
                    message=(
                        f"Ingress '{ingress_name}' {context} targets "
                        f"port {port_number or port_name} on service '{svc_name}' "
                        f"but service only exposes: {', '.join(available)}."
                    ),
                    severity="warning",
                ))

        return issues

    def _read_resources(
        self, index: "BundleIndex", namespace: str, resource_type: str,
    ) -> list[dict]:
        """Read a list of resources from the bundle."""
        try:
            data = index.read_json(f"cluster-resources/{resource_type}/{namespace}.json")
            if data is None:
                data = index.read_json(f"{namespace}/{resource_type}.json")
            if data is None:
                return []
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.debug("Could not read {} for {}: {}", resource_type, namespace, exc)
            return []
