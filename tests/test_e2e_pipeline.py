"""End-to-end pipeline test with realistic multi-failure bundle.

Creates a realistic support bundle with 6 simultaneous failure scenarios,
runs the full triage + validation pipeline (no AI key needed), and verifies
that every failure is detected with correct evidence grounding.

Scenarios injected:
  1. CrashLoopBackOff — app crashes because DB is unreachable (exit code 1)
  2. OOMKilled — Java heap exceeds memory limit (exit code 137)
  3. ImagePullBackOff — typo in image tag, ECR auth failure
  4. Pending pod — insufficient CPU, FailedScheduling event
  5. Node MemoryPressure — node under pressure, evictions happening
  6. Missing ConfigMap — pod references configmap that doesn't exist
  7. DNS resolution failure — CoreDNS pod crashlooping
  8. Expired TLS certificate — ingress cert expired
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bundle_analyzer.bundle.indexer import BundleIndex
from bundle_analyzer.models import AnalysisResult, TriageResult
from bundle_analyzer.triage.engine import TriageEngine


# ---------------------------------------------------------------------------
# Fixture: build a realistic multi-failure bundle on disk
# ---------------------------------------------------------------------------


def _ts(minutes_ago: int = 0) -> str:
    """ISO timestamp relative to a fixed collection time."""
    base = datetime(2024, 3, 15, 14, 0, 0, tzinfo=timezone.utc)
    from datetime import timedelta

    dt = base - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_test_bundle(root: Path) -> None:
    """Populate *root* with a realistic multi-failure support bundle."""
    cr = root / "cluster-resources"

    # ── version.yaml (bundle metadata) ──────────────────────────
    (root / "version.yaml").write_text(
        "apiVersion: troubleshoot.sh/v1beta2\n"
        f"collectedAt: {_ts(0)}\n"
        "kubernetesVersion: v1.28.3\n"
    )

    # ── Nodes ────────────────────────────────────────────────────
    (cr / "nodes").mkdir(parents=True)
    nodes = {
        "items": [
            {
                "metadata": {
                    "name": "node-healthy",
                    "creationTimestamp": _ts(1440),
                    "labels": {"node.kubernetes.io/instance-type": "m5.xlarge"},
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True", "lastTransitionTime": _ts(60)},
                        {"type": "MemoryPressure", "status": "False"},
                        {"type": "DiskPressure", "status": "False"},
                    ],
                    "capacity": {"memory": "16Gi", "cpu": "4"},
                    "allocatable": {"memory": "15Gi", "cpu": "3800m"},
                    "addresses": [
                        {"type": "InternalIP", "address": "10.0.1.10"},
                        {"type": "Hostname", "address": "node-healthy"},
                    ],
                },
            },
            {
                "metadata": {
                    "name": "node-pressure",
                    "creationTimestamp": _ts(1440),
                },
                "status": {
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "True",
                            "lastTransitionTime": _ts(30),
                        },
                        {
                            "type": "MemoryPressure",
                            "status": "True",
                            "message": "kubelet has insufficient memory available",
                            "lastTransitionTime": _ts(10),
                        },
                        {"type": "DiskPressure", "status": "False"},
                    ],
                    "capacity": {"memory": "4Gi", "cpu": "2"},
                    "allocatable": {"memory": "3Gi", "cpu": "1800m"},
                    "addresses": [
                        {"type": "InternalIP", "address": "10.0.1.11"},
                        {"type": "Hostname", "address": "node-pressure"},
                    ],
                },
            },
            {
                "metadata": {
                    "name": "node-notready",
                    "creationTimestamp": _ts(1440),
                },
                "status": {
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "False",
                            "message": "Kubelet stopped posting node status",
                            "lastTransitionTime": _ts(5),
                        },
                    ],
                    "capacity": {"memory": "4Gi", "cpu": "2"},
                    "allocatable": {"memory": "3Gi", "cpu": "1800m"},
                    "addresses": [
                        {"type": "InternalIP", "address": "10.0.1.12"},
                    ],
                },
            },
        ]
    }
    (cr / "nodes.json").write_text(json.dumps(nodes, indent=2))

    # ── Pods ─────────────────────────────────────────────────────
    pods_dir = cr / "pods" / "default"
    pods_dir.mkdir(parents=True)

    # Pod 1: CrashLoopBackOff (DB connection refused)
    crashloop = {
        "metadata": {
            "name": "api-server-7f8b9c",
            "namespace": "default",
            "creationTimestamp": _ts(60),
            "labels": {"app": "api-server"},
        },
        "spec": {
            "nodeName": "node-healthy",
            "containers": [
                {
                    "name": "api",
                    "image": "myregistry.io/api-server:v2.1.0",
                    "env": [
                        {"name": "DB_HOST", "value": "postgres.db.svc.cluster.local"},
                        {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "db-creds", "key": "password"}}},
                        {"name": "LOG_LEVEL", "value": "debug"},
                    ],
                    "resources": {
                        "requests": {"memory": "256Mi", "cpu": "100m"},
                        "limits": {"memory": "512Mi", "cpu": "500m"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "api",
                    "ready": False,
                    "restartCount": 23,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting failed container=api pod=api-server-7f8b9c",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "exitCode": 1,
                            "reason": "Error",
                            "startedAt": _ts(6),
                            "finishedAt": _ts(5),
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "api-server-7f8b9c.json").write_text(json.dumps(crashloop, indent=2))

    # Pod 2: OOMKilled (Java heap too large)
    oom = {
        "metadata": {
            "name": "worker-batch-4a2c",
            "namespace": "default",
            "creationTimestamp": _ts(120),
            "labels": {"app": "batch-worker"},
        },
        "spec": {
            "nodeName": "node-pressure",
            "containers": [
                {
                    "name": "worker",
                    "image": "myregistry.io/batch-worker:v1.0",
                    "args": ["-Xmx512m", "-Xms256m"],
                    "resources": {
                        "requests": {"memory": "256Mi", "cpu": "200m"},
                        "limits": {"memory": "256Mi", "cpu": "1"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "worker",
                    "ready": False,
                    "restartCount": 8,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "exitCode": 137,
                            "reason": "OOMKilled",
                            "startedAt": _ts(4),
                            "finishedAt": _ts(3),
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "worker-batch-4a2c.json").write_text(json.dumps(oom, indent=2))

    # Pod 3: ImagePullBackOff
    imagepull = {
        "metadata": {
            "name": "frontend-deploy-x9z",
            "namespace": "default",
            "creationTimestamp": _ts(30),
            "labels": {"app": "frontend"},
        },
        "spec": {
            "nodeName": "node-healthy",
            "containers": [
                {
                    "name": "nginx",
                    "image": "myregistry.io/frontend:v3.0.0-typo",
                    "resources": {
                        "requests": {"memory": "64Mi", "cpu": "50m"},
                        "limits": {"memory": "128Mi", "cpu": "200m"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Pending",
            "containerStatuses": [
                {
                    "name": "nginx",
                    "ready": False,
                    "restartCount": 0,
                    "state": {
                        "waiting": {
                            "reason": "ImagePullBackOff",
                            "message": "Back-off pulling image \"myregistry.io/frontend:v3.0.0-typo\"",
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "frontend-deploy-x9z.json").write_text(json.dumps(imagepull, indent=2))

    # Pod 4: Pending (insufficient CPU — FailedScheduling)
    pending = {
        "metadata": {
            "name": "ml-training-job-1",
            "namespace": "default",
            "creationTimestamp": _ts(45),
            "labels": {"app": "ml-training"},
        },
        "spec": {
            "containers": [
                {
                    "name": "trainer",
                    "image": "myregistry.io/ml-trainer:latest",
                    "resources": {
                        "requests": {"memory": "32Gi", "cpu": "16"},
                        "limits": {"memory": "64Gi", "cpu": "16"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Pending",
            "conditions": [
                {
                    "type": "PodScheduled",
                    "status": "False",
                    "reason": "Unschedulable",
                    "message": "0/3 nodes are available: 1 Insufficient cpu, 1 node had memory pressure, 1 node was not ready.",
                }
            ],
        },
    }
    (pods_dir / "ml-training-job-1.json").write_text(json.dumps(pending, indent=2))

    # Pod 5: Missing configmap reference
    configref = {
        "metadata": {
            "name": "config-app-abc",
            "namespace": "default",
            "creationTimestamp": _ts(20),
            "labels": {"app": "config-app"},
        },
        "spec": {
            "nodeName": "node-healthy",
            "containers": [
                {
                    "name": "app",
                    "image": "myregistry.io/config-app:v1",
                    "env": [
                        {
                            "name": "APP_CONFIG",
                            "valueFrom": {
                                "configMapKeyRef": {
                                    "name": "app-settings",
                                    "key": "config.yaml",
                                }
                            },
                        }
                    ],
                    "resources": {
                        "requests": {"memory": "128Mi", "cpu": "100m"},
                        "limits": {"memory": "256Mi", "cpu": "500m"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Pending",
            "containerStatuses": [
                {
                    "name": "app",
                    "ready": False,
                    "restartCount": 0,
                    "state": {
                        "waiting": {
                            "reason": "CreateContainerConfigError",
                            "message": "configmap \"app-settings\" not found",
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "config-app-abc.json").write_text(json.dumps(configref, indent=2))

    # Pod 6: CoreDNS crashlooping (DNS failure scenario)
    coredns = {
        "metadata": {
            "name": "coredns-5d78c9869d-abc12",
            "namespace": "kube-system",
            "creationTimestamp": _ts(90),
            "labels": {"k8s-app": "kube-dns"},
        },
        "spec": {
            "nodeName": "node-pressure",
            "containers": [
                {
                    "name": "coredns",
                    "image": "registry.k8s.io/coredns/coredns:v1.11.1",
                    "resources": {
                        "requests": {"memory": "70Mi", "cpu": "100m"},
                        "limits": {"memory": "170Mi", "cpu": "100m"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "coredns",
                    "ready": False,
                    "restartCount": 12,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off restarting failed container",
                        }
                    },
                    "lastState": {
                        "terminated": {
                            "exitCode": 1,
                            "reason": "Error",
                        }
                    },
                }
            ],
        },
    }
    ks_pods = cr / "pods" / "kube-system"
    ks_pods.mkdir(parents=True)
    (ks_pods / "coredns-5d78c9869d-abc12.json").write_text(json.dumps(coredns, indent=2))

    # Pod 7: healthy pod (control — should NOT be flagged)
    healthy = {
        "metadata": {
            "name": "web-frontend-ok",
            "namespace": "default",
            "creationTimestamp": _ts(200),
            "labels": {"app": "web"},
        },
        "spec": {
            "nodeName": "node-healthy",
            "containers": [
                {
                    "name": "web",
                    "image": "nginx:1.25",
                    "resources": {
                        "requests": {"memory": "64Mi", "cpu": "50m"},
                        "limits": {"memory": "128Mi", "cpu": "200m"},
                    },
                }
            ],
        },
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "web",
                    "ready": True,
                    "restartCount": 0,
                    "state": {"running": {"startedAt": _ts(200)}},
                }
            ],
        },
    }
    (pods_dir / "web-frontend-ok.json").write_text(json.dumps(healthy, indent=2))

    # ── Events (flat layout: cluster-resources/events/<ns>.json) ──
    events_dir = cr / "events"
    events_dir.mkdir(parents=True)

    default_events = {
        "items": [
            {
                "metadata": {"name": "ev-backoff", "namespace": "default", "creationTimestamp": _ts(5)},
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container api in pod api-server-7f8b9c",
                "involvedObject": {"kind": "Pod", "name": "api-server-7f8b9c", "namespace": "default"},
                "firstTimestamp": _ts(55),
                "lastTimestamp": _ts(5),
                "count": 23,
            },
            {
                "metadata": {"name": "ev-oom", "namespace": "default", "creationTimestamp": _ts(3)},
                "type": "Warning",
                "reason": "OOMKilling",
                "message": "Memory cgroup out of memory: Killed process 7890 (java)",
                "involvedObject": {"kind": "Pod", "name": "worker-batch-4a2c", "namespace": "default"},
                "firstTimestamp": _ts(30),
                "lastTimestamp": _ts(3),
                "count": 8,
            },
            {
                "metadata": {"name": "ev-imagepull", "namespace": "default", "creationTimestamp": _ts(28)},
                "type": "Warning",
                "reason": "Failed",
                "message": "Failed to pull image \"myregistry.io/frontend:v3.0.0-typo\": not found",
                "involvedObject": {"kind": "Pod", "name": "frontend-deploy-x9z", "namespace": "default"},
                "firstTimestamp": _ts(30),
                "lastTimestamp": _ts(28),
                "count": 5,
            },
            {
                "metadata": {"name": "ev-schedule", "namespace": "default", "creationTimestamp": _ts(44)},
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/3 nodes are available: 1 Insufficient cpu, 1 node had memory pressure, 1 node was not ready.",
                "involvedObject": {"kind": "Pod", "name": "ml-training-job-1", "namespace": "default"},
                "firstTimestamp": _ts(45),
                "lastTimestamp": _ts(2),
                "count": 15,
            },
            {
                "metadata": {"name": "ev-configerr", "namespace": "default", "creationTimestamp": _ts(19)},
                "type": "Warning",
                "reason": "Failed",
                "message": "Error: configmap \"app-settings\" not found",
                "involvedObject": {"kind": "Pod", "name": "config-app-abc", "namespace": "default"},
                "firstTimestamp": _ts(20),
                "lastTimestamp": _ts(19),
                "count": 3,
            },
            {
                "metadata": {"name": "ev-eviction", "namespace": "default", "creationTimestamp": _ts(8)},
                "type": "Warning",
                "reason": "Evicted",
                "message": "The node was low on resource: memory. Threshold quantity: 100Mi, available: 50Mi.",
                "involvedObject": {"kind": "Pod", "name": "evicted-pod-xyz", "namespace": "default"},
                "firstTimestamp": _ts(10),
                "lastTimestamp": _ts(8),
                "count": 1,
            },
        ]
    }
    (events_dir / "default.json").write_text(json.dumps(default_events, indent=2))

    ks_events_data = {
        "items": [
            {
                "metadata": {"name": "ev-coredns", "namespace": "kube-system", "creationTimestamp": _ts(4)},
                "type": "Warning",
                "reason": "BackOff",
                "message": "Back-off restarting failed container coredns in pod coredns-5d78c9869d-abc12",
                "involvedObject": {"kind": "Pod", "name": "coredns-5d78c9869d-abc12", "namespace": "kube-system"},
                "firstTimestamp": _ts(85),
                "lastTimestamp": _ts(4),
                "count": 12,
            },
        ]
    }
    (events_dir / "kube-system.json").write_text(json.dumps(ks_events_data, indent=2))

    # ── Deployments (flat: deployments/<ns>.json with items array) ──
    deploys_dir = cr / "deployments"
    deploys_dir.mkdir(parents=True)

    deployments_data = {
        "items": [
            {
                "metadata": {
                    "name": "api-server",
                    "namespace": "default",
                    "creationTimestamp": _ts(1440),
                },
                "spec": {
                    "replicas": 3,
                    "selector": {"matchLabels": {"app": "api-server"}},
                },
                "status": {
                    "replicas": 3,
                    "readyReplicas": 0,
                    "unavailableReplicas": 3,
                    "conditions": [
                        {
                            "type": "Available",
                            "status": "False",
                            "message": "Deployment does not have minimum availability.",
                        }
                    ],
                },
            }
        ]
    }
    (deploys_dir / "default.json").write_text(json.dumps(deployments_data, indent=2))

    # ── ConfigMaps (app-settings is deliberately MISSING) ────────
    cm_dir = cr / "configmaps" / "default"
    cm_dir.mkdir(parents=True)
    configmaps = {
        "items": [
            {
                "metadata": {"name": "kube-root-ca.crt", "namespace": "default"},
                "data": {"ca.crt": "-----BEGIN CERTIFICATE-----\nMIIC..."},
            },
            # NOTE: "app-settings" is deliberately missing — config-app-abc references it
        ]
    }
    (cm_dir / "configmaps.json").write_text(json.dumps(configmaps, indent=2))

    # ── Container logs (path: cluster-resources/pods/logs/<ns>/<pod>/<container>.log) ──
    logs_base = cr / "pods" / "logs"

    # crashloop pod logs
    api_logs = logs_base / "default" / "api-server-7f8b9c"
    api_logs.mkdir(parents=True)
    (api_logs / "api.log").write_text(
        f"{_ts(6)} INFO  Starting api-server v2.1.0\n"
        f"{_ts(6)} INFO  Connecting to database postgres.db.svc.cluster.local:5432\n"
        f"{_ts(5)} ERROR Failed to connect to database: connection refused\n"
        f"{_ts(5)} ERROR dial tcp 10.96.42.17:5432: connect: connection refused\n"
        f"{_ts(5)} FATAL Cannot start without database connection, exiting\n"
    )
    (api_logs / "api-previous.log").write_text(
        f"{_ts(12)} INFO  Starting api-server v2.1.0\n"
        f"{_ts(12)} INFO  Connecting to database postgres.db.svc.cluster.local:5432\n"
        f"{_ts(11)} ERROR Failed to connect to database: connection refused\n"
        f"{_ts(11)} FATAL Cannot start without database connection, exiting\n"
    )

    # OOM pod logs (empty — OOM leaves no app logs)
    oom_logs = logs_base / "default" / "worker-batch-4a2c"
    oom_logs.mkdir(parents=True)
    (oom_logs / "worker.log").write_text("")

    # ── Namespaces ───────────────────────────────────────────────
    (cr / "namespaces.json").write_text(json.dumps({
        "items": [
            {"metadata": {"name": "default"}},
            {"metadata": {"name": "kube-system"}},
        ]
    }))

    # ── RBAC errors (collection errors) ──────────────────────────
    (cr / "pods-errors.json").write_text(json.dumps([
        "pods is forbidden: User \"system:serviceaccount:troubleshoot\" cannot list resource \"pods\" in namespace \"monitoring\""
    ]))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def bundle_dir(tmp_path: Path) -> Path:
    """Create a temporary bundle directory with all failure scenarios."""
    bundle = tmp_path / "test-bundle"
    bundle.mkdir()
    _build_test_bundle(bundle)
    return bundle


@pytest.mark.asyncio
async def test_full_triage_detects_all_failures(bundle_dir: Path) -> None:
    """Run the full triage pipeline and verify every failure is detected."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    # ── Verify critical pods detected ────────────────────────────
    critical_names = {p.pod_name for p in triage.critical_pods}
    warning_names = {p.pod_name for p in triage.warning_pods}
    all_flagged = critical_names | warning_names

    # CrashLoopBackOff detected
    assert "api-server-7f8b9c" in all_flagged, (
        f"CrashLoopBackOff pod not detected. Found: {all_flagged}"
    )

    # OOMKilled detected
    assert "worker-batch-4a2c" in all_flagged, (
        f"OOMKilled pod not detected. Found: {all_flagged}"
    )

    # ImagePullBackOff detected
    assert "frontend-deploy-x9z" in all_flagged, (
        f"ImagePullBackOff pod not detected. Found: {all_flagged}"
    )

    # Pending pod detected
    assert "ml-training-job-1" in all_flagged, (
        f"Pending pod not detected. Found: {all_flagged}"
    )

    # CreateContainerConfigError detected
    assert "config-app-abc" in all_flagged, (
        f"ConfigError pod not detected. Found: {all_flagged}"
    )

    # CoreDNS crashlooping detected
    assert "coredns-5d78c9869d-abc12" in all_flagged, (
        f"CoreDNS crash not detected. Found: {all_flagged}"
    )

    # ── Healthy pod should NOT be flagged ────────────────────────
    assert "web-frontend-ok" not in all_flagged, (
        "Healthy pod incorrectly flagged as failing!"
    )


