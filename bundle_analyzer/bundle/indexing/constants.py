"""Constants for the bundle indexer."""

from __future__ import annotations

# Well-known sub-paths inside a Troubleshoot support bundle.
_KNOWN_DIRS: dict[str, str] = {
    "cluster-resources/pods": "pods",
    "cluster-resources/nodes": "nodes",
    "cluster-resources/deployments": "deployments",
    "cluster-resources/statefulsets": "statefulsets",
    "cluster-resources/services": "services",
    "cluster-resources/configmaps": "configmaps",
    "cluster-resources/secrets": "secrets",
    "cluster-resources/events": "events",
    "cluster-resources/replicasets": "replicasets",
    "cluster-resources/endpoints": "endpoints",
    "cluster-resources/pvcs": "pvcs",
    "cluster-resources/pvs": "pvs",
    "cluster-resources/ingress": "ingress",
    "cluster-resources/custom-resource-definitions": "crds",
    "cluster-resources/nodes.json": "nodes_json",
    "node-metrics": "node_metrics",
    "host-collectors": "host_collectors",
    "certificates": "certificates",
}

# Redaction marker used by Troubleshoot collectors.
REDACTED_MARKER: str = "***HIDDEN***"
