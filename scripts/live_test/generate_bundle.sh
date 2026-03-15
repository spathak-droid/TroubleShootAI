#!/usr/bin/env bash
# Generate a support bundle from the current cluster.
# Uses kubectl support-bundle (Troubleshoot.sh) if available.
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-./bundles}"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BUNDLE_NAME="test-bundle-$TIMESTAMP"

echo "==> Generating support bundle..."

if command -v kubectl-support_bundle &>/dev/null || kubectl support-bundle --help &>/dev/null 2>&1; then
  # Use Troubleshoot.sh support-bundle collector
  cat > /tmp/support-bundle-spec.yaml <<'EOF'
apiVersion: troubleshoot.sh/v1beta2
kind: SupportBundle
metadata:
  name: test-bundle
spec:
  collectors:
    - clusterResources: {}
    - clusterInfo: {}
    - logs:
        selector: []
        namespace: ""
        limits:
          maxLines: 500
EOF
  kubectl support-bundle /tmp/support-bundle-spec.yaml --output "$OUTPUT_DIR/$BUNDLE_NAME.tar.gz" || {
    echo "support-bundle command failed. Falling back to manual collection."
  }
else
  echo "kubectl support-bundle not found."
  echo "Install: https://troubleshoot.sh/docs/support-bundle/installing/"
  echo ""
  echo "Falling back to manual kubectl dump..."

  BUNDLE_DIR="$OUTPUT_DIR/$BUNDLE_NAME"
  mkdir -p "$BUNDLE_DIR/cluster-resources/pods" "$BUNDLE_DIR/cluster-resources/events" "$BUNDLE_DIR/cluster-resources/nodes"

  # Collect pods
  for ns in $(kubectl get namespaces -o jsonpath='{.items[*].metadata.name}'); do
    mkdir -p "$BUNDLE_DIR/cluster-resources/pods/$ns"
    kubectl get pods -n "$ns" -o json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('items', []):
    name = item['metadata']['name']
    with open('$BUNDLE_DIR/cluster-resources/pods/$ns/' + name + '.json', 'w') as f:
        json.dump(item, f, indent=2)
" 2>/dev/null || true
  done

  # Collect events
  kubectl get events --all-namespaces -o json > "$BUNDLE_DIR/cluster-resources/events/events.json" 2>/dev/null || true

  # Collect nodes
  kubectl get nodes -o json 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('items', []):
    name = item['metadata']['name']
    with open('$BUNDLE_DIR/cluster-resources/nodes/' + name + '.json', 'w') as f:
        json.dump(item, f, indent=2)
" 2>/dev/null || true

  echo "==> Manual bundle saved to: $BUNDLE_DIR"
fi

echo "==> Bundle generation complete."
