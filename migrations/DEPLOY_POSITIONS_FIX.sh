#!/bin/bash
# Deploy positions view fix to AWS RDS
# This script applies migration 999 to your production RDS instance

set -e

echo "========================================="
echo "Positions View Fix - AWS RDS Deployment"
echo "========================================="
echo

# Check if RDS endpoint is provided
if [ -z "$RDS_ENDPOINT" ]; then
    echo "ERROR: RDS_ENDPOINT environment variable not set"
    echo "Usage: export RDS_ENDPOINT=your-rds-endpoint.rds.amazonaws.com"
    echo "       export RDS_DB_USER=postgres"
    echo "       export RDS_DB_NAME=algo"
    echo "       $0"
    exit 1
fi

if [ -z "$RDS_DB_USER" ]; then
    RDS_DB_USER="postgres"
fi

if [ -z "$RDS_DB_NAME" ]; then
    RDS_DB_NAME="algo"
fi

echo "Deploying to:"
echo "  Host: $RDS_ENDPOINT"
echo "  User: $RDS_DB_USER"
echo "  Database: $RDS_DB_NAME"
echo

# Apply the migration
echo "Applying migration 999..."
psql -h "$RDS_ENDPOINT" -U "$RDS_DB_USER" -d "$RDS_DB_NAME" < migrations/versions/999_emergency_recreate_positions_view.sql

if [ $? -eq 0 ]; then
    echo
    echo "✓ Migration applied successfully"
    echo

    # Verify the view exists
    echo "Verifying view creation..."
    POSITION_COUNT=$(psql -h "$RDS_ENDPOINT" -U "$RDS_DB_USER" -d "$RDS_DB_NAME" -t -c "SELECT COUNT(*) FROM algo_positions_with_risk WHERE status='open'")

    if [ "$POSITION_COUNT" = "10" ]; then
        echo "✓ View verified: 10 open positions found"
        echo
        echo "DEPLOYMENT SUCCESSFUL!"
        echo
        echo "Next steps:"
        echo "  1. Restart Lambda: aws lambda update-function-configuration --function-name algo-api --environment Variables={REDEPLOY=true}"
        echo "  2. Test dashboard: python -m dashboard -w 30"
    else
        echo "✗ Verification failed: Expected 10 positions, got $POSITION_COUNT"
        exit 1
    fi
else
    echo "✗ Migration failed"
    exit 1
fi
