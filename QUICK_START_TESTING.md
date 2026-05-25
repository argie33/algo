# Quick Start Testing Guide - May 24, 2026

## 1️⃣ After Terraform Apply (5 min)

### Verify API Lambda is Deployed
```bash
# Check the Lambda was updated
aws lambda get-function --function-name algo-api-dev \
  --query 'Configuration.[Timeout,MemorySize]' \
  --output text

# Expected output: 300 128 (timeout=300s, memory=128MB)
```

### Test API Health Endpoint
```bash
# Get API Gateway endpoint
API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query 'Items[0].ApiEndpoint' --output text)

# Test health (should return 200)
curl -s ${API_ENDPOINT}/health | jq .

# Test detailed health (shows database connection)
curl -s ${API_ENDPOINT}/api/health/detailed | jq .
```

---

## 2️⃣ Verify Database and Data Flow (10-20 min)

### Run Diagnostic Script (locally, needs AWS DB access)
```bash
cd ~/code/algo
python3 scripts/diagnose_deployment.py

# This will check:
# - Database connectivity ✓
# - Table population (rows, freshness)
# - Loader status
# - Environment variables
# - Orchestrator config
```

### Manual Data Checks (if diagnostic not available)
```bash
# Connect to RDS database
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U stocks -d stocks -W

# Check key tables have data
SELECT COUNT(*) FROM price_daily;
SELECT COUNT(*) FROM technical_data_daily;
SELECT COUNT(*) FROM buy_sell_daily;
SELECT COUNT(*) FROM stock_scores;
SELECT COUNT(*) FROM data_loader_status;

# Check data age
SELECT table_name, MAX(last_updated) FROM data_loader_status GROUP BY table_name;
```

---

## 3️⃣ Test Loaders (20-30 min)

### Check EventBridge Rules
```bash
# List active EventBridge rules
aws events list-rules --name-prefix algo --state ENABLED

# Expected: 10+ enabled rules for different loaders
```

### Manually Trigger a Test Loader
```bash
# Trigger stock prices loader (should complete in 5-10 min)
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-stock-prices-daily-loader \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={
    subnets=[<PRIVATE_SUBNET_ID>],
    securityGroups=[<ECS_SG_ID>],
    assignPublicIp=DISABLED
  }'

# Get task ID from output and monitor
TASK_ID="<from above output>"
aws ecs describe-tasks --cluster algo-cluster --tasks ${TASK_ID}

# Check CloudWatch logs
aws logs tail /ecs/algo-cluster --follow

# After 5-10 min, verify data was loaded
psql -c "SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL '2 days';"
```

---

## 4️⃣ Test API Endpoints (10 min)

### Test Public Endpoints (no auth required)
```bash
API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query 'Items[0].ApiEndpoint' --output text)

# Test signals endpoint
curl -s ${API_ENDPOINT}/api/signals/stocks?limit=10 | jq '.items | length'
# Expected: > 0 if buy_sell_daily has data

# Test scores endpoint
curl -s ${API_ENDPOINT}/api/scores?limit=10 | jq '.items | length'
# Expected: > 0 if stock_scores has data

# Test prices endpoint
curl -s ${API_ENDPOINT}/api/prices/history/AAPL?limit=5 | jq '.items | length'
# Expected: > 0 if price_daily has data
```

### Check API Response Quality
```bash
# Inspect full response structure
curl -s ${API_ENDPOINT}/api/scores?limit=1 | jq '.'

# Expected fields:
# {
#   "statusCode": 200,
#   "items": [
#     {
#       "symbol": "...",
#       "composite_score": ...,
#       "current_price": ...,
#       ...
#     }
#   ]
# }
```

---

## 5️⃣ Test Orchestrator (5-15 min)

### Check Orchestrator Configuration
```bash
# Get orchestrator Lambda config
aws lambda get-function-configuration --function-name algo-algo-dev \
  --query 'Environment.Variables | {ORCHESTRATOR_DRY_RUN, ALPACA_PAPER_TRADING, DEV_MODE}'

# Expected:
# {
#   "ORCHESTRATOR_DRY_RUN": "false",
#   "ALPACA_PAPER_TRADING": "false",
#   "DEV_MODE": "false"
# }
```

### Invoke Orchestrator (Safety Check)
```bash
# Invoke orchestrator in dry-run mode first (safe test)
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{}' \
  --log-type Tail \
  /tmp/orchestrator-output.json \
  | jq '.LogResult' -r | base64 -d | tail -50

# Check for "SUCCESS" or error messages
```

