"""Pydantic v2 models for the resource dependency graph.

Defines the node and edge types used to represent Kubernetes resource
relationships within a support bundle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResourceNode(BaseModel):
    """A single Kubernetes resource in the dependency graph.

    Attributes:
        kind: The Kubernetes resource kind (e.g. "Pod", "Deployment").
        namespace: The namespace the resource lives in ("" for cluster-scoped).
        name: The resource name from metadata.name.
        key: A unique identifier in the form "Kind/namespace/name".
        raw: The original Kubernetes JSON for this resource.
    """

    kind: str
    namespace: str = ""
    name: str = ""
    key: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class ResourceEdge(BaseModel):
    """A directed relationship between two Kubernetes resources.

    Attributes:
        source: The key of the source node (e.g. "Pod/default/my-pod").
        target: The key of the target node (e.g. "Node//my-node").
        relation: The type of relationship (e.g. "scheduled_on", "owned_by").
    """

    source: str
    target: str
    relation: str
