# Deployment Guide: Lambda Functions & End-to-End Testing

This guide walks through deploying the fixed Lambda functions and verifying the system works end-to-end.

## Prerequisites

- GitHub Actions access to the repository
- AWS credentials configured
- Local database for testing (optional but recommended)

## Step 1: Verify Local System (DONE ✓)

All systems verified operational locally:
- Lambda handler imports: OK
- Database connectivity: OK
- Dashboard endpoints: OK (200 status)
- Orchestrator running: 14 runs/24h
- Trades executing: 12/7 days
- Signals generating: 10 active

## Step 2: Deploy Lambda Functions

### Option A: Via GitHub Actions (Recommended)

1. Go to GitHub Actions workflow: `deploy-api-lambda.yml`
2. Click "Run workflow"
3. Monitor the deployment:
   ```bash
   # Watch CI output
   gh run watch --exit-status
   ```

The deployment will:
- Validate code (linting, type checking)
- Package Lambda handler with all dependencies
- Deploy to AWS Lambda function: `algo-api-dev`
- Update LIVE alias to point to new version
- Provisioned concurrency (if enabled) will warm up instances

### Option B: Manual Deployment (if needed)

```bash
# Package the Lambda function
mkdir -p api-pkg
cp -r lambda/api/. api-pkg/
cp -r utils/. api-pkg/utils/
cp -r config/ api-pkg/config/
cp -r algo/ api-pkg/algo/
cp -r shared_contracts/. api-pkg/shared_contracts/

# Install dependencies
pip install -r lambda/api/requirements.txt -t api-pkg/ --platform manylinux2014_x86_64 --only-binary=:all: --quiet

# Create deployment package
cd api-pkg && zip -r ../api_lambda.zip . -x "*.pyc" -x "__pycache__/*"

# Deploy to AWS
aws lambda update-function-code \
  --function-name algo-api-dev \
  --zip-file fileb://../api_lambda.zip \
  --region us-east-1

# Publish version and update alias
NEW_VERSION=$(aws lambda publish-version --function-name algo-api-dev --region us-east-1 --query Version --output text)
aws lambda update-alias --function-name algo-api-dev --name LIVE --function-version $NEW_VERSION --region us-east-1
```

## Step 3: Verify Lambda Deployment

### Check Lambda Startup

```bash
# View Lambda logs for import errors
aws logs tail /aws/lambda/algo-api-dev --since 1m --follow

# Look for:
# ✓ "Handler index.handler successfully created"
# ✓ No MarketCalendar import errors
# ✓ No other import failures
```

### Test Health Endpoint

```bash
# Call health endpoint (no auth required)
curl -s https://api.alpaca-algo.com/api/health | jq .

# Should return:
# {
#   "statusCode": 200,
#   "data": {
#     "status": "healthy",
#     "version": "v2-2026-06-06",
#     "api_route_imports": {"status": "healthy", "failed_count": 0},
#     ...
#   }
# }
```

### Test Dashboard Endpoints

```bash
# Get authentication token (if required)
export JWT_TOKEN=$(aws cognito-idp admin-initiate-auth \
  --user-pool-id <pool-id> \
  --client-id <client-id> \
  --auth-flow ADMIN_NO_SRP_AUTH \
  --auth-parameters USERNAME=<user>,PASSWORD=<password> \
  --query 'AuthenticationResult.AccessToken' --output text)

# Test positions endpoint
curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  https://api.alpaca-algo.com/api/algo/positions | jq '.data.items | length'

# Should return number of open positions

# Test circuit breakers endpoint
curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  https://api.alpaca-algo.com/api/algo/circuit-breakers | jq '.data | keys'

# Should show: breakers, any_triggered, triggered_count, data_freshness
# Should NOT show: timestamp (we fixed this)
```

## Step 4: End-to-End Trading Verification

### Verify Orchestrator is Executing

```bash
# Check orchestrator runs in AWS CloudWatch or database
psql -h $DB_HOST -U $DB_USER -d stocks -c \
  "SELECT COUNT(*) FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '1 hour'"

# Should show runs in last hour
```

### Verify Signals are Generating

