#!/usr/bin/env bash
# Scenario: Deploy requesting more CPU than the cluster has.
# Expected: FailedScheduling / Pending detected.
set -euo pipefail

echo "==> Deploying pod requesting excessive CPU..."
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: cpu-hog-test
  namespace: default
  labels:
    test-scenario: insufficient-cpu
spec:
  containers:
  - name: main
    image: nginx:latest
    resources:
      requests:
        cpu: "100"
        memory: "64Mi"
      limits:
        cpu: "100"
        memory: "64Mi"
EOF

echo "==> Waiting 15s for FailedScheduling..."
sleep 15
echo "==> Scenario deployed. Collect bundle now."
