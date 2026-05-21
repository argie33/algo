#!/bin/bash
# Runs immediately after deployment notification - captures all logs

echo "DEPLOYMENT COMPLETE - TESTING ORCHESTRATOR"
echo "=========================================="
echo ""

python3 test_orchestrator_live.py 2>&1 | tee /tmp/orchestrator_test_$(date +%s).log
