"""Config scanner — detects missing ConfigMaps, Secrets, broken label selectors.

Cross-references resource dependencies to find dangling references
such as pods referencing non-existent ConfigMaps or Secrets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import ConfigIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class ConfigScanner:
    """Scans pods for missing ConfigMap/Secret references and broken Service endpoints.

    For each pod, extracts all ConfigMap and Secret references from envFrom,
    env.valueFrom, and volumes. Cross-references against actual resources in
    the bundle. Also checks Services for empty Endpoints.
    """

    async def scan(self, index: "BundleIndex") -> list[ConfigIssue]:
        """Scan all pods and services for config reference issues.

        Args:
            index: The bundle index providing access to pod, configmap, secret, and service data.

        Returns:
            A list of ConfigIssue objects for every missing reference found.
        """
        issues: list[ConfigIssue] = []

        namespaces = getattr(index, "namespaces", []) or []

        # Build lookup sets for existing ConfigMaps and Secrets per namespace
        existing_configmaps: dict[str, set[str]] = {}
        existing_secrets: dict[str, set[str]] = {}

        for ns in namespaces:
            existing_configmaps[ns] = self._get_resource_names(index, ns, "configmaps")
            existing_secrets[ns] = self._get_resource_names(index, ns, "secrets")

        # Check pod references
        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for config scan: {}", exc)
            pods = []

        for pod in pods:
            try:
                pod_issues = self._check_pod_references(
                    pod, existing_configmaps, existing_secrets,
                )
                issues.extend(pod_issues)
            except Exception as exc:
                name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.debug("Error checking config refs for pod {}: {}", name, exc)

        # Check services for empty endpoints
        for ns in namespaces:
            try:
                svc_issues = self._check_services(index, ns)
                issues.extend(svc_issues)
            except Exception as exc:
                logger.debug("Error checking services in {}: {}", ns, exc)

        logger.info("ConfigScanner found {} issues", len(issues))
        return issues

    def _get_resource_names(
        self, index: "BundleIndex", namespace: str, resource_type: str,
    ) -> set[str]:
        """Get a set of resource names for a given type in a namespace."""
        names: set[str] = set()
        try:
            data = index.read_json(f"cluster-resources/{resource_type}/{namespace}.json")
            if data is None:
                data = index.read_json(f"{namespace}/{resource_type}.json")
            if data is None:
                return names
            items = data if isinstance(data, list) else data.get("items", [])
            for item in items:
                name = item.get("metadata", {}).get("name")
                if name:
                    names.add(name)
        except Exception as exc:
            logger.debug("Could not read {} for {}: {}", resource_type, namespace, exc)
        return names

    def _check_pod_references(
        self,
        pod: dict,
        existing_configmaps: dict[str, set[str]],
        existing_secrets: dict[str, set[str]],
    ) -> list[ConfigIssue]:
        """Check a pod's spec for references to missing ConfigMaps/Secrets."""
        issues: list[ConfigIssue] = []
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        spec = pod.get("spec", {})

        cms = existing_configmaps.get(namespace, set())
        secrets = existing_secrets.get(namespace, set())

        # Check all containers (including init)
        all_containers = spec.get("containers", []) + spec.get("initContainers", [])
        for container in all_containers:
            # envFrom
            for env_from in container.get("envFrom", []):
                cm_ref = env_from.get("configMapRef")
                if cm_ref and cm_ref.get("name") and cm_ref["name"] not in cms:
                    # Only flag if optional is not True
                    if not cm_ref.get("optional", False):
                        issues.append(ConfigIssue(
                            namespace=namespace,
                            resource_type="ConfigMap",
                            resource_name=cm_ref["name"],
                            referenced_by=pod_name,
                            issue="missing",
                            confidence=0.95,
                            source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                            evidence_excerpt=f"container.envFrom.configMapRef.name={cm_ref['name']} not found in namespace {namespace}",
                        ))
                secret_ref = env_from.get("secretRef")
                if secret_ref and secret_ref.get("name") and secret_ref["name"] not in secrets:
                    if not secret_ref.get("optional", False):
                        issues.append(ConfigIssue(
                            namespace=namespace,
                            resource_type="Secret",
                            resource_name=secret_ref["name"],
                            referenced_by=pod_name,
                            issue="missing",
                            confidence=0.95,
                            source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                            evidence_excerpt=f"container.envFrom.secretRef.name={secret_ref['name']} not found in namespace {namespace}",
                        ))

            # env[].valueFrom
            for env in container.get("env", []):
                value_from = env.get("valueFrom", {})
                cm_key_ref = value_from.get("configMapKeyRef")
                if cm_key_ref and cm_key_ref.get("name"):
                    if not cm_key_ref.get("optional", False):
                        if cm_key_ref["name"] not in cms:
                            issues.append(ConfigIssue(
                                namespace=namespace,
                                resource_type="ConfigMap",
                                resource_name=cm_key_ref["name"],
                                referenced_by=pod_name,
                                issue="missing",
                                confidence=0.95,
                                source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                                evidence_excerpt=f"container.env.valueFrom.configMapKeyRef.name={cm_key_ref['name']} not found in namespace {namespace}",
                            ))
                secret_key_ref = value_from.get("secretKeyRef")
                if secret_key_ref and secret_key_ref.get("name"):
                    if not secret_key_ref.get("optional", False):
                        if secret_key_ref["name"] not in secrets:
                            issues.append(ConfigIssue(
                                namespace=namespace,
                                resource_type="Secret",
                                resource_name=secret_key_ref["name"],
                                referenced_by=pod_name,
                                issue="missing",
                                confidence=0.95,
                                source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                                evidence_excerpt=f"container.env.valueFrom.secretKeyRef.name={secret_key_ref['name']} not found in namespace {namespace}",
                            ))

        # Check volumes
        for volume in spec.get("volumes", []):
            cm = volume.get("configMap")
            if cm and cm.get("name") and cm["name"] not in cms:
                if not cm.get("optional", False):
                    issues.append(ConfigIssue(
                        namespace=namespace,
                        resource_type="ConfigMap",
                        resource_name=cm["name"],
                        referenced_by=pod_name,
                        issue="missing",
                        confidence=0.95,
                        source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                        evidence_excerpt=f"volumes.configMap.name={cm['name']} not found in namespace {namespace}",
                    ))
            secret = volume.get("secret")
            if secret and secret.get("secretName") and secret["secretName"] not in secrets:
                if not secret.get("optional", False):
                    issues.append(ConfigIssue(
                        namespace=namespace,
                        resource_type="Secret",
                        resource_name=secret["secretName"],
                        referenced_by=pod_name,
                        issue="missing",
                        confidence=0.95,
                        source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                        evidence_excerpt=f"volumes.secret.secretName={secret['secretName']} not found in namespace {namespace}",
                    ))
            projected = volume.get("projected", {})
            for source in projected.get("sources", []):
                cm_proj = source.get("configMap")
                if cm_proj and cm_proj.get("name") and cm_proj["name"] not in cms:
                    if not cm_proj.get("optional", False):
                        issues.append(ConfigIssue(
                            namespace=namespace,
                            resource_type="ConfigMap",
                            resource_name=cm_proj["name"],
                            referenced_by=pod_name,
                            issue="missing",
                            confidence=0.95,
                            source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                            evidence_excerpt=f"volumes.projected.configMap.name={cm_proj['name']} not found in namespace {namespace}",
                        ))
                secret_proj = source.get("secret")
                if secret_proj and secret_proj.get("name") and secret_proj["name"] not in secrets:
                    if not secret_proj.get("optional", False):
                        issues.append(ConfigIssue(
                            namespace=namespace,
                            resource_type="Secret",
                            resource_name=secret_proj["name"],
                            referenced_by=pod_name,
                            issue="missing",
                            confidence=0.95,
                            source_file=f"cluster-resources/pods/{namespace}/{pod_name}.json",
                            evidence_excerpt=f"volumes.projected.secret.name={secret_proj['name']} not found in namespace {namespace}",
                        ))

        return issues

    def _check_services(self, index: "BundleIndex", namespace: str) -> list[ConfigIssue]:
        """Check services for empty endpoints in a namespace."""
        issues: list[ConfigIssue] = []

        services = self._read_resources(index, namespace, "services")
        endpoints = self._read_resources(index, namespace, "endpoints")

        # Build endpoint lookup: name -> has addresses
        endpoint_map: dict[str, bool] = {}
        for ep in endpoints:
            ep_name = ep.get("metadata", {}).get("name", "")
            subsets = ep.get("subsets", [])
            has_addresses = any(
                s.get("addresses") for s in subsets
            ) if subsets else False
            endpoint_map[ep_name] = has_addresses

        for svc in services:
            svc_name = svc.get("metadata", {}).get("name", "")
            svc_type = svc.get("spec", {}).get("type", "ClusterIP")

            # Skip headless and ExternalName services
            if svc_type == "ExternalName":
                continue
            cluster_ip = svc.get("spec", {}).get("clusterIP", "")
            if cluster_ip == "None":
                continue  # headless

            # Check if this service has matching endpoints
            if svc_name in endpoint_map and not endpoint_map[svc_name]:
                issues.append(ConfigIssue(
                    namespace=namespace,
                    resource_type="Service",
                    resource_name=svc_name,
                    referenced_by=svc_name,
                    issue="missing",
                    missing_key=None,
                    confidence=0.7,
                    source_file=f"cluster-resources/services/{namespace}.json",
                    evidence_excerpt=f"Service {svc_name} endpoints have no ready addresses",
                ))

        return issues

    def _read_resources(
        self, index: "BundleIndex", namespace: str, resource_type: str,
    ) -> list[dict]:
        """Generic helper to read a list of resources."""
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
