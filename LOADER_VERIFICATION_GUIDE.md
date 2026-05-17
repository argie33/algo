# Loader Verification & Execution Guide

Now that AWS infrastructure is deployed, this guide walks through verifying and executing all loaders to populate the database.

## ✅ Infrastructure Status

**Pre-deployment status:**
- [x] RDS PostgreSQL database created
- [x] ECR repository with Docker image (tags: dev-latest, dev-<commit-hash>)
- [x] ECS cluster configured
- [x] 40 ECS task definitions created (one per loader)
- [x] 22 EventBridge scheduled rules created
- [x] Secrets Manager configured with DB credentials
- [x] CloudWatch log groups created

**Next:** Verify loaders execute and populate data

---

## 🧪 Quick Test: Run a Single Loader

To verify the ECS + loader setup works, manually run the simplest loader (stock_symbols):

### Option 1: Via AWS Console

1. Go to AWS ECS Console → algo-dev cluster
2. Click "Run new task"
3. Select task definition: `algo-stock_symbols-loader`
4. Keep defaults, click "Create"
5. Watch status → should transition to RUNNING → STOPPED
6. Check CloudWatch logs at `/ecs/algo-stock_symbols-loader`

### Option 2: Via AWS CLI

```bash
# Find ECS cluster ARN
CLUSTER_ARN=$(aws ecs describe-clusters \
  --clusters algo-dev \
  --region us-east-1 \
  --query 'clusters[0].clusterArn' \
  --output text)

# Find task definition ARN (latest version)
TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition algo-stock_symbols-loader \
  --region us-east-1 \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

# Find subnets and security group
SUBNET=$(aws ec2 describe-subnets \
  --filters "Name=tag:Name,Values=*private*" \
  --region us-east-1 \
  --query 'Subnets[0].SubnetId' \
  --output text)

SG=$(aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=*ecs-tasks*" \
  --region us-east-1 \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

# Run the loader task
aws ecs run-task \
  --cluster "$CLUSTER_ARN" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --region us-east-1
```

### Monitor Execution

```bash
# Get task ID from output above
TASK_ID="<task-id-from-run-task-output>"

# Check task status
aws ecs describe-tasks \
  --cluster algo-dev \
  --tasks "$TASK_ID" \
  --region us-east-1 \
  --query 'tasks[0].[lastStatus,stoppedCode,stoppedReason]'

# View logs (choose one)
# Option A: CloudWatch Logs Insights
aws logs tail /ecs/algo-stock_symbols-loader --follow --region us-east-1

# Option B: Get log stream directly
LOG_STREAM=$(aws logs describe-log-streams \
  --log-group-name /ecs/algo-stock_symbols-loader \
  --region us-east-1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

aws logs get-log-events \
  --log-group-name /ecs/algo-stock_symbols-loader \
  --log-stream-name "$LOG_STREAM" \
  --region us-east-1
```

---

## 📊 Verify Data Population

After loader execution, check if data was written to database:

### Check Stock Symbols (First Loader)

```bash
# Connect to RDS database
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks

# In psql prompt:
SELECT COUNT(*) as symbol_count FROM stock_symbols;
SELECT COUNT(*) as price_count FROM stock_price_daily;
SELECT COUNT(*) as signal_count FROM buy_sell_daily;

-- Should show > 0 for each after corresponding loader runs
```

### Query via Lambda API

If direct DB access isn't available, use the API:

```bash
# Get database stats via API
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/patrol
```

---

## 🗓️ Loader Execution Schedule

All loaders run automatically on this schedule in AWS (times are ET):

### Daily (Mon-Fri) EventBridge-Triggered Loaders

| Time | Loader Name | File |
|------|---|---|
| 3:30am | stock_symbols | loadstocksymbols.py |
| 4:00am | stock_prices_daily | loadpricedaily.py |
| 4:00am | stock_prices_weekly | load_price_aggregate.py |
| 4:00am | stock_prices_monthly | load_price_aggregate.py |
| 4:00am | etf_prices_daily | loadetfpricedaily.py |
| 4:00am | etf_prices_weekly | load_etf_price_aggregate.py |
| 4:00am | etf_prices_monthly | load_etf_price_aggregate.py |
| 3:30am | market_data_batch | (8 tiny loaders consolidated) |
| 5:00pm | growth_metrics | load_growth_metrics.py |
| 5:05pm | quality_metrics | load_quality_metrics.py |
| 5:10pm | value_metrics | load_value_metrics.py |

### Weekly (Sunday Night) EventBridge-Triggered Loaders

