#!/bin/bash
# Test if Lambda deployment fixed the scores data issue

echo "=== AWS LAMBDA SCORES DATA FIX VERIFICATION ==="
echo ""
echo "Waiting for Lambda deployment to complete..."
echo "Monitor deployment at: https://github.com/argie33/algo/actions"
echo ""

# Function to test API
test_api() {
    echo "Testing AWS Lambda API..."
    python3 << 'PYTHON'
from dashboard.api_data_layer import api_call
import time

try:
    result = api_call('/api/algo/scores', params={'limit': 3})
    if isinstance(result, dict) and 'top' in result and result['top']:
        scores = result['top']
        print("\n✓ API Response received:")
        for i, score in enumerate(scores[:2], 1):
            sym = score.get('symbol')
            growth = score.get('growth_score')
            rs = score.get('rs_percentile')

            # Check for corruption
            growth_ok = growth is not None and growth > 0
            rs_ok = rs is not None and rs > 0

            status = "✅" if (growth_ok or growth is None) and (rs_ok or rs is None) else "❌"

            print(f"  {i}. {sym}: growth={growth}, rs={rs} {status}")

        # Final verdict
        all_ok = all(
            s.get('growth_score') is not None and s.get('growth_score') > 0
            for s in scores[:5]
        )
        if all_ok:
            print("\n✓✓✓ FIXED! AWS Lambda now returns correct data")
            return True
        else:
            print("\n⚠ Partial fix - some values still corrupt")
            return False
    else:
        print("❌ No scores returned")
        return False
except Exception as e:
    print(f"❌ API Error: {e}")
    return False
PYTHON
}

# Wait for deployment (max 5 minutes)
echo "Polling for Lambda deployment completion..."
for i in {1..30}; do
    echo -n "."
    sleep 10

    # Check if Lambda was updated (via AWS CLI or by testing)
    if test_api; then
        exit 0
    fi
done

echo ""
echo "❌ Lambda deployment verification timeout or still has issues"
echo ""
echo "Next steps:"
echo "1. Check deployment status: https://github.com/argie33/algo/actions/runs/29342497624"
echo "2. If deployment failed, run: gh workflow run deploy-api-lambda.yml --ref main"
echo "3. If deployment succeeded but data still wrong:"
echo "   - Run: aws lambda update-alias --function-name algo-api-dev --name LIVE --routing-config '{\"AdditionalVersionWeight\": null}'"
echo "   - Check RDS connection: aws rds describe-db-instances | grep -i algo"
echo ""
exit 1
