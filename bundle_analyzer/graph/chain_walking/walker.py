"""ChainWalker facade — the public API for causal chain walking.

This is the main entry point. It holds state (index, triage, pod cache)
and delegates to the module-level functions in sibling modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import (
    CausalChain,
    DeploymentIssue,
    NodeIssue,
    PodIssue,
    TriageResult,
)

from .data_access import ensure_pod_index
from .dedup import deduplicate
from .deployment_helpers import parse_memory
from .issue_walkers import (
    walk_deployment_issue as _walk_deployment_issue,
)
from .issue_walkers import (
    walk_node_issue as _walk_node_issue,
)
from .issue_walkers import (
    walk_pod_issue as _walk_pod_issue,
)

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class ChainWalker:
    """Walks causal chains from symptoms to root causes using bundle data.

    Takes triage results and a BundleIndex, then applies deterministic
    reasoning patterns (exit-code analysis, resource checks, log pattern
    matching) to produce CausalChain objects.
    """

    def __init__(self, triage: TriageResult, index: BundleIndex) -> None:
        """Initialize the walker with triage results and bundle index.

        Args:
            triage: Aggregated triage findings from all scanners.
            index: The bundle index for reading raw Kubernetes JSON.
        """
        self._triage = triage
        self._index = index
        # Pre-index pod JSON for fast lookup
        self._pod_cache: dict[str, dict] = {}
        self._pods_indexed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def walk_all(self) -> list[CausalChain]:
        """Walk all triage findings and produce causal chains.

        Processes critical pods, warning pods, deployment issues, and
        node issues, then deduplicates chains sharing the same root cause.

        Returns:
            Deduplicated list of CausalChain objects.
        """
        self._ensure_pod_index()
        chains: list[CausalChain] = []

        for pod in self._triage.critical_pods + self._triage.warning_pods:
            chain = await self.walk_pod_issue(pod)
            if chain is not None:
                chains.append(chain)

        for dep in self._triage.deployment_issues:
            chain = await self.walk_deployment_issue(dep)
            if chain is not None:
                chains.append(chain)

        for node in self._triage.node_issues:
            chain = await self.walk_node_issue(node)
            if chain is not None:
                chains.append(chain)

        deduped = deduplicate(chains)
        logger.info(
            "ChainWalker produced {} chains ({} before dedup)",
            len(deduped),
            len(chains),
        )
        return deduped

    async def walk_pod_issue(self, issue: PodIssue) -> CausalChain | None:
        """Walk a single pod issue to produce a causal chain.

        Args:
            issue: The pod issue from triage.

        Returns:
            A CausalChain tracing the symptom, or None if no chain produced.
        """
        self._ensure_pod_index()
        return await _walk_pod_issue(
            issue, self._index, self._triage, self._pod_cache,
        )

    async def walk_deployment_issue(self, issue: DeploymentIssue) -> CausalChain | None:
        """Walk a deployment issue by examining its owned pods.

        Args:
            issue: The deployment issue from triage.

        Returns:
            A CausalChain for the deployment, or None if no chain produced.
        """
        self._ensure_pod_index()
        return await _walk_deployment_issue(
            issue, self._index, self._triage, self._pod_cache,
        )

    async def walk_node_issue(self, issue: NodeIssue) -> CausalChain | None:
        """Walk a node issue by checking resource pressure and pod scheduling.

        Args:
            issue: The node issue from triage.

        Returns:
            A CausalChain for the node issue, or None if no chain produced.
        """
        self._ensure_pod_index()
        return await _walk_node_issue(
            issue, self._triage, self._pod_cache,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_pod_index(self) -> None:
        """Build the pod cache from the bundle index if not already done."""
        self._pods_indexed = ensure_pod_index(
            self._index, self._pod_cache, self._pods_indexed,
        )

    @staticmethod
    def _parse_memory(value: str) -> int:
        """Parse a Kubernetes memory string to bytes (backward-compat shim).

        Args:
            value: The memory string (e.g. '128Mi', '1Gi').

        Returns:
            Memory in bytes, or 0 if unparseable.
        """
        return parse_memory(value)