```bash
# Check active signals
psql -h $DB_HOST -U $DB_USER -d stocks -c \
  "SELECT COUNT(*) as active_signals FROM algo_signals WHERE signal_active = true"

# Should show 5+ signals if market open, 0+ if market closed
```

### Verify Trades are Executing

```bash
# Check recent trades
psql -h $DB_HOST -U $DB_USER -d stocks -c \
  "SELECT COUNT(*) as recent_trades FROM algo_trades WHERE DATE(created_at) >= CURRENT_DATE - 1"

# Should show active trading
```

### Verify Positions are Being Managed

```bash
# Check open positions
psql -h $DB_HOST -U $DB_USER -d stocks -c \
  "SELECT symbol, quantity, current_price, position_value FROM algo_positions WHERE status = 'open' ORDER BY position_value DESC"

# Should show active positions with current prices
```

## Step 5: Dashboard Verification

### Check All Panels Display Data

1. **Positions Panel**
   - Should show open positions (3+)
   - Each should show: symbol, quantity, entry price, current price, unrealized P&L
   - Should NOT show "data not available"

2. **Trades Panel**
   - Should show recent trades (10+)
   - Each should show: entry date, exit date, profit/loss, status
   - Should NOT show "data not available"

3. **Signals Panel**
   - Should show active signals (5+)
   - Each should show: symbol, signal quality, sector
   - Grade distribution should show A/B/C/D breakdown
   - Should NOT show "data not available"

4. **Circuit Breakers Panel**
   - Should show 9 circuit breaker checks
   - Each should show: current value, threshold, triggered status
   - Should NOT show schema validation errors

5. **Portfolio Panel**
   - Should show total portfolio value
   - Should show total cash
   - Should show position count
   - Daily return should be current

### Test Dashboard Refresh

```bash
# Open dashboard in browser
# Click refresh on each panel
# Verify data updates (should be <2 seconds for most panels)
# Check browser console for errors (should be none)
```

## Step 6: Troubleshooting Post-Deployment

### Lambda Still Returning 503

1. Check Lambda logs for errors:
   ```bash
   aws logs tail /aws/lambda/algo-api-dev --since 5m
   ```

2. Look for:
   - Import errors (should be none now)
   - Database connection failures
   - Timeout errors

3. If database connection fails:
   - Verify security group allows Lambda → RDS
   - Verify database credentials in Secrets Manager
   - Check RDS is in correct VPC

### Dashboard Shows "data not available"

1. Verify Lambda health endpoint returns 200
2. Check CloudWatch logs for API errors
3. Verify Cognito authentication (if required)
4. Check browser network tab for API response status

### Orchestrator Not Running

1. Check AWS Step Functions execution:
   ```bash
   aws stepfunctions describe-state-machine \
     --state-machine-arn arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:algo-orchestrator-dev
   ```

2. Check EventBridge scheduler:
   ```bash
   aws scheduler get-schedule --name algo-orchestrator-morning
   aws scheduler get-schedule --name algo-orchestrator-evening
   ```

## Step 7: Production Readiness Checklist

- [ ] Lambda functions deployed successfully
- [ ] Health endpoint returns 200
- [ ] All dashboard endpoints responding
- [ ] No import errors in Lambda logs
- [ ] Circuit breaker response has correct schema (no timestamp field)
- [ ] Orchestrator running and executing phases
- [ ] Signals generating (if market hours)
- [ ] Trades executing in paper mode
- [ ] Dashboard panels displaying data
- [ ] No "data not available" messages

## Success Criteria

✓ System is production-ready when:
1. Lambda health endpoint returns 200 OK
2. Dashboard displays data on all panels
3. Orchestrator executes without errors
4. Signals generate (market hours) or system waits correctly (market closed)
5. Trades execute in paper trading mode
6. All monitoring/alert systems operational

## Rollback Procedure

If deployment fails:

```bash
# Revert to previous Lambda version
aws lambda update-alias \
  --function-name algo-api-dev \
  --name LIVE \
  --function-version PREVIOUS_VERSION \
  --region us-east-1
```

## Next Steps

Once deployment verified:
1. Monitor CloudWatch metrics and logs
2. Verify daily orchestrator executions
3. Check signal generation and trade execution
4. Monitor dashboard usage and performance
5. Consider enabling live trading once paper mode verified stable
