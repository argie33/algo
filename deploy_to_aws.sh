#!/bin/bash
# AWS RDS Data Deployment Script
# Run this script AFTER all local loaders complete

set -e

echo "================================================================================"
echo "             AWS RDS Data Deployment - Final Sync"
echo "================================================================================"
echo "Time: $(date)"
echo ""

# Check if AWS_SECRET_ARN is set
if [ -z "$AWS_SECRET_ARN" ]; then
    echo "❌ ERROR: AWS_SECRET_ARN environment variable not set"
    echo ""
    echo "This script requires AWS credentials to deploy to RDS."
    echo "Set the variable and try again:"
    echo ""
    echo '  export AWS_SECRET_ARN="arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"'
    echo '  bash /home/stocks/algo/deploy_to_aws.sh'
    exit 1
fi

# Run Python sync script
echo "Starting AWS RDS sync..."
python3 /home/stocks/algo/sync_to_aws.py

RESULT=$?
if [ $RESULT -eq 0 ]; then
    echo ""
    echo "✅ Deployment to AWS completed successfully"
    exit 0
else
    echo ""
    echo "❌ Deployment to AWS failed"
    exit 1
fi
