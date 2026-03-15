"""Realistic multi-failure support bundle builder for E2E tests.

Creates a support bundle directory with 8 simultaneous failure scenarios:
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

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _ts(minutes_ago: int = 0) -> str:
    """ISO timestamp relative to a fixed collection time."""
    base = datetime(2024, 3, 15, 14, 0, 0, tzinfo=timezone.utc)
    dt = base - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_test_bundle(root: Path) -> None:
    """Populate *root* with a realistic multi-failure support bundle."""
    cr = root / "cluster-resources"

    # ── version.yaml (bundle metadata) ──────────────────────────
    (root / "version.yaml").write_text(
        "apiVersion: troubleshoot.sh/v1beta2\n"
        f"collectedAt: {_ts(0)}\n"
        "kubernetesVersion: v1.28.3\n"
    )

    # ── Nodes ────────────────────────────────────────────────────
    _build_nodes(cr)

    # ── Pods ─────────────────────────────────────────────────────
    _build_pods(cr)

    # ── Events ───────────────────────────────────────────────────
    _build_events(cr)

    # ── Deployments ──────────────────────────────────────────────
    _build_deployments(cr)

    # ── ConfigMaps (app-settings is deliberately MISSING) ────────
    _build_configmaps(cr)

    # ── Container logs ───────────────────────────────────────────
    _build_logs(cr)

    # ── Namespaces ───────────────────────────────────────────────
    (cr / "namespaces.json").write_text(json.dumps({
        "items": [
            {"metadata": {"name": "default"}},
            {"metadata": {"name": "kube-system"}},
        ]
    }))

    # ── RBAC errors (collection errors) ──────────────────────────
    (cr / "pods-errors.json").write_text(json.dumps([
        "pods is forbidden: User \"system:serviceaccount:troubleshoot\" "
        "cannot list resource \"pods\" in namespace \"monitoring\""
    ]))


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

def _build_nodes(cr: Path) -> None:
    """Create node JSON files."""
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
                        {"type": "Ready", "status": "True", "lastTransitionTime": _ts(30)},
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


# ---------------------------------------------------------------------------
# Pod builders
# ---------------------------------------------------------------------------

def _build_pods(cr: Path) -> None:
    """Create pod JSON files for all failure scenarios."""
    pods_dir = cr / "pods" / "default"
    pods_dir.mkdir(parents=True)

    _build_crashloop_pod(pods_dir)
    _build_oom_pod(pods_dir)
    _build_imagepull_pod(pods_dir)
    _build_pending_pod(pods_dir)
    _build_config_error_pod(pods_dir)
    _build_healthy_pod(pods_dir)
    _build_coredns_pod(cr)


def _build_crashloop_pod(pods_dir: Path) -> None:
    """Pod 1: CrashLoopBackOff (DB connection refused)."""
    pod = {
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
    (pods_dir / "api-server-7f8b9c.json").write_text(json.dumps(pod, indent=2))


def _build_oom_pod(pods_dir: Path) -> None:
    """Pod 2: OOMKilled (Java heap too large)."""
    pod = {
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
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
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
    (pods_dir / "worker-batch-4a2c.json").write_text(json.dumps(pod, indent=2))


def _build_imagepull_pod(pods_dir: Path) -> None:
    """Pod 3: ImagePullBackOff."""
    pod = {
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
                            "message": 'Back-off pulling image "myregistry.io/frontend:v3.0.0-typo"',
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "frontend-deploy-x9z.json").write_text(json.dumps(pod, indent=2))


def _build_pending_pod(pods_dir: Path) -> None:
    """Pod 4: Pending (insufficient CPU — FailedScheduling)."""
    pod = {
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
                    "message": "0/3 nodes are available: 1 Insufficient cpu, "
                               "1 node had memory pressure, 1 node was not ready.",
                }
            ],
        },
    }
    (pods_dir / "ml-training-job-1.json").write_text(json.dumps(pod, indent=2))


def _build_config_error_pod(pods_dir: Path) -> None:
    """Pod 5: Missing configmap reference."""
    pod = {
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
                            "message": 'configmap "app-settings" not found',
                        }
                    },
                }
            ],
        },
    }
    (pods_dir / "config-app-abc.json").write_text(json.dumps(pod, indent=2))


def _build_coredns_pod(cr: Path) -> None:
    """Pod 6: CoreDNS crashlooping (DNS failure scenario)."""
    pod = {
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
    (ks_pods / "coredns-5d78c9869d-abc12.json").write_text(json.dumps(pod, indent=2))


def _build_healthy_pod(pods_dir: Path) -> None:
    """Pod 7: healthy pod (control — should NOT be flagged)."""
    pod = {
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
    (pods_dir / "web-frontend-ok.json").write_text(json.dumps(pod, indent=2))


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------

def _build_events(cr: Path) -> None:
    """Create event JSON files."""
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
                "message": 'Failed to pull image "myregistry.io/frontend:v3.0.0-typo": not found',
                "involvedObject": {"kind": "Pod", "name": "frontend-deploy-x9z", "namespace": "default"},
                "firstTimestamp": _ts(30),
                "lastTimestamp": _ts(28),
                "count": 5,
            },
            {
                "metadata": {"name": "ev-schedule", "namespace": "default", "creationTimestamp": _ts(44)},
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/3 nodes are available: 1 Insufficient cpu, "
                           "1 node had memory pressure, 1 node was not ready.",
                "involvedObject": {"kind": "Pod", "name": "ml-training-job-1", "namespace": "default"},
                "firstTimestamp": _ts(45),
                "lastTimestamp": _ts(2),
                "count": 15,
            },
            {
                "metadata": {"name": "ev-configerr", "namespace": "default", "creationTimestamp": _ts(19)},
                "type": "Warning",
                "reason": "Failed",
                "message": 'Error: configmap "app-settings" not found',
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


# ---------------------------------------------------------------------------
# Deployment / ConfigMap / Log builders
# ---------------------------------------------------------------------------

def _build_deployments(cr: Path) -> None:
    """Create deployment JSON files."""
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


def _build_configmaps(cr: Path) -> None:
    """Create ConfigMap files — app-settings is deliberately MISSING."""
    cm_dir = cr / "configmaps" / "default"
    cm_dir.mkdir(parents=True)
    configmaps = {
        "items": [
            {
                "metadata": {"name": "kube-root-ca.crt", "namespace": "default"},
                "data": {"ca.crt": "-----BEGIN CERTIFICATE-----\nMIIC..."},
            },
            # NOTE: "app-settings" is deliberately missing
        ]
    }
    (cm_dir / "configmaps.json").write_text(json.dumps(configmaps, indent=2))


def _build_logs(cr: Path) -> None:
    """Create container log files."""
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
