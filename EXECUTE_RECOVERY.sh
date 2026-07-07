#!/bin/bash
# EXECUTE THIS IMMEDIATELY AFTER TERRAFORM DEPLOYMENT COMPLETES
# This brings the system fully online with fresh data

set -e

echo "════════════════════════════════════════════════════════════════"
echo "  SESSION 38 RECOVERY: Bringing System Online"
echo "════════════════════════════════════════════════════════════════"

# Step 1: Verify Lambda concurrency was updated
echo ""
echo "Step 1: Verifying Lambda concurrency fix..."
python -m dashboard.diagnose_dashboard 2>&1 | head -30

# Step 2: Generate fresh data immediately
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 2: Running orchestrator to generate fresh data..."
echo "This will load prices, calculate scores, execute paper trades"
echo "════════════════════════════════════════════════════════════════"
echo ""

python3 scripts/trigger_orchestrator.py --run morning --mode paper

echo ""
echo "✅ Fresh data generated!"

# Step 3: Verify dashboard shows data
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 3: Verifying dashboard has fresh data..."
echo "════════════════════════════════════════════════════════════════"
echo ""

python -m dashboard.diagnose_dashboard 2>&1 | grep -A 50 "SUMMARY"

# Step 4: Start continuous scheduler
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 4: Starting continuous orchestrator scheduler..."
echo "This will refresh data every 4 hours indefinitely"
echo "════════════════════════════════════════════════════════════════"
echo ""

python3 scripts/orchestrator_scheduler.py --mode paper --interval 4

