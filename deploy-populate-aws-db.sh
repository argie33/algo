#!/bin/bash
###############################################################################
# AWS RDS Data Population Script
# Runs all required data loaders against AWS RDS to populate empty tables
###############################################################################

set -e

export AWS_REGION="us-east-1"
export DB_SECRET_ARN="arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"

echo "========================================="
echo "AWS RDS Data Population"
echo "========================================="
echo "Region: $AWS_REGION"
echo "Secret ARN: $DB_SECRET_ARN"
echo ""

# Critical loaders for stock scores to work
echo "Running critical loaders for stock scores..."
echo ""

echo "[1/3] Loading sector benchmarks..."
python3 loadsectorbenchmarks.py

echo "[2/3] Loading historical benchmarks..."
python3 loadhistoricalbenchmarks.py

echo "[3/3] Loading stock scores..."
python3 loadstockscores.py

echo ""
echo "========================================="
echo "✅ AWS RDS populated successfully!"
echo "========================================="
echo ""
echo "Stock scores should now be visible in the frontend."