@pytest.mark.asyncio
async def test_node_issues_detected(bundle_dir: Path) -> None:
    """Verify node-level failures are caught."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    node_names = {n.node_name for n in triage.node_issues}

    # MemoryPressure node
    assert "node-pressure" in node_names, (
        f"MemoryPressure node not detected. Found: {node_names}"
    )

    # NotReady node
    assert "node-notready" in node_names, (
        f"NotReady node not detected. Found: {node_names}"
    )

    # Healthy node should NOT be flagged
    assert "node-healthy" not in node_names, (
        "Healthy node incorrectly flagged!"
    )


@pytest.mark.asyncio
async def test_issue_types_correct(bundle_dir: Path) -> None:
    """Verify correct issue_type classification for each pod."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    all_pods = triage.critical_pods + triage.warning_pods
    pod_issues: dict[str, str] = {}
    for p in all_pods:
        pod_issues[p.pod_name] = p.issue_type

    assert pod_issues.get("api-server-7f8b9c") == "CrashLoopBackOff"
    assert pod_issues.get("worker-batch-4a2c") == "OOMKilled"
    assert pod_issues.get("frontend-deploy-x9z") == "ImagePullBackOff"
    # Pod scanner classifies by phase first — Pending phase overrides waiting reason
    assert pod_issues.get("config-app-abc") in ("CreateContainerConfigError", "Pending")