### Monitor Orchestrator Logs
```bash
# Watch logs in real-time
aws logs tail /aws/lambda/algo-algo-dev --follow

# Look for:
# - "[ORCHESTRATOR] Starting 7-phase run"
# - "PHASE 1" through "PHASE 7"
# - Final status: "HALT" or "SUCCESS"
```

---

## 6️⃣ Test Frontend (5 min)

### Verify Frontend is Deployed
```bash
# Get CloudFront distribution
aws cloudfront list-distributions \
  --query 'DistributionList.Items[0].[DomainName,Enabled]' \
  --output text

# Expected: <domain> True

# Test frontend loads
curl -I https://d2u93283nn45h2.cloudfront.net
# Expected: HTTP/2 200
```

### Access Frontend in Browser
```
https://d2u93283nn45h2.cloudfront.net

Check:
☐ Home page loads
☐ Navigation works
☐ Can navigate to dashboards
☐ Check Network tab - API calls return 200
☐ Check Console - no JS errors
```

### Verify Data Display
```
Pages to test:
☐ Market Health - should show indices + sectors
☐ Scores Dashboard - should show stock rankings
☐ Trading Signals - should show buy/sell signals
☐ Algo Dashboard - should show trading metrics
```

---

## 7️⃣ Test Alpaca Integration (5 min)

### Check Alpaca Credentials
```bash
# Verify Alpaca API keys are set
aws secretsmanager get-secret-value --secret-id algo/alpaca \
  --query 'SecretString' | jq -r . | jq 'keys'

# Expected: ["api_key", "secret_key"]
```

### Verify Live vs Paper Mode
```bash
# In orchestrator logs, look for:
# "ALPACA_PAPER_TRADING: false" → live trading
# "ALPACA_PAPER_TRADING: true"  → paper trading

aws lambda get-function-configuration --function-name algo-algo-dev \
  --query 'Environment.Variables.ALPACA_PAPER_TRADING'
```

### Monitor Alpaca Orders (if orchestrator is running)
```bash
# Check if any trades were executed
psql -c "SELECT symbol, side, qty, price, created_at FROM algo_trades ORDER BY created_at DESC LIMIT 5;"
```

---

## 🎯 Success Criteria Checklist

- [ ] API Lambda timeout increased to 300s
- [ ] API health endpoint returns 200 OK
- [ ] Database is reachable and populated
- [ ] Loaders are running and updating tables
- [ ] API endpoints return data (not 500 errors)
- [ ] Frontend loads and displays data
- [ ] Orchestrator phases run successfully
- [ ] Trading signals are generated
- [ ] Alpaca integration is active (live mode)

---

## 🔴 If Something Fails

### API Returns 500
```bash
# 1. Check logs
aws logs tail /aws/lambda/algo-api-dev

# 2. Look for errors related to:
# - Database connection (VPC/networking)
# - Secrets Manager access
# - Query execution
# - Missing tables

# 3. Common fixes:
# - Increase timeout (already done: 300s)
# - Check security group allows RDS port 5432
# - Verify Secrets Manager secret exists and readable
# - Check Lambda has IAM permissions
```

### Loaders Not Running
```bash
# 1. Check EventBridge rules
aws events list-rules --name-prefix algo

# 2. Check if rule is enabled
aws events describe-rule --name <rule-name>

# 3. Check ECS task permissions
aws iam get-role-policy --role-name algo-svc-ecs-task-dev --policy-name <policy-name>

# 4. Manually trigger and check logs
aws logs tail /ecs/algo-cluster --follow
```

### Orchestrator Phase Failures
```bash
# 1. Check phase-specific logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-algo-dev \
  --filter-pattern "PHASE 1"

# 2. Common reasons:
# - Data too old (> 7 days)
# - Missing required tables
# - Insufficient data in tables
# - Data patrol found critical issues

# 3. Fix data first, then retry orchestrator
```

---

## 📊 Performance Baselines (After Success)

- **API Health Response:** < 1 second
- **Scores API (5000 rows):** < 3 seconds  
- **Orchestrator Phase 1:** 10-30 seconds
- **Orchestrator Full Run:** 5-15 minutes
- **Loader Execution:** 5-30 minutes depending on data source

---

## 🚀 Next: Go Live

Once testing passes:
1. Review `LIVE_TRADING_CHECKLIST.md`
2. Verify all environment variables are correct
3. Confirm ORCHESTRATOR_DRY_RUN=false
4. Confirm ALPACA_PAPER_TRADING=false
5. Enable daily schedule in EventBridge
6. Monitor first live day's trades and P&L
