"""Storage scanner -- detects PVC, PV, and StorageClass issues.

Examines PVC phases, PV phases, and cross-references StorageClass
references to find pending volumes and orphaned resources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from bundle_analyzer.models import StorageIssue

if TYPE_CHECKING:
    from bundle_analyzer.bundle.indexer import BundleIndex


class StorageScanner:
    """Scans storage resources for issues.

    Detects PVCs stuck in Pending, PVCs referencing missing StorageClasses,
    and PVs in Released or Failed phase.
    """

    async def scan(self, index: BundleIndex) -> list[StorageIssue]:
        """Scan all storage resources and return detected issues.

        Args:
            index: The bundle index providing access to PVC, PV, and
                   StorageClass data.

        Returns:
            A list of StorageIssue objects for every storage problem found.
        """
        issues: list[StorageIssue] = []

        # Load StorageClasses
        storage_class_names = self._get_storage_class_names(index)

        # Scan PVCs per namespace
        namespaces = getattr(index, "namespaces", []) or []
        for ns in namespaces:
            try:
                pvc_issues = self._scan_pvcs(index, ns, storage_class_names)
                issues.extend(pvc_issues)
            except Exception as exc:
                logger.warning("Error scanning PVCs in namespace {}: {}", ns, exc)

        # Scan PVs (cluster-scoped)
        try:
            pv_issues = self._scan_pvs(index)
            issues.extend(pv_issues)
        except Exception as exc:
            logger.warning("Error scanning PVs: {}", exc)

        logger.info("StorageScanner found {} issues", len(issues))
        return issues

    def _get_storage_class_names(self, index: BundleIndex) -> set[str]:
        """Load the set of available StorageClass names."""
        names: set[str] = set()
        data = index.read_json("cluster-resources/storage-classes.json")
        if data is None:
            # Try alternative paths
            data = index.read_json("cluster-resources/storageclasses.json")
        if data is None:
            return names

        items: list[dict] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("items", [])

        for sc in items:
            name = sc.get("metadata", {}).get("name", "")
            if name:
                names.add(name)

        return names

    def _scan_pvcs(
        self,
        index: BundleIndex,
        namespace: str,
        storage_class_names: set[str],
    ) -> list[StorageIssue]:
        """Scan PVCs in a namespace for issues."""
        issues: list[StorageIssue] = []

        pvcs = self._read_resources(index, namespace, "pvcs")
        for pvc in pvcs:
            pvc_name = pvc.get("metadata", {}).get("name", "unknown")
            phase = pvc.get("status", {}).get("phase", "")
            sc_name = pvc.get("spec", {}).get("storageClassName", "")

            source = f"cluster-resources/pvcs/{namespace}.json"

            # PVC in Pending phase
            if phase == "Pending":
                message = f"PVC '{pvc_name}' in namespace '{namespace}' is stuck in Pending phase."
                conditions = pvc.get("status", {}).get("conditions", [])
                cond_excerpt = "status.phase=Pending"
                for cond in conditions:
                    if cond.get("message"):
                        message += f" {cond['message']}"
                        cond_excerpt += f", condition={cond.get('message', '')[:100]}"
                        break
                issues.append(StorageIssue(
                    namespace=namespace,
                    resource_name=pvc_name,
                    resource_type="PVC",
                    issue="pending",
                    message=message,
                    severity="critical",
                    source_file=source,
                    evidence_excerpt=cond_excerpt,
                ))

            # PVC referencing a StorageClass that doesn't exist
            if sc_name and storage_class_names and sc_name not in storage_class_names:
                issues.append(StorageIssue(
                    namespace=namespace,
                    resource_name=pvc_name,
                    resource_type="PVC",
                    issue="missing_storage_class",
                    message=(
                        f"PVC '{pvc_name}' references StorageClass '{sc_name}' "
                        f"which does not exist. Available: {sorted(storage_class_names)}."
                    ),
                    severity="critical",
                    source_file=source,
                    evidence_excerpt=f"spec.storageClassName={sc_name}, not in available classes",
                ))

        return issues

    def _scan_pvs(self, index: BundleIndex) -> list[StorageIssue]:
        """Scan PVs for Released or Failed phase."""
        issues: list[StorageIssue] = []

        pvs = self._read_pv_resources(index)
        for pv in pvs:
            pv_name = pv.get("metadata", {}).get("name", "unknown")
            phase = pv.get("status", {}).get("phase", "")

            if phase == "Released":
                issues.append(StorageIssue(
                    namespace="",
                    resource_name=pv_name,
                    resource_type="PV",
                    issue="released",
                    message=(
                        f"PV '{pv_name}' is in Released phase. Its data is still "
                        "intact but the PV cannot be rebound to a new PVC without "
                        "manual intervention."
                    ),
                    severity="warning",
                    source_file="cluster-resources/pvs.json",
                    evidence_excerpt="status.phase=Released",
                ))
            elif phase == "Failed":
                issues.append(StorageIssue(
                    namespace="",
                    resource_name=pv_name,
                    resource_type="PV",
                    issue="failed",
                    message=(
                        f"PV '{pv_name}' is in Failed phase. Automatic reclamation "
                        "has failed and manual recovery is needed."
                    ),
                    severity="critical",
                    source_file="cluster-resources/pvs.json",
                    evidence_excerpt="status.phase=Failed",
                ))

        return issues

    def _read_resources(
        self, index: BundleIndex, namespace: str, resource_type: str,
    ) -> list[dict]:
        """Read a list of namespaced resources from the bundle."""
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

    def _read_pv_resources(self, index: BundleIndex) -> list[dict]:
        """Read PV resources (cluster-scoped)."""
        try:
            # PVs may be in a single file or directory
            data = index.read_json("cluster-resources/pvs.json")
            if data is None:
                # Try reading from pvs directory
                pvs_dir = index.root / "cluster-resources" / "pvs"
                if pvs_dir.is_dir():
                    all_pvs: list[dict] = []
                    for f in pvs_dir.glob("*.json"):
                        file_data = index.read_json(str(f.relative_to(index.root)))
                        if isinstance(file_data, list):
                            all_pvs.extend(file_data)
                        elif isinstance(file_data, dict):
                            if "items" in file_data:
                                all_pvs.extend(file_data["items"] or [])
                            else:
                                all_pvs.append(file_data)
                    return all_pvs
                return []
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"] or []
            return []
        except Exception as exc:
            logger.debug("Could not read PVs: {}", exc)
            return []