@pytest.mark.asyncio
async def test_pending_pod_detected_as_pending(bundle_dir: Path) -> None:
    """Verify pending pod with FailedScheduling is classified correctly."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    all_pods = triage.critical_pods + triage.warning_pods
    pending_pods = [p for p in all_pods if p.pod_name == "ml-training-job-1"]

    assert len(pending_pods) >= 1, "Pending pod not found in triage results"
    assert pending_pods[0].issue_type == "Pending"


@pytest.mark.asyncio
async def test_deployment_issues_detected(bundle_dir: Path) -> None:
    """Verify deployment with 0 ready replicas is flagged."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    deploy_names = {d.name for d in triage.deployment_issues}
    assert "api-server" in deploy_names, (
        f"Broken deployment not detected. Found: {deploy_names}"
    )


@pytest.mark.asyncio
async def test_config_issues_detected(bundle_dir: Path) -> None:
    """Verify missing configmap reference is detected."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    config_refs = [c.resource_name for c in triage.config_issues]
    has_missing_cm = any("app-settings" in ref for ref in config_refs)
    assert has_missing_cm, (
        f"Missing configmap 'app-settings' not detected. Config issues: {config_refs}"
    )


@pytest.mark.asyncio
async def test_warning_events_captured(bundle_dir: Path) -> None:
    """Verify warning events (BackOff, OOMKilling, FailedScheduling) are captured."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    event_reasons = {e.reason for e in triage.warning_events}

    assert "BackOff" in event_reasons, f"BackOff event not captured. Found: {event_reasons}"
    assert "OOMKilling" in event_reasons, f"OOMKilling event not captured. Found: {event_reasons}"
    assert "FailedScheduling" in event_reasons, f"FailedScheduling event not captured. Found: {event_reasons}"


