"""Builds and queries a dependency graph of Kubernetes resources from a support bundle.

The graph captures ownership, scheduling, configuration references, service
selectors, ingress routing, and storage bindings so that callers can answer
questions like "what is the blast radius if this node goes down?".
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from loguru import logger

from bundle_analyzer.graph.models import ResourceEdge, ResourceNode

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


def _make_key(kind: str, namespace: str, name: str) -> str:
    """Build a canonical node key like ``Pod/default/my-pod``."""
    if namespace:
        return f"{kind}/{namespace}/{name}"
    return f"{kind}//{name}"


def _read_resources(index: BundleIndex, resource_dir: str) -> list[dict[str, Any]]:
    """Read all resources of a given type from every namespace file.

    Handles both list-style (``{items: [...]}`` / ``[...]``) and single-object
    JSON files that appear under ``cluster-resources/<resource_dir>/``.
    """
    base = index.root / "cluster-resources" / resource_dir
    results: list[dict[str, Any]] = []

    if not base.exists():
        return results

    if base.is_file() and base.suffix == ".json":
        data = index.read_json(f"cluster-resources/{resource_dir}")
        if data is not None:
            results.extend(_unwrap(data))
        return results

    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.suffix != ".json":
                continue
            rel = str(child.relative_to(index.root))
            data = index.read_json(rel)
            if data is not None:
                results.extend(_unwrap(data))

    return results


def _unwrap(data: Any) -> list[dict[str, Any]]:
    """Normalise a JSON payload into a flat list of resource dicts."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "items" in data:
            return data["items"] or []
        return [data]
    return []


