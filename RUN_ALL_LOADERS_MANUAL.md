# Manual Execution of All 40 Loaders in AWS

**Goal:** Run all 40 loaders sequentially, verify each completes successfully, confirm data is populated. **Don't rely on schedules until this is proven.**

## Quick Start: Get AWS Resources

```bash
# Get resource IDs (copy-paste this entire block)
CLUSTER_ARN=$(aws ecs describe-clusters --clusters algo-dev --region us-east-1 --query 'clusters[0].clusterArn' --output text)
SUBNET=$(aws ec2 describe-subnets --filters "Name=tag:Name,Values=*private*" --region us-east-1 --query 'Subnets[0].SubnetId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=tag:Name,Values=*ecs-tasks*" --region us-east-1 --query 'SecurityGroups[0].GroupId' --output text)
export CLUSTER_ARN SUBNET SG CLUSTER="algo-dev" REGION="us-east-1"
export DB_HOST="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com" DB_USER="stocks" DB_NAME="stocks"

echo "Ready. CLUSTER_ARN=$CLUSTER_ARN, SUBNET=$SUBNET, SG=$SG"
```

## Run Test Loader (Stock Symbols) - 3 minutes

```bash
# Start loader
TASK=$(aws ecs run-task \
  --cluster "$CLUSTER_ARN" \
  --task-definition algo-stock_symbols-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --region $REGION \
  --query 'tasks[0].taskArn' \
  --output text)

echo "Task: $TASK"

# Watch logs
aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1

# Verify
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -t -c "SELECT COUNT(*) as symbols FROM stock_symbols;"
```

Expected result: 5000+ symbols

## Run All 40 Loaders - ~6 hours

Once test passes, run all loaders in order:

```bash
# Tier 0: Symbols (done above)

# Tier 1: Prices (7 loaders, 60 min)
for loader in stock_prices_daily stock_prices_weekly stock_prices_monthly etf_prices_daily etf_prices_weekly etf_prices_monthly market_data_batch; do
  echo "Starting: $loader"
  aws ecs run-task --cluster "$CLUSTER_ARN" --task-definition "algo-${loader}-loader" --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" --region $REGION --output text > /dev/null
  sleep 300  # 5 min between starts
done
sleep 2700  # Wait for all to finish

# Tier 2: Financials (12 loaders, 120 min)
for loader in financials_annual_income financials_annual_balance financials_annual_cashflow financials_quarterly_income financials_quarterly_balance financials_quarterly_cashflow key_metrics growth_metrics quality_metrics value_metrics company_profile earnings_calendar; do
  echo "Starting: $loader"
  aws ecs run-task --cluster "$CLUSTER_ARN" --task-definition "algo-${loader}-loader" --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" --region $REGION --output text > /dev/null
  sleep 300
done
sleep 4800  # Wait for all

# Tier 3: Analysis (10 loaders, 90 min)
for loader in analyst_sentiment analyst_upgrades_downgrades earnings_history earnings_revisions earnings_surprise market_indices seasonality econ_data aaiidata feargreed; do
  echo "Starting: $loader"
  aws ecs run-task --cluster "$CLUSTER_ARN" --task-definition "algo-${loader}-loader" --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" --region $REGION --output text > /dev/null
  sleep 300
done
sleep 3600  # Wait for all

# Tier 4: Signals (7 loaders, 90 min)
for loader in signals_daily signals_weekly signals_monthly signals_etf_daily signals_etf_weekly signals_etf_monthly algo_metrics_daily; do
  echo "Starting: $loader"
  aws ecs run-task --cluster "$CLUSTER_ARN" --task-definition "algo-${loader}-loader" --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" --region $REGION --output text > /dev/null
  sleep 300
done
sleep 3600  # Wait for all

# Tier 5: Additional (4 loaders, 45 min)
for loader in naaim_data sectors industry_ranking stock_scores; do
  echo "Starting: $loader"
  aws ecs run-task --cluster "$CLUSTER_ARN" --task-definition "algo-${loader}-loader" --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" --region $REGION --output text > /dev/null
  sleep 300
done
sleep 2700  # Wait for all
```

## Final Verification

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<'SQLEOF'
SELECT 'stock_symbols' as table_name, COUNT(*) as row_count FROM stock_symbols
UNION ALL
SELECT 'stock_price_daily', COUNT(*) FROM stock_price_daily
UNION ALL
SELECT 'buy_sell_daily', COUNT(*) FROM buy_sell_daily
UNION ALL
SELECT 'algo_metrics', COUNT(*) FROM algo_metrics
ORDER BY row_count DESC;
SQLEOF
```

Expected: stock_price_daily > 1M, buy_sell_daily > 50K, algo_metrics > 100

## Check for Failures

```bash
# View logs from a specific loader
aws logs tail /ecs/algo-stock_prices_daily-loader --region us-east-1 --max-items 50

# Check dead-letter queue (failures)
DLQ_URL=$(aws sqs get-queue-url --queue-name algo-loader-dlq-dev --region us-east-1 --output text)
aws sqs receive-message --queue-url $DLQ_URL --max-number-of-messages 10 --region us-east-1
```

**If any loader fails:** Check CloudWatch logs for error messages, fix the issue, re-run that loader.

---

**Timeline:** 6-8 hours total. Start it, monitor the key ones, everything else runs in background. Once all 40 pass, you can trust the schedules.**