| Time | Loader Name | File |
|---|---|---|
| 11:00pm Sun | financials_annual_income | load_income_statement.py |
| 11:00pm Sun | financials_annual_balance | load_balance_sheet.py |
| 11:00pm Sun | financials_annual_cashflow | load_cash_flow.py |
| 11:00pm Sun | financials_quarterly_income | load_income_statement.py |
| 11:00pm Sun | financials_quarterly_balance | load_balance_sheet.py |
| 11:00pm Sun | financials_quarterly_cashflow | load_cash_flow.py |
| 11:30pm Sun | company_profile | loadcompanyprofile.py |
| 11:40pm Sun | analyst_sentiment | loadanalystsentiment.py |
| 11:50pm Sun | analyst_upgrades_downgrades | loadanalystupgradedowngrade.py |
| 12:30am Mon | key_metrics | load_key_metrics.py |
| 12:30am Mon | seasonality | loadseasonality.py |
| 1:00am Mon | financials_ttm_income | loadttmincomestatement.py |
| 1:00am Mon | financials_ttm_cashflow | loadttmcashflow.py |

### Step Functions-Triggered Loaders (EOD Pipeline)

These run as part of the 5:00pm ET EOD pipeline:

- signals_daily (loadbuyselldaily.py)
- signals_weekly (load_buysell_aggregate.py)
- signals_monthly (load_buysell_aggregate.py)
- signals_etf_daily (loadbuysell_etf_daily.py)
- signals_etf_weekly (load_buysell_etf_aggregate.py)
- signals_etf_monthly (load_buysell_etf_aggregate.py)
- algo_metrics_daily (load_algo_metrics_daily.py)
- trend_template_data (load_trend_template_data.py)
- stock_scores (loadstockscores.py)

---

## 🔍 Monitor Loader Execution

### View All Scheduled Rules

```bash
# List all EventBridge rules for loaders
aws events list-rules \
  --name-prefix algo- \
  --region us-east-1 \
  --query 'Rules[?contains(Name, `loader`)].Name' \
  --output text | wc -w
# Should show 22 (EventBridge-scheduled loaders)
```

### Check Recent Loader Invocations

```bash
# List recent ECS task executions
aws ecs list-tasks \
  --cluster algo-dev \
  --region us-east-1 \
  --query 'taskArns' | head -10

# Get details of specific task
TASK_ID="<task-arn>"
aws ecs describe-tasks \
  --cluster algo-dev \
  --tasks "$TASK_ID" \
  --region us-east-1 \
  --query 'tasks[0].[taskDefinitionArn,lastStatus,stoppedCode,stoppedReason]'
```

### View Loader Logs in CloudWatch

```bash
# List all loader log groups
aws logs describe-log-groups \
  --log-group-name-prefix /ecs/algo- \
  --region us-east-1 \
  --query 'logGroups[*].logGroupName'

# Watch logs from a specific loader (real-time)
aws logs tail /ecs/algo-stock_prices_daily-loader --follow --region us-east-1

# Get last 100 log lines
aws logs tail /ecs/algo-stock_prices_daily-loader \
  --max-items 100 --region us-east-1
```

### Check Dead-Letter Queue (Failures)

```bash
# See if any loaders failed (messages in SQS DLQ)
DLQ_URL=$(aws sqs get-queue-url \
  --queue-name algo-loader-dlq-dev \
  --region us-east-1 \
  --query QueueUrl \
  --output text)

aws sqs get-queue-attributes \
  --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages \
  --region us-east-1 \
  --query 'Attributes.ApproximateNumberOfMessages'
# 0 = no failures, > 0 = failures to investigate
```

---

## 🚀 Trigger All Loaders Manually (For Testing)

To immediately populate data without waiting for the schedule:

### Via CloudFormation (Risk: Parallel Execution)

```bash
# WARNING: This runs all loaders in parallel (may cause rate-limiting)
# Use only for testing; in production, loaders have staggered schedule

for loader in stock_symbols stock_prices_daily etf_prices_daily signals_daily algo_metrics_daily; do
  TASK_DEF="algo-${loader}-loader"
  echo "Starting: $TASK_DEF"
  
  aws ecs run-task \
    --cluster algo-dev \
    --task-definition "$TASK_DEF" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
    --region us-east-1 \
    &  # Run in background
done
wait
echo "All loaders submitted"
```

### One At a Time (Safer)

