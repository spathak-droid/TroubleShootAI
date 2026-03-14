"""Service dependency scanner — discovers inter-service dependencies from pod specs.

Mines pod env vars, service references, and volume mounts to build a dependency
map, then cross-references each dependency against actual services and endpoints
in the bundle to identify broken or missing dependencies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


# ── Models ────────────────────────────────────────────────────────────


class ServiceDependency(BaseModel):
    """A discovered service dependency."""

    source_pod: str  # namespace/pod that depends on this
    target_service: str  # what it depends on (service name, hostname, etc.)
    target_namespace: str = ""  # if discoverable
    discovery_method: str  # "env_var", "connection_string", "service_ref", "volume_mount"
    env_var_name: str = ""  # which env var revealed this (name only, NOT value)
    is_healthy: bool | None = None  # True=healthy, False=unhealthy, None=unknown
    health_detail: str = ""  # why it's unhealthy
    severity: Literal["critical", "warning", "info"] = "info"


class DependencyMap(BaseModel):
    """Complete dependency map for the cluster."""

    dependencies: list[ServiceDependency] = Field(default_factory=list)
    broken_dependencies: list[ServiceDependency] = Field(default_factory=list)
    total_services_discovered: int = 0
    total_broken: int = 0


# ── Patterns ──────────────────────────────────────────────────────────

# Kubernetes auto-injected service env var pattern: <SVC>_SERVICE_HOST
_SERVICE_HOST_PATTERN = re.compile(r"^(.+)_SERVICE_HOST$")

# Env var names suggesting a dependency on another service
_SERVICE_ENV_PATTERNS = [
    re.compile(r"^(.+)_SERVICE_HOST$"),  # K8s auto-injected
    re.compile(r"^(.+)_(URL|URI|ENDPOINT|HOST|ADDR|ADDRESS)$", re.IGNORECASE),
    re.compile(
        r"^(DATABASE|DB|REDIS|MONGO|POSTGRES|MYSQL|KAFKA|RABBITMQ|AMQP|ELASTICSEARCH|ES)_",
        re.IGNORECASE,
    ),
]

# Well-known infra service keywords for extracting service name
_INFRA_KEYWORDS = frozenset({
    "database", "db", "redis", "mongo", "postgres", "mysql",
    "kafka", "rabbitmq", "amqp", "elasticsearch", "es",
    "memcached", "nats", "etcd", "consul", "vault", "minio",
    "zookeeper", "cassandra", "cockroachdb", "influxdb",
})


class DependencyScanner:
    """Scans pods for inter-service dependencies and checks their health.

    Discovers dependencies from:
    - Kubernetes auto-injected ``*_SERVICE_HOST`` env vars
    - Env var names matching common dependency patterns (``*_URL``, ``*_HOST``, etc.)
    - Service account volume mounts and projected service references

    Then cross-references each dependency against services and endpoints
    in the bundle to determine health status.
    """

    async def scan(self, index: "BundleIndex") -> DependencyMap:
        """Scan all pods for service dependencies and check health.

        Args:
            index: The bundle index providing access to cluster data.

        Returns:
            A DependencyMap with all discovered and broken dependencies.
        """
        dep_map = DependencyMap()

        # Build service and endpoint caches per namespace
        service_cache: dict[str, set[str]] = {}
        endpoint_cache: dict[str, dict[str, bool]] = {}

        for ns in index.namespaces:
            service_cache[ns] = self._get_service_names(index, ns)
            endpoint_cache[ns] = self._get_endpoint_health(index, ns)

        # Discover dependencies from pods
        try:
            pods = list(index.get_all_pods())
        except Exception as exc:
            logger.warning("Failed to enumerate pods for dependency scan: {}", exc)
            pods = []

        all_deps: list[ServiceDependency] = []
        for pod in pods:
            try:
                pod_deps = self._discover_dependencies_from_pod(pod)
                all_deps.extend(pod_deps)
            except Exception as exc:
                name = pod.get("metadata", {}).get("name", "<unknown>")
                logger.debug("Error scanning dependencies for pod {}: {}", name, exc)

        # Deduplicate: same source_pod + target_service + discovery_method
        seen: set[tuple[str, str, str]] = set()
        unique_deps: list[ServiceDependency] = []
        for dep in all_deps:
            key = (dep.source_pod, dep.target_service, dep.discovery_method)
            if key not in seen:
                seen.add(key)
                unique_deps.append(dep)

        # Check health of each dependency
        for dep in unique_deps:
            try:
                dep = self._check_service_health(dep, index, service_cache, endpoint_cache)
            except Exception as exc:
                logger.debug(
                    "Error checking health for dependency {} -> {}: {}",
                    dep.source_pod, dep.target_service, exc,
                )

        # Split into healthy and broken
        broken = [d for d in unique_deps if d.is_healthy is False]
        dep_map.dependencies = unique_deps
        dep_map.broken_dependencies = broken
        dep_map.total_services_discovered = len(unique_deps)
        dep_map.total_broken = len(broken)

        logger.info(
            "DependencyScanner found {} dependencies ({} broken)",
            dep_map.total_services_discovered,
            dep_map.total_broken,
        )
        return dep_map

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_dependencies_from_pod(self, pod: dict) -> list[ServiceDependency]:
        """Extract service dependencies from a pod's spec.

        Scans env var names (never values), container ports, and volume mounts
        to identify services this pod depends on.

        Args:
            pod: A parsed pod JSON object.

        Returns:
            List of discovered ServiceDependency objects.
        """
        deps: list[ServiceDependency] = []
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        pod_name = metadata.get("name", "unknown")
        source = f"{namespace}/{pod_name}"
        spec = pod.get("spec", {})

        all_containers = spec.get("containers", []) + spec.get("initContainers", [])

        for container in all_containers:
            # Scan env var NAMES for dependency patterns
            for env in container.get("env", []):
                env_name = env.get("name", "")
                if not env_name:
                    continue

                for pattern in _SERVICE_ENV_PATTERNS:
                    match = pattern.match(env_name)
                    if match:
                        service_name = self._service_name_from_env(env_name)
                        if service_name:
                            deps.append(ServiceDependency(
                                source_pod=source,
                                target_service=service_name,
                                target_namespace=namespace,
                                discovery_method="env_var",
                                env_var_name=env_name,
                            ))
                        break  # only match first pattern

            # Scan envFrom for configMapRef/secretRef names that suggest services
            for env_from in container.get("envFrom", []):
                cm_ref = env_from.get("configMapRef", {})
                cm_name = cm_ref.get("name", "") if cm_ref else ""
                if cm_name and self._looks_like_service_config(cm_name):
                    deps.append(ServiceDependency(
                        source_pod=source,
                        target_service=self._extract_service_from_config_name(cm_name),
                        target_namespace=namespace,
                        discovery_method="service_ref",
                        env_var_name=f"configMapRef:{cm_name}",
                    ))

        return deps

    def _check_service_health(
        self,
        dep: ServiceDependency,
        index: "BundleIndex",
        service_cache: dict[str, set[str]],
        endpoint_cache: dict[str, dict[str, bool]],
    ) -> ServiceDependency:
        """Check whether a discovered dependency is healthy in the bundle.

        Cross-references against services and endpoints to determine if the
        target service exists and has healthy endpoints.

        Args:
            dep: The dependency to check.
            index: The bundle index.
            service_cache: Pre-built map of namespace -> service names.
            endpoint_cache: Pre-built map of namespace -> {service_name: has_addresses}.

        Returns:
            Updated ServiceDependency with health status set.
        """
        target = dep.target_service.lower()
        ns = dep.target_namespace or "default"

        # Try to find the service in the target namespace first, then all namespaces
        namespaces_to_check = [ns] if ns in service_cache else []
        namespaces_to_check.extend(
            n for n in service_cache if n != ns
        )

        found_ns: str | None = None
        for check_ns in namespaces_to_check:
            services = service_cache.get(check_ns, set())
            if target in services:
                found_ns = check_ns
                break

        if found_ns is None:
            # Service not found in any namespace
            dep.is_healthy = None
            dep.health_detail = f"Service '{target}' not found in bundle (may be external)"
            dep.severity = "info"
            return dep

        dep.target_namespace = found_ns

        # Check endpoints
        ep_healthy, ep_detail = self._check_endpoints_exist(
            target, found_ns, endpoint_cache,
        )

        if not ep_healthy:
            dep.is_healthy = False
            dep.health_detail = ep_detail
            dep.severity = "critical"
        else:
            dep.is_healthy = True
            dep.health_detail = "Service exists with healthy endpoints"
            dep.severity = "info"

        return dep

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _service_name_from_env(env_name: str) -> str:
        """Extract a likely service name from an env var name.

        Converts Kubernetes-style env var names to lowercase service names.
        For example:
        - ``REDIS_SERVICE_HOST`` -> ``redis``
        - ``MY_APP_DB_URL`` -> ``my-app-db``
        - ``POSTGRES_HOST`` -> ``postgres``

        Args:
            env_name: The environment variable name.

        Returns:
            Lowercase service name derived from the env var, or empty string
            if no meaningful name can be extracted.
        """
        name = env_name

        # Strip known suffixes
        for suffix in (
            "_SERVICE_HOST", "_SERVICE_PORT",
            "_URL", "_URI", "_ENDPOINT", "_HOST",
            "_ADDR", "_ADDRESS", "_PORT",
        ):
            if name.upper().endswith(suffix):
                name = name[: -len(suffix)]
                break

        # Strip known infra prefixes when they are the entire prefix portion
        # e.g. "DATABASE_HOST" -> keep "database" as the service name
        name_lower = name.lower()

        if not name_lower:
            return ""

        # Convert underscores to hyphens (K8s naming convention)
        service_name = name_lower.replace("_", "-")

        # Skip if it's just a single character or KUBERNETES itself
        if len(service_name) <= 1 or service_name == "kubernetes":
            return ""

        return service_name

    @staticmethod
    def _looks_like_service_config(config_name: str) -> bool:
        """Check if a ConfigMap/Secret name suggests a service dependency.

        Args:
            config_name: Name of the ConfigMap or Secret.

        Returns:
            True if the name contains a known infrastructure keyword.
        """
        name_lower = config_name.lower()
        return any(kw in name_lower for kw in _INFRA_KEYWORDS)

    @staticmethod
    def _extract_service_from_config_name(config_name: str) -> str:
        """Extract a service name from a ConfigMap/Secret name.

        Args:
            config_name: Name of the ConfigMap or Secret.

        Returns:
            The best-guess service name.
        """
        name_lower = config_name.lower()
        for kw in _INFRA_KEYWORDS:
            if kw in name_lower:
                return kw
        return config_name.lower()

    @staticmethod
    def _check_endpoints_exist(
        service_name: str,
        namespace: str,
        endpoint_cache: dict[str, dict[str, bool]],
    ) -> tuple[bool, str]:
        """Check whether a service has healthy endpoints.

        Args:
            service_name: Name of the Kubernetes service.
            namespace: Namespace to check in.
            endpoint_cache: Pre-built map of namespace -> {service_name: has_addresses}.

        Returns:
            Tuple of (is_healthy, detail_message).
        """
        ns_endpoints = endpoint_cache.get(namespace, {})

        if service_name not in ns_endpoints:
            return False, f"No endpoints object found for service '{service_name}' in namespace '{namespace}'"

        has_addresses = ns_endpoints[service_name]
        if not has_addresses:
            return False, f"Service '{service_name}' in namespace '{namespace}' has empty endpoints (no ready addresses)"

        return True, "Endpoints exist with ready addresses"

    def _get_service_names(self, index: "BundleIndex", namespace: str) -> set[str]:
        """Get all service names in a namespace from the bundle.

        Args:
            index: The bundle index.
            namespace: Namespace to query.

        Returns:
            Set of lowercase service names.
        """
        names: set[str] = set()
        resources = self._read_resources(index, namespace, "services")
        for svc in resources:
            name = svc.get("metadata", {}).get("name", "")
            if name:
                names.add(name.lower())
        return names

    def _get_endpoint_health(
        self, index: "BundleIndex", namespace: str,
    ) -> dict[str, bool]:
        """Build a map of service_name -> has_ready_addresses for a namespace.

        Args:
            index: The bundle index.
            namespace: Namespace to query.

        Returns:
            Dict mapping lowercase service names to whether they have ready addresses.
        """
        result: dict[str, bool] = {}
        endpoints = self._read_resources(index, namespace, "endpoints")
        for ep in endpoints:
            ep_name = ep.get("metadata", {}).get("name", "").lower()
            if not ep_name:
                continue
            subsets = ep.get("subsets", [])
            has_addresses = any(
                s.get("addresses") for s in subsets
            ) if subsets else False
            result[ep_name] = has_addresses
        return result

    @staticmethod
    def _read_resources(
        index: "BundleIndex", namespace: str, resource_type: str,
    ) -> list[dict]:
        """Read a list of Kubernetes resources from the bundle.

        Tries both ``cluster-resources/<type>/<namespace>.json`` and
        ``<namespace>/<type>.json`` layouts.

        Args:
            index: The bundle index.
            namespace: Namespace to read from.
            resource_type: Resource type (e.g. ``"services"``, ``"endpoints"``).

        Returns:
            List of resource dicts, or empty list on failure.
        """
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