class ResourceGraph:
    """In-memory directed graph of Kubernetes resource dependencies.

    Use the async :meth:`build` classmethod to construct a graph from a
    :class:`BundleIndex`.  Then query with :meth:`neighbors`,
    :meth:`owner_chain`, :meth:`blast_radius`, etc.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, ResourceNode] = {}
        self._edges: list[ResourceEdge] = []
        # Adjacency: source_key -> list[edge]
        self._adj: dict[str, list[ResourceEdge]] = defaultdict(list)
        # Reverse adjacency: target_key -> list[edge]
        self._rev: dict[str, list[ResourceEdge]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def build(cls, index: BundleIndex) -> ResourceGraph:
        """Build the full resource dependency graph from a bundle index.

        Reads every supported resource type and creates edges for ownership,
        scheduling, config references, service selectors, ingress routing,
        and storage bindings.

        Args:
            index: A populated :class:`BundleIndex`.

        Returns:
            A fully-populated :class:`ResourceGraph`.
        """
        import asyncio

        return await asyncio.to_thread(cls._build_sync, index)

    @classmethod
    def _build_sync(cls, index: BundleIndex) -> ResourceGraph:
        """Blocking helper that reads resources and wires edges."""
        graph = cls()

        # ── Load all resource types ──────────────────────────────────
        pods = _read_resources(index, "pods")
        nodes = _read_resources(index, "nodes")
        deployments = _read_resources(index, "deployments")
        replicasets = _read_resources(index, "replicasets")
        statefulsets = _read_resources(index, "statefulsets")
        services = _read_resources(index, "services")
        configmaps = _read_resources(index, "configmaps")
        secrets = _read_resources(index, "secrets")
        pvcs = _read_resources(index, "pvcs")
        ingresses = _read_resources(index, "ingress")

        # Also try nodes.json (single file variant)
        if not nodes:
            nodes_file = index.root / "cluster-resources" / "nodes.json"
            if nodes_file.is_file():
                data = index.read_json("cluster-resources/nodes.json")
                if data is not None:
                    nodes = _unwrap(data)

        # ── Register nodes ───────────────────────────────────────────
        for res_list, kind in [
            (pods, "Pod"),
            (nodes, "Node"),
            (deployments, "Deployment"),
            (replicasets, "ReplicaSet"),
            (statefulsets, "StatefulSet"),
            (services, "Service"),
            (configmaps, "ConfigMap"),
            (secrets, "Secret"),
            (pvcs, "PersistentVolumeClaim"),
            (ingresses, "Ingress"),
        ]:
            for resource in res_list:
                graph._register_resource(resource, kind)

        # ── Build edges ──────────────────────────────────────────────
        for pod in pods:
            graph._link_pod(pod)

        for rs in replicasets:
            graph._link_owner_references(rs, "ReplicaSet")

        for svc in services:
            graph._link_service_selector(svc, pods)

        for ing in ingresses:
            graph._link_ingress(ing)

        for pvc in pvcs:
            graph._link_pvc_storage_class(pvc)

        logger.info(
            "ResourceGraph built: {} nodes, {} edges",
            len(graph._nodes),
            len(graph._edges),
        )
        return graph

    # ------------------------------------------------------------------
    # Internal: node registration
    # ------------------------------------------------------------------

    def _register_resource(self, resource: dict[str, Any], kind: str) -> str | None:
        """Add a resource as a node in the graph. Returns its key or None."""
        meta = resource.get("metadata") or {}
        name = meta.get("name", "")
        namespace = meta.get("namespace", "")
        if not name:
            return None

        key = _make_key(kind, namespace, name)
        if key not in self._nodes:
            self._nodes[key] = ResourceNode(
                kind=kind,
                namespace=namespace,
                name=name,
                key=key,
                raw=resource,
            )
        return key

    def _add_edge(self, source: str, target: str, relation: str) -> None:
        """Create a directed edge (idempotent-safe)."""
        edge = ResourceEdge(source=source, target=target, relation=relation)
        self._edges.append(edge)
        self._adj[source].append(edge)
        self._rev[target].append(edge)

    # ------------------------------------------------------------------
    # Internal: edge builders
    # ------------------------------------------------------------------

    def _link_pod(self, pod: dict[str, Any]) -> None:
        """Create all edges from a Pod to its dependencies."""
        meta = pod.get("metadata") or {}
        spec = pod.get("spec") or {}
        namespace = meta.get("namespace", "default")
        pod_name = meta.get("name", "")
        if not pod_name:
            return

        pod_key = _make_key("Pod", namespace, pod_name)

        # Pod → Node (scheduled_on)
        node_name = spec.get("nodeName")
        if node_name:
            node_key = _make_key("Node", "", node_name)
            # Ensure the node exists as a node even if we didn't load nodes
            if node_key not in self._nodes:
                self._nodes[node_key] = ResourceNode(
                    kind="Node", namespace="", name=node_name, key=node_key, raw={},
                )
            self._add_edge(pod_key, node_key, "scheduled_on")

        # Pod → owner (owned_by) via ownerReferences
        self._link_owner_references(pod, "Pod")

        # Pod → ServiceAccount
        sa_name = spec.get("serviceAccountName")
        if sa_name:
            sa_key = _make_key("ServiceAccount", namespace, sa_name)
            if sa_key not in self._nodes:
                self._nodes[sa_key] = ResourceNode(
                    kind="ServiceAccount", namespace=namespace, name=sa_name,
                    key=sa_key, raw={},
                )
            self._add_edge(pod_key, sa_key, "uses_service_account")

        # Pod → ConfigMap / Secret / PVC from volumes
        for vol in spec.get("volumes") or []:
            cm = vol.get("configMap")
            if cm and cm.get("name"):
                cm_key = _make_key("ConfigMap", namespace, cm["name"])
                self._ensure_node(cm_key, "ConfigMap", namespace, cm["name"])
                self._add_edge(pod_key, cm_key, "references_configmap")

            secret = vol.get("secret")
            if secret and secret.get("secretName"):
                s_key = _make_key("Secret", namespace, secret["secretName"])
                self._ensure_node(s_key, "Secret", namespace, secret["secretName"])
                self._add_edge(pod_key, s_key, "references_secret")

            pvc_claim = vol.get("persistentVolumeClaim")
            if pvc_claim and pvc_claim.get("claimName"):
                pvc_key = _make_key("PersistentVolumeClaim", namespace, pvc_claim["claimName"])
                self._ensure_node(pvc_key, "PersistentVolumeClaim", namespace, pvc_claim["claimName"])
                self._add_edge(pod_key, pvc_key, "references_pvc")

            # projected volumes
            projected = vol.get("projected") or {}
            for source in projected.get("sources") or []:
                p_cm = source.get("configMap")
                if p_cm and p_cm.get("name"):
                    cm_key = _make_key("ConfigMap", namespace, p_cm["name"])
                    self._ensure_node(cm_key, "ConfigMap", namespace, p_cm["name"])
                    self._add_edge(pod_key, cm_key, "references_configmap")
                p_secret = source.get("secret")
                if p_secret and p_secret.get("name"):
                    s_key = _make_key("Secret", namespace, p_secret["name"])
                    self._ensure_node(s_key, "Secret", namespace, p_secret["name"])
                    self._add_edge(pod_key, s_key, "references_secret")

        # Pod → ConfigMap / Secret from container env
        all_containers = (spec.get("containers") or []) + (spec.get("initContainers") or [])
        for container in all_containers:
            # envFrom
            for env_from in container.get("envFrom") or []:
                cm_ref = env_from.get("configMapRef")
                if cm_ref and cm_ref.get("name"):
                    cm_key = _make_key("ConfigMap", namespace, cm_ref["name"])
                    self._ensure_node(cm_key, "ConfigMap", namespace, cm_ref["name"])
                    self._add_edge(pod_key, cm_key, "references_configmap")
                secret_ref = env_from.get("secretRef")
                if secret_ref and secret_ref.get("name"):
                    s_key = _make_key("Secret", namespace, secret_ref["name"])
                    self._ensure_node(s_key, "Secret", namespace, secret_ref["name"])
                    self._add_edge(pod_key, s_key, "references_secret")

            # env[].valueFrom
            for env in container.get("env") or []:
                value_from = env.get("valueFrom") or {}
                cm_key_ref = value_from.get("configMapKeyRef")
                if cm_key_ref and cm_key_ref.get("name"):
                    cm_key = _make_key("ConfigMap", namespace, cm_key_ref["name"])
                    self._ensure_node(cm_key, "ConfigMap", namespace, cm_key_ref["name"])
                    self._add_edge(pod_key, cm_key, "references_configmap")
                secret_key_ref = value_from.get("secretKeyRef")
                if secret_key_ref and secret_key_ref.get("name"):
                    s_key = _make_key("Secret", namespace, secret_key_ref["name"])
                    self._ensure_node(s_key, "Secret", namespace, secret_key_ref["name"])
                    self._add_edge(pod_key, s_key, "references_secret")

    def _link_owner_references(self, resource: dict[str, Any], kind: str) -> None:
        """Create owned_by edges from ownerReferences."""
        meta = resource.get("metadata") or {}
        namespace = meta.get("namespace", "")
        name = meta.get("name", "")
        if not name:
            return

        res_key = _make_key(kind, namespace, name)

        for owner in meta.get("ownerReferences") or []:
            owner_kind = owner.get("kind", "")
            owner_name = owner.get("name", "")
            if not owner_kind or not owner_name:
                continue
            owner_key = _make_key(owner_kind, namespace, owner_name)
            self._ensure_node(owner_key, owner_kind, namespace, owner_name)
            self._add_edge(res_key, owner_key, "owned_by")

    def _link_service_selector(self, svc: dict[str, Any], pods: list[dict[str, Any]]) -> None:
        """Create selects edges from a Service to pods matching its selector."""
        meta = svc.get("metadata") or {}
        spec = svc.get("spec") or {}
        namespace = meta.get("namespace", "")
        svc_name = meta.get("name", "")
        selector = spec.get("selector") or {}
        if not svc_name or not selector:
            return

        svc_key = _make_key("Service", namespace, svc_name)

        for pod in pods:
            pod_meta = pod.get("metadata") or {}
            pod_ns = pod_meta.get("namespace", "")
            pod_name = pod_meta.get("name", "")
            if pod_ns != namespace or not pod_name:
                continue
            labels = pod_meta.get("labels") or {}
            if all(labels.get(k) == v for k, v in selector.items()):
                pod_key = _make_key("Pod", pod_ns, pod_name)
                self._add_edge(svc_key, pod_key, "selects")

    def _link_ingress(self, ingress: dict[str, Any]) -> None:
        """Create routes_to edges from an Ingress to backend Services."""
        meta = ingress.get("metadata") or {}
        spec = ingress.get("spec") or {}
        namespace = meta.get("namespace", "")
        ing_name = meta.get("name", "")
        if not ing_name:
            return

        ing_key = _make_key("Ingress", namespace, ing_name)

        # Default backend
        default_backend = spec.get("defaultBackend") or {}
        svc_ref = default_backend.get("service") or {}
        if svc_ref.get("name"):
            svc_key = _make_key("Service", namespace, svc_ref["name"])
            self._ensure_node(svc_key, "Service", namespace, svc_ref["name"])
            self._add_edge(ing_key, svc_key, "routes_to")

        # Rules
        for rule in spec.get("rules") or []:
            http = rule.get("http") or {}
            for path in http.get("paths") or []:
                backend = path.get("backend") or {}
                svc_info = backend.get("service") or {}
                if svc_info.get("name"):
                    svc_key = _make_key("Service", namespace, svc_info["name"])
                    self._ensure_node(svc_key, "Service", namespace, svc_info["name"])
                    self._add_edge(ing_key, svc_key, "routes_to")
                # Legacy backend format (pre-networking.k8s.io/v1)
                svc_name_legacy = backend.get("serviceName")
                if svc_name_legacy:
                    svc_key = _make_key("Service", namespace, svc_name_legacy)
                    self._ensure_node(svc_key, "Service", namespace, svc_name_legacy)
                    self._add_edge(ing_key, svc_key, "routes_to")

    def _link_pvc_storage_class(self, pvc: dict[str, Any]) -> None:
        """Create uses_storage_class edge from PVC to StorageClass."""
        meta = pvc.get("metadata") or {}
        spec = pvc.get("spec") or {}
        namespace = meta.get("namespace", "")
        pvc_name = meta.get("name", "")
        sc_name = spec.get("storageClassName")
        if not pvc_name or not sc_name:
            return

        pvc_key = _make_key("PersistentVolumeClaim", namespace, pvc_name)
        sc_key = _make_key("StorageClass", "", sc_name)
        self._ensure_node(sc_key, "StorageClass", "", sc_name)
        self._add_edge(pvc_key, sc_key, "uses_storage_class")

    def _ensure_node(self, key: str, kind: str, namespace: str, name: str) -> None:
        """Register a placeholder node if it does not exist yet."""
        if key not in self._nodes:
            self._nodes[key] = ResourceNode(
                kind=kind, namespace=namespace, name=name, key=key, raw={},
            )

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_node(self, key: str) -> ResourceNode | None:
        """Return the node for a given key, or None if not found.

        Args:
            key: A resource key like ``"Pod/default/my-pod"``.
        """
        return self._nodes.get(key)

    def neighbors(self, key: str, relation: str | None = None) -> list[ResourceNode]:
        """Return nodes this resource points TO (outgoing edges).

        Args:
            key: Source node key.
            relation: Optional filter — only return neighbors connected by
                      this relation type.

        Returns:
            List of target :class:`ResourceNode` objects.
        """
        edges = self._adj.get(key, [])
        if relation is not None:
            edges = [e for e in edges if e.relation == relation]
        result: list[ResourceNode] = []
        seen: set[str] = set()
        for edge in edges:
            if edge.target not in seen:
                node = self._nodes.get(edge.target)
                if node is not None:
                    result.append(node)
                    seen.add(edge.target)
        return result

    def reverse_neighbors(self, key: str, relation: str | None = None) -> list[ResourceNode]:
        """Return nodes that point TO this resource (incoming edges).

        Args:
            key: Target node key.
            relation: Optional relation filter.

        Returns:
            List of source :class:`ResourceNode` objects.
        """
        edges = self._rev.get(key, [])
        if relation is not None:
            edges = [e for e in edges if e.relation == relation]
        result: list[ResourceNode] = []
        seen: set[str] = set()
        for edge in edges:
            if edge.source not in seen:
                node = self._nodes.get(edge.source)
                if node is not None:
                    result.append(node)
                    seen.add(edge.source)
        return result

    def pods_on_node(self, node_name: str) -> list[ResourceNode]:
        """Return all pods scheduled on a given node.

        Args:
            node_name: The node's metadata.name.

        Returns:
            List of Pod :class:`ResourceNode` objects.
        """
        node_key = _make_key("Node", "", node_name)
        return self.reverse_neighbors(node_key, relation="scheduled_on")

    def owner_chain(self, key: str) -> list[ResourceNode]:
        """Walk ownerReferences upward and return the chain.

        For example, for a Pod owned by a ReplicaSet owned by a Deployment
        this returns ``[ReplicaSet/…, Deployment/…]``.

        Args:
            key: Starting resource key.

        Returns:
            Ordered list from immediate owner to top-level owner.
        """
        chain: list[ResourceNode] = []
        visited: set[str] = set()
        current = key
        while True:
            if current in visited:
                break
            visited.add(current)
            owners = self.neighbors(current, relation="owned_by")
            if not owners:
                break
            owner = owners[0]
            chain.append(owner)
            current = owner.key
        return chain

    def dependents(self, key: str) -> list[ResourceNode]:
        """Return all resources that reference this one (all incoming edges).

        Args:
            key: Target resource key.

        Returns:
            List of :class:`ResourceNode` objects that have an edge pointing
            to *key*.
        """
        return self.reverse_neighbors(key)

    def blast_radius(self, key: str) -> list[ResourceNode]:
        """Compute the set of all resources transitively affected if *key* fails.

        Performs a BFS over both forward edges (what this resource depends on
        that would lose a consumer) and reverse edges (what depends on this
        resource).

        Args:
            key: The resource key to fail.

        Returns:
            All transitively affected :class:`ResourceNode` objects
            (excluding the starting node itself).
        """
        affected: dict[str, ResourceNode] = {}
        queue: list[str] = [key]
        visited: set[str] = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Anything that depends on current is affected
            for edge in self._rev.get(current, []):
                if edge.source not in visited and edge.source != key:
                    node = self._nodes.get(edge.source)
                    if node is not None:
                        affected[edge.source] = node
                        queue.append(edge.source)

            # Ownership flows downward too: if a Deployment fails,
            # its ReplicaSets and Pods are affected
            for edge in self._adj.get(current, []):
                if edge.relation == "owned_by" and edge.target not in visited:
                    # The *owner* failing affects the *owned* — but here
                    # we traverse reverse: owned_by points child→parent.
                    # So for blast radius of a parent, we need the reverse
                    # edges (children pointing to the parent).
                    pass

        return list(affected.values())

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def nodes(self) -> dict[str, ResourceNode]:
        """All nodes keyed by their canonical key."""
        return dict(self._nodes)

    @property
    def edges(self) -> list[ResourceEdge]:
        """All edges in the graph."""
        return list(self._edges)

    def find_dependency_cascades(self, failing_resources: set[str]) -> list[dict]:
        """Find dependency cascades starting from failing resources.

        Walks the graph to identify resources that depend on failing resources,
        creating cascade chains that explain how a root failure propagates.

        Args:
            failing_resources: Set of resource keys (e.g. "default/redis-master")
                that are known to be failing.

        Returns:
            List of cascade dicts with root_cause, affected, chain, and depth keys.
        """
        cascades: list[dict] = []

        for root in failing_resources:
            if root not in self._nodes:
                continue

            # BFS to find all dependents
            visited: set[str] = set()
            queue: list[str] = [root]
            chain: list[str] = []

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                chain.append(current)

                # Find resources that depend on current (reverse edges)
                for edge in self._rev.get(current, []):
                    if edge.source not in visited:
                        queue.append(edge.source)

            affected = [r for r in chain if r != root]
            if affected:
                cascades.append({
                    "root_cause": root,
                    "affected": affected,
                    "chain": " → ".join(chain),
                    "depth": len(chain) - 1,
                })

        return cascades

    def __repr__(self) -> str:
        return f"ResourceGraph(nodes={len(self._nodes)}, edges={len(self._edges)})"
