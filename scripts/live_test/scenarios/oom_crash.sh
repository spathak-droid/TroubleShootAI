#!/usr/bin/env bash
# Scenario: Deploy a memory-hungry pod with a low limit.
# Expected: OOMKilled / CrashLoopBackOff detected.
set -euo pipefail

echo "==> Deploying OOM-triggering pod..."
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: oom-crash-test
  namespace: default
  labels:
    test-scenario: oom-crash
spec:
  containers:
  - name: main
    image: python:3.11-slim
    command: ["python3", "-c", "x = ' ' * (200 * 1024 * 1024)"]
    resources:
      limits:
        memory: "32Mi"
        cpu: "100m"
  restartPolicy: Always
EOF

echo "==> Waiting 60s for OOMKill + CrashLoopBackOff..."
sleep 60
echo "==> Scenario deployed. Collect bundle now."