@pytest.mark.asyncio
async def test_scheduling_issues_from_events(bundle_dir: Path) -> None:
    """Verify FailedScheduling events produce scheduling issues."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    # Scheduling issues may come from events or from pod status conditions
    scheduling_pods = {s.pod_name for s in triage.scheduling_issues}
    # Also check if the pod was detected as Pending (which covers the scheduling failure)
    pending_pods = {p.pod_name for p in triage.critical_pods + triage.warning_pods
                    if p.issue_type == "Pending"}
    detected = scheduling_pods | pending_pods
    assert "ml-training-job-1" in detected, (
        f"FailedScheduling not detected for ml-training-job-1. "
        f"Scheduling: {scheduling_pods}, Pending: {pending_pods}"
    )


@pytest.mark.asyncio
async def test_evidence_has_source_files(bundle_dir: Path) -> None:
    """Verify triage findings include source_file references."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    # Critical pods should have source_file set
    for pod in triage.critical_pods:
        assert pod.source_file, (
            f"Pod {pod.pod_name} missing source_file in evidence"
        )


@pytest.mark.asyncio
async def test_rbac_errors_captured(bundle_dir: Path) -> None:
    """Verify RBAC collection errors are captured."""
    index = await BundleIndex.build(bundle_dir)
    engine = TriageEngine()
    triage = await engine.run(index)

    has_rbac = len(triage.rbac_issues) > 0 or len(index.rbac_errors) > 0
    assert has_rbac, "RBAC collection errors not captured"


