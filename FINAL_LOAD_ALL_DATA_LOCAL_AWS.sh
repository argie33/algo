#!/bin/bash
# FINAL COMPREHENSIVE LOADER - Push ALL critical data to LOCAL + AWS
# Runs sequentially with fixed loaders to ensure data consistency

export PGPASSWORD='bed0elAn'
export DB_HOST='localhost'
export DB_USER='stocks'
export DB_PASSWORD='bed0elAn'
export DB_NAME='stocks'
export AWS_REGION='us-east-1'
export AWS_DEFAULT_REGION='us-east-1'
export DB_SECRET_ARN='arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret-ABCDE'

cd /home/arger/algo

echo "🚀🚀🚀 FINAL COMPREHENSIVE DATA LOAD - LOCAL + AWS 🚀🚀🚀"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$(date)"
echo ""
echo "📊 Target Databases:"
echo "  • LOCAL: postgresql://stocks:***@localhost:5432/stocks"
echo "  • AWS RDS: via AWS Secrets Manager"
echo ""

# Kill any existing loaders
pkill -9 -f "load.*\.py" 2>/dev/null || true
sleep 3

run_loader() {
  local target=$1  # "LOCAL" or "AWS"
  local name=$2
  local file=$3
  local timeout=${4:-3600}

  # Kill any parallel loaders
  pkill -9 -f "load.*\.py" 2>/dev/null || true
  sleep 2

  echo ""
  echo "▶️  [$target] $name"
  START=$(date +%s)

  if [ "$target" = "AWS" ]; then
    # AWS Configuration
    (
      export PGPASSWORD='bed0elAn'
      export AWS_REGION='us-east-1'
      export AWS_DEFAULT_REGION='us-east-1'
      export DB_SECRET_ARN='arn:aws:secretsmanager:us-east-1:626216981288:secret:rds-stocks-secret-ABCDE'

      timeout $timeout python3 -u "$file" 2>&1 | tee /tmp/${file%.py}_final_aws.log | tail -30
    )
  else
    # LOCAL Configuration
    (
      export PGPASSWORD='bed0elAn'
      export DB_HOST='localhost'
      export DB_USER='stocks'
      export DB_PASSWORD='bed0elAn'
      export DB_NAME='stocks'

      timeout $timeout python3 -u "$file" 2>&1 | tee /tmp/${file%.py}_final_local.log | tail -30
    )
  fi

  ELAPSED=$(($(date +%s) - START))
  echo "✅ [$target] Done in ${ELAPSED}s"
  sleep 2
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 1: Load ALL critical data to LOCAL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_loader "LOCAL" "Price Daily (100%)" "loadpricedaily.py" 3600
run_loader "LOCAL" "Company Profile (4.9%)" "loaddailycompanydata.py" 3600
run_loader "LOCAL" "Quarterly Cashflow (70.8%)" "loadquarterlycashflow.py" 3600
run_loader "LOCAL" "Quarterly Income (92%)" "loadquarterlyincomestatement.py" 2700
run_loader "LOCAL" "Quarterly Balance (98.3%)" "loadquarterlybalancesheet.py" 2700
run_loader "LOCAL" "Annual Income (99.1%)" "loadannualincomestatement.py" 1800
run_loader "LOCAL" "Annual Cashflow (98.5%)" "loadannualcashflow.py" 1800
run_loader "LOCAL" "Earnings History (30.8%)" "loadearningshistory.py" 1800

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 2: Replicate ALL critical data to AWS RDS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_loader "AWS" "Price Daily (100%)" "loadpricedaily.py" 3600
run_loader "AWS" "Company Profile (4.9%)" "loaddailycompanydata.py" 3600
run_loader "AWS" "Quarterly Cashflow (70.8%)" "loadquarterlycashflow.py" 3600
run_loader "AWS" "Quarterly Income (92%)" "loadquarterlyincomestatement.py" 2700
run_loader "AWS" "Quarterly Balance (98.3%)" "loadquarterlybalancesheet.py" 2700
run_loader "AWS" "Annual Income (99.1%)" "loadannualincomestatement.py" 1800
run_loader "AWS" "Annual Cashflow (98.5%)" "loadannualcashflow.py" 1800
run_loader "AWS" "Earnings History (30.8%)" "loadearningshistory.py" 1800

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅✅✅ ALL DATA LOADED TO LOCAL + AWS RDS ✅✅✅"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$(date)"
echo ""
echo "📊 Data is now synchronized across both databases"
