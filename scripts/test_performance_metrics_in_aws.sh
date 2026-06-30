#!/bin/bash
# Helper script to apply migrations and test performance metrics loader in AWS
# Run this from within the VPC (EC2, Lambda, or ECS task)
# Usage: bash scripts/test_performance_metrics_in_aws.sh

set -e

echo "=========================================="
echo "Performance Metrics Loader - AWS Test"
echo "=========================================="

# Step 1: Apply database migrations
echo ""
echo "Step 1: Applying database migrations..."
python scripts/apply_rds_migrations.py

# Check for success
if [ $? -eq 0 ]; then
    echo "✓ Migrations applied successfully"
else
    echo "✗ Migration failed"
    exit 1
fi

# Step 2: Verify columns exist
echo ""
echo "Step 2: Verifying database schema..."
python -c "
import json
import psycopg2
from utils.db.context import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics'
        AND column_name IN ('avg_win_r', 'avg_loss_r', 'expectancy')
        ORDER BY column_name
    ''')
    cols = cur.fetchall()
    if len(cols) == 3:
        print('✓ All three R-metrics columns found:')
        for col in cols:
            print(f'  - {col[\"column_name\"]}: {col[\"data_type\"]}')
    else:
        print('✗ Missing columns. Found:', len(cols), '/ 3')
        exit(1)
"

# Step 3: Run the performance metrics loader
echo ""
echo "Step 3: Running compute_performance_metrics loader..."
python -m loaders.compute_performance_metrics

# Step 4: Verify data was inserted
echo ""
echo "Step 4: Verifying data was inserted..."
python -c "
from utils.db.context import DatabaseContext
from datetime import date

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT metric_date, total_trades, avg_win_r, avg_loss_r, expectancy
        FROM algo_performance_metrics
        WHERE metric_date = CURRENT_DATE
    ''')
    result = cur.fetchone()
    if result:
        print(f'✓ Metrics inserted for {result[\"metric_date\"]}:')
        print(f'  - Total trades: {result[\"total_trades\"]}')
        print(f'  - Avg Win R: {result[\"avg_win_r\"]}')
        print(f'  - Avg Loss R: {result[\"avg_loss_r\"]}')
        print(f'  - Expectancy: {result[\"expectancy\"]}')
    else:
        print('✗ No metrics found for today')
        exit(1)
"

echo ""
echo "=========================================="
echo "✓ All tests passed!"
echo "=========================================="
