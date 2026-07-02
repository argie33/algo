#!/bin/bash
# Active monitoring script - checks pipeline status and AWS data every 10 minutes
# Exits when data appears in AWS RDS

EXECUTION_ARN="arn:aws:states:us-east-1:626216981288:execution:algo-computed-metrics-pipeline-dev:manual-trigger-1782997142"
CHECK_INTERVAL=600  # 10 minutes
MAX_CHECKS=20       # ~3.3 hours max

check_count=0

echo "=============================================="
echo "MONITORING AWS PIPELINE & DATA ARRIVAL"
echo "=============================================="
echo ""
echo "Will check every 10 minutes for:"
echo "  1. Pipeline completion (SUCCEEDED status)"
echo "  2. AWS RDS data arrival (metric tables populated)"
echo ""

while [ $check_count -lt $MAX_CHECKS ]; do
    check_count=$((check_count + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo "[$timestamp] Check #$check_count..."

    # Get pipeline status
    STATUS=$(aws stepfunctions describe-execution \
        --execution-arn "$EXECUTION_ARN" \
        --region us-east-1 \
        --query 'status' \
        --output text 2>/dev/null)

    echo "  Pipeline status: $STATUS"

    # If pipeline succeeded, check for AWS data
    if [ "$STATUS" = "SUCCEEDED" ]; then
        echo "  Pipeline COMPLETED! Verifying AWS data..."
        echo ""

        # Check AWS data
        python3 << 'PYTHON_EOF'
import psycopg2
import sys

try:
    conn = psycopg2.connect(
        host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
        port=5432,
        database="algo_prod",
        user="algo_admin",
        password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe",
        sslmode="require"
    )

    cur = conn.cursor()

    # Check key metrics
    metrics_check = []

    cur.execute("SELECT COUNT(*) FROM quality_metrics WHERE quality_score IS NOT NULL")
    quality_count = cur.fetchone()[0]
    metrics_check.append(("quality_metrics with quality_score", quality_count, 4000))

    cur.execute("SELECT COUNT(*) FROM growth_metrics WHERE growth_score IS NOT NULL")
    growth_count = cur.fetchone()[0]
    metrics_check.append(("growth_metrics with growth_score", growth_count, 4000))

    cur.execute("SELECT COUNT(*) FROM value_metrics WHERE value_score IS NOT NULL")
    value_count = cur.fetchone()[0]
    metrics_check.append(("value_metrics with value_score", value_count, 4000))

    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
    stock_scores = cur.fetchone()[0]
    metrics_check.append(("stock_scores with composite_score", stock_scores, 4500))

    cur.close()
    conn.close()

    print("✓ AWS RDS Data Check:")
    all_good = True
    for name, actual, threshold in metrics_check:
        status = "✓" if actual >= threshold else "✗"
        print(f"  {status} {name}: {actual:,} (need {threshold:,})")
        if actual < threshold:
            all_good = False

    print()

    if all_good:
        print("=" * 60)
        print("✓✓✓ SUCCESS! AWS DATA NOW VISIBLE ✓✓✓")
        print("=" * 60)
        print()
        print("Factor inputs data has been successfully loaded into AWS RDS:")
        print("  • Quality metrics: populated")
        print("  • Growth metrics: populated")
        print("  • Value metrics: populated")
        print("  • Stock scores: computed and stored")
        print()
        print("Data is now accessible via the /api/scores endpoint")
        sys.exit(0)
    else:
        print("Data loading... some tables not yet at target level")
        sys.exit(1)

except Exception as e:
    print(f"✗ AWS connection failed: {e}")
    print("  (Data may still be loading)")
    sys.exit(1)
PYTHON_EOF

        if [ $? -eq 0 ]; then
            # AWS data confirmed!
            echo ""
            echo "=============================================="
            echo "GOAL CONDITION MET!"
            echo "=============================================="
            exit 0
        fi
    fi

    # Check if pipeline failed
    if [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "TIMED_OUT" ]; then
        echo "✗ Pipeline FAILED with status: $STATUS"
        echo ""
        echo "Getting failure details..."
        aws stepfunctions get-execution-history \
            --execution-arn "$EXECUTION_ARN" \
            --region us-east-1 \
            --query 'events[-1]' \
            --output json
        exit 1
    fi

    # Still running - wait before next check
    echo "  Waiting $((CHECK_INTERVAL / 60)) minutes before next check..."
    echo ""
    sleep $CHECK_INTERVAL
done

echo ""
echo "✗ Timeout: Max checks exceeded without data confirmation"
exit 1
