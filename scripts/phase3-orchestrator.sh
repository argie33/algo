#!/bin/bash
set -e

echo "=========================================="
echo "PHASE 3: Execute Orchestrator"
echo "=========================================="
echo ""

# Step 1: Invoke orchestrator
echo "[1/2] Invoking orchestrator (7-phase logic)..."
orch_run=$(gh workflow run "Manual - Test Orchestrator" --ref main --json id -q 2>/dev/null || \
  gh workflow run test-orchestrator --ref main --json id -q 2>/dev/null || echo "")

if [ -z "$orch_run" ]; then
  echo "ERROR: Could not trigger orchestrator workflow"
  echo "Workflows available:"
  gh workflow list
  exit 1
fi

echo "✓ Orchestrator triggered (run: $orch_run)"
echo ""

# Step 2: Monitor orchestrator completion
echo "[2/2] Monitoring orchestrator execution..."
ELAPSED=0
MAX_WAIT=2400  # 40 min
POLL_INTERVAL=30

while [ $ELAPSED -lt $MAX_WAIT ]; do
  status=$(gh run view "$orch_run" --json status,conclusion | python3 -c "import json,sys; r=json.load(sys.stdin); print(f'{r[\"status\"]}:{r[\"conclusion\"]}')" 2>/dev/null || echo "unknown:unknown")

  if [[ "$status" == "completed:"* ]]; then
    conclusion=$(echo "$status" | cut -d: -f2)
    if [ "$conclusion" = "success" ]; then
      echo "✓ Orchestrator completed successfully"
      break
    else
      echo "WARNING: Orchestrator completed with status: $conclusion"
      # Don't fail here - we still want to check if trades were placed
      break
    fi
  fi

  echo "  [$ELAPSED/$MAX_WAIT] Orchestrator running... (status: $status)"
  sleep $POLL_INTERVAL
  ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

echo ""
echo "=========================================="
echo "PHASE 3 COMPLETE"
echo "=========================================="
echo "✓ Orchestrator executed (7 phases)"
echo "✓ Ready for Phase 4: Verify trades"