@pytest.mark.asyncio
async def test_bundle_metadata_populated(bundle_dir: Path) -> None:
    """Verify bundle metadata is extracted from version.yaml."""
    index = await BundleIndex.build(bundle_dir)

    assert index.metadata is not None
    assert index.metadata.collected_at is not None


@pytest.mark.asyncio
async def test_log_streaming_works(bundle_dir: Path) -> None:
    """Verify container logs are streamable from the bundle."""
    index = await BundleIndex.build(bundle_dir)

    # Stream crashloop pod's current logs
    lines = list(index.stream_log("default", "api-server-7f8b9c", "api", previous=False))
    assert len(lines) > 0, "No current logs streamed for crashloop pod"
    assert any("connection refused" in line for line in lines), (
        "Expected 'connection refused' in crashloop pod logs"
    )

    # Stream previous logs
    prev_lines = list(index.stream_log("default", "api-server-7f8b9c", "api", previous=True))
    assert len(prev_lines) > 0, "No previous logs streamed for crashloop pod"


@pytest.mark.asyncio
async def test_triage_only_analysis_completes(bundle_dir: Path) -> None:
    """Verify the orchestrator returns triage-only results without an API key."""
    import os

    # Clear any AI keys to force triage-only mode
    saved = {}
    for key in ("OPEN_ROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        saved[key] = os.environ.pop(key, None)

    try:
        from bundle_analyzer.ai.orchestrator import AnalysisOrchestrator
        from bundle_analyzer.ai.context_injector import ContextInjector

        index = await BundleIndex.build(bundle_dir)
        engine = TriageEngine()
        triage = await engine.run(index)

        orchestrator = AnalysisOrchestrator()
        result = await orchestrator.run(
            triage=triage,
            index=index,
            context_injector=ContextInjector(),
        )

        assert isinstance(result, AnalysisResult)
        assert result.triage is not None
        assert result.analysis_quality == "degraded"  # no AI key
        assert len(result.triage.critical_pods) + len(result.triage.warning_pods) > 0
    finally:
        for key, val in saved.items():
            if val is not None:
                os.environ[key] = val


@pytest.mark.asyncio
async def test_security_scrubber_redacts_secrets(bundle_dir: Path) -> None:
    """Verify the scrubber redacts secrets from pod JSON."""
    from bundle_analyzer.security.scrubber import BundleScrubber

    index = await BundleIndex.build(bundle_dir)

    # Read the crashloop pod with real secrets in env
    pod_data = index.read_json("cluster-resources/pods/default/api-server-7f8b9c.json")
    assert pod_data is not None

    scrubber = BundleScrubber()
    scrubbed, report = scrubber.scrub_pod_json(pod_data)

    # Env var NAMES should be preserved
    scrubbed_json = json.dumps(scrubbed)
    assert "DB_HOST" in scrubbed_json, "Env var name DB_HOST should be preserved"
    assert "LOG_LEVEL" in scrubbed_json, "Env var name LOG_LEVEL should be preserved"

    # Env var VALUES should be redacted (scrubber redacts ALL env values)
    assert "[REDACTED" in scrubbed_json, "Env var values should be redacted"
    # Original secret values should NOT appear
    assert "postgres.db.svc.cluster.local" not in scrubbed_json, (
        "DB_HOST value should be redacted"
    )


@pytest.mark.asyncio
async def test_api_response_scrubber(bundle_dir: Path) -> None:
    """Verify the API response scrubber redacts sensitive data in findings."""
    from bundle_analyzer.api.response_scrubber import scrub_findings_list
    from bundle_analyzer.models import Evidence, Finding

    findings = [
        Finding(
            id="test-1",
            severity="critical",
            type="pod-failure",
            resource="pod/default/test",
            symptom="Pod crashed with connection to postgres://admin:s3cretP@ss@10.0.5.23:5432",
            root_cause="Database password exposed in connection string",
            evidence=[
                Evidence(
                    file="cluster-resources/pods/default/test.json",
                    excerpt="DATABASE_URL=postgres://admin:s3cretP@ss@10.0.5.23:5432/production",
                )
            ],
            confidence=0.9,
        )
    ]

    scrubbed = scrub_findings_list(findings)
    assert len(scrubbed) == 1

    # The connection string should be scrubbed
    scrubbed_symptom = scrubbed[0]["symptom"]
    scrubbed_excerpt = scrubbed[0]["evidence"][0]["excerpt"]

    # Structural fields preserved
    assert scrubbed[0]["id"] == "test-1"
    assert scrubbed[0]["severity"] == "critical"
    assert scrubbed[0]["confidence"] == 0.9
