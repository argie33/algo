#!/bin/bash
# Test orchestrator after deployment completes

echo "Waiting for deployment to finish..."
until [ "$(gh run view 26244761650 --repo argie33/algo --json conclusion -q)" != "" ]; do
  sleep 10
done

echo ""
echo "Deployment complete! Running orchestrator test..."
echo ""

python3 test_orchestrator_live.py
