#!/usr/bin/env bash
# Scenario: Deploy a pod referencing a nonexistent secret.
# Expected: CreateContainerConfigError detected by PodScanner + ConfigScanner.
set -euo pipefail

echo "==> Deploying pod referencing missing secret..."
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: missing-secret-test
  namespace: default
  labels:
    test-scenario: missing-secret
spec:
  containers:
  - name: main
    image: nginx:latest
    env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: nonexistent-db-secret
          key: password
    resources:
      limits:
        memory: "64Mi"
        cpu: "100m"
EOF

echo "==> Waiting 15s for CreateContainerConfigError..."
sleep 15
echo "==> Scenario deployed. Collect bundle now."