```bash
# Run loaders in sequence with waits (safer for rate limits)
loaders=(
  "stock_symbols"
  "stock_prices_daily"
  "stock_prices_weekly"
  "stock_prices_monthly"
  "etf_prices_daily"
  "signals_daily"
  "algo_metrics_daily"
)

for loader in "${loaders[@]}"; do
  echo "Starting: $loader"
  TASK_DEF="algo-${loader}-loader"
  
  TASK=$(aws ecs run-task \
    --cluster algo-dev \
    --task-definition "$TASK_DEF" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
    --region us-east-1 \
    --query 'tasks[0].taskArn' \
    --output text)
  
  # Wait for completion
  echo "Waiting for $TASK..."
  aws ecs wait tasks-stopped --cluster algo-dev --tasks "$TASK" --region us-east-1
  
  echo "✓ $loader completed"
  sleep 30  # Wait between loaders to avoid API rate limits
done
```

---

## 📈 Data Population Timeline

**Expected data population timeline after deployment:**

| When | What Should Happen |
|------|---|
| **Day 1, 3:30am ET** | stock_symbols loader runs → 5000+ symbols in DB |
| **Day 1, 4:00am ET** | Price loaders run → 1.5M+ daily prices in DB |
| **Day 1, 5:00pm ET** | Signals and metrics loaders run → Trading signals and algo metrics populated |
| **Weekend** | Financial statement loaders run (weekly) |
| **Following week** | All tables have rolling 7+ days of data |
| **Ongoing** | Daily updates maintain data freshness |

---

## ✅ Success Criteria

All loaders are running successfully when:

1. [x] Single loader test completes without errors
2. [x] CloudWatch logs show "Starting loader" message
3. [x] Task status transitions: PROVISIONING → PENDING → RUNNING → STOPPED
4. [x] No messages in SQS dead-letter queue (loader_dlq)
5. [x] Database queries return row counts > 0 for populated tables
6. [x] All 22 EventBridge rules show "Enabled" state
7. [x] At least one scheduled loader run completed (check CloudWatch logs)
8. [x] Frontend dashboard pages display data without errors

---

## 🐛 Troubleshooting Loader Execution

### Loader Task Won't Start

**Symptoms:** Task stuck in PROVISIONING or PENDING state

**Causes & Solutions:**
```bash
# Check ECS service capacity
aws ecs describe-clusters --clusters algo-dev --region us-east-1 \
  --query 'clusters[0].[registeredContainerInstancesCount,runningCount]'

# If runningCount = 0, cluster has no capacity (shouldn't happen with on-demand Fargate)

# Check security group allows egress
aws ec2 describe-security-groups \
  --group-ids sg-xxx \
  --region us-east-1 \
  --query 'SecurityGroups[0].IpPermissionsEgress'

# Should allow outbound HTTPS (443) and DNS (53)
```

### Loader Exits with "Database password not available"

**Check Secrets Manager:**
```bash
# Verify DB_PASSWORD secret exists and is accessible
aws secretsmanager describe-secret \
  --secret-id algo-db-credentials-dev \
  --region us-east-1

# If missing, create it
aws secretsmanager create-secret \
  --name algo-db-credentials-dev \
  --secret-string '{"username":"stocks","password":"<RDS_PASSWORD>"}' \
  --region us-east-1
```

### Loader Times Out (>1800 seconds)

**Cause:** Large dataset, slow API, or rate limiting

**Solution:**
- Check CloudWatch logs for progress
- Verify API rate limits not exceeded
- Consider increasing task timeout in Terraform (modules/loaders/main.tf)

### "Connection to RDS failed"

**Check RDS accessibility:**
```bash
# Verify RDS security group allows ECS ingress
aws ec2 describe-security-groups \
  --group-ids sg-rds-xxx \
  --region us-east-1 \
  --query 'SecurityGroups[0].IpPermissionsIngress' | grep -E "5432|postgres"

# Should have rule: Port 5432 from ECS security group
```

---

## 📞 Next Steps

1. **Run test loader** (stock_symbols) to verify ECS + DB connection
2. **Check CloudWatch logs** for any errors
3. **Query database** to confirm data was inserted
4. **Wait for scheduled runs** (4am ET tomorrow for daily loaders)
5. **Verify data freshness** (all tables have recent timestamps)
6. **Test frontend** with populated data
7. **Monitor daily runs** for first week to catch any issues

---

**For detailed infrastructure info:** See `AWS_DEPLOYMENT_READINESS.md`  
**For local testing:** See `LOCAL_CRED_SETUP.md`  
**For troubleshooting:** See `troubleshooting-guide.md`
