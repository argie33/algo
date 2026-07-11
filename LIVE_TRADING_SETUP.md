# Live Trading Setup - Critical Fixes

## ⚠️ CRITICAL ISSUES ADDRESSED

### Issue 1: Alpaca Credentials Missing (BLOCKER)
**Problem:** System cannot trade because Alpaca API credentials are not configured.
**Evidence:** 
- `ALPACA_API_KEY_ID: NOT SET` in verification
- Secrets Manager contains empty credentials
- Database has no recent Alpaca API calls

**Fix:** Configure Alpaca credentials

```bash
# Step 1: Get your Alpaca credentials
# Log in to https://alpaca.markets → Dashboard → Settings → API Keys
# Copy: API Key ID and Secret Key

# Step 2: Set environment variables
export TF_VAR_alpaca_api_key_id="your-api-key-here"
export TF_VAR_alpaca_api_secret_key="your-secret-key-here"

# Step 3: Apply Terraform
cd terraform
terraform apply -auto-approve
cd ..

# Step 4: Deploy Lambda with credentials
gh workflow run deploy-api-lambda.yml

# Step 5: Wait 2-3 minutes for deployment

# Step 6: Verify connection
curl -H "Authorization: Bearer dev-admin" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio
```

### Issue 2: Lambda 503 Errors (VPC Cold Start)
**Problem:** Lambda returns 503 Service Unavailable on cold starts.
**Cause:** VPC cold-start timeout (15-40 seconds) exceeds API Gateway timeout (29 seconds).

**Fix:** Already configured in terraform.tfvars:
- `api_lambda_provisioned_concurrency = 1` ✓ Keeps instances warm
- `api_lambda_timeout = 40` ✓ Increased from 30s
- `api_lambda_reserved_concurrency = 20` ✓ Reserved capacity

**Verification:**
```bash
# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=algo-api-dev \
  --start-time 2026-07-10T00:00:00Z \
  --end-time 2026-07-12T00:00:00Z \
  --period 3600 \
  --statistics Average \
  --region us-east-1

# If Duration > 10000ms (10s): Cold start detected
# If provisioned_concurrency = 0: Need to enable
# If timeout < 30: Need to increase
```

### Issue 3: API Gateway 401 Auth Errors - FIXED
**Status:** ✅ Fixed in this session
- Added `ALLOW_DEV_TOKENS_TEST` configuration
- Dev tokens now work during testing
- For production: Cognito JWT required

## 🔧 Health Check - Full System

### Database Connection
```bash
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily"
# Should return: ~8.5 million
```

### Lambda Function
```bash
# Check if Lambda is deployed
aws lambda get-function-configuration \
  --function-name algo-api-dev \
  --region us-east-1 \
  --query 'Environment.Variables.APCA_API_KEY_ID'
# Should return: Your API Key ID (if credentials configured)
```

### Alpaca Paper Trading
```bash
# Test Alpaca connectivity
curl -H "Authorization: Bearer dev-admin" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio
# Should return: Portfolio data from Alpaca account
```

### Dashboard Data
```bash
# Local mode
python3 -m dashboard --local
# Should display: All 26 fetchers, portfolio, positions, trades
```

## 🚀 End-to-End Testing

### Step 1: Configure Alpaca (REQUIRED)
```bash
export TF_VAR_alpaca_api_key_id="your-key"
export TF_VAR_alpaca_api_secret_key="your-secret"
cd terraform && terraform apply -auto-approve && cd ..
gh workflow run deploy-api-lambda.yml
# Wait 2-3 minutes for Lambda deployment
```

### Step 2: Verify Connection
```bash
# Test Alpaca connection
curl -H "Authorization: Bearer dev-admin" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio
# Look for: "statusCode": 200 and Alpaca portfolio data
```

### Step 3: Start Dashboard
```bash
# Local mode (no AWS needed)
python3 api-pkg/dev_server.py
python3 -m dashboard --local

# OR AWS mode (after Alpaca setup)
python3 -m dashboard  # Uses Lambda endpoints
```

### Step 4: Verify Trading Readiness
Dashboard should display:
- ✓ Portfolio: Cash, positions, total value
- ✓ Positions: Open positions with entry prices
- ✓ Trades: Historical trades from Alpaca
- ✓ Signals: Buy/sell signals being generated
- ✓ Markets: Current market state
- ✓ Health: All data feeds green

### Step 5: Monitor Live Trading
Once everything is working, you can:

1. **Monitor through dashboard:**
   ```bash
   python3 -m dashboard --local  # Refreshes every 30 seconds
   ```

2. **Check execution logs:**
   ```bash
   aws logs tail /aws/lambda/algo-orchestrator-dev --follow
   ```

3. **Database status:**
   ```bash
   psql -h localhost -U stocks -d stocks -c \
     "SELECT COUNT(*) as open_positions FROM algo_positions WHERE status='open'"
   ```

## 🔍 Troubleshooting

### Dashboard shows "data not available"
```bash
# Check dev server is running
ps aux | grep dev_server.py

# Check database connection
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Restart dev server
python3 api-pkg/dev_server.py
```

### Lambda returns 401 "Authentication required"
```bash
# Verify dev tokens are enabled
aws lambda get-function-configuration \
  --function-name algo-api-dev \
  --query 'Environment.Variables.ALLOW_DEV_TOKENS_TEST'
# Should return: "true"

# If not, re-run:
terraform apply -var="allow_dev_tokens_test=true"
gh workflow run deploy-api-lambda.yml
```

### Lambda returns 503 "Service Unavailable"
```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/algo-api-dev --follow

# Common causes:
# 1. VPC cold start (check provisioned_concurrency)
# 2. Database connection timeout (check RDS connection pool)
# 3. Timeout too short (check api_lambda_timeout)

# Fix: Increase provisioned concurrency
terraform apply -var="api_lambda_provisioned_concurrency=3"
```

### Alpaca credentials not working
```bash
# Verify in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id algo-algo-secrets-dev \
  --region us-east-1 \
  --query 'SecretString'
# Should show APCA_API_KEY_ID and APCA_API_SECRET_KEY

# If empty, re-run:
export TF_VAR_alpaca_api_key_id="your-key"
export TF_VAR_alpaca_api_secret_key="your-secret"
cd terraform && terraform apply -auto-approve && cd ..
```

## ✅ Verification Checklist

### Prerequisites
- [ ] AWS credentials configured (aws configure)
- [ ] GitHub CLI installed (gh auth login)
- [ ] Alpaca account created (paper trading)
- [ ] Alpaca API keys obtained

### Configuration
- [ ] Alpaca credentials set via environment variables
- [ ] Terraform applied successfully
- [ ] Lambda deployed via GitHub Actions
- [ ] Credentials in Secrets Manager
- [ ] Dev tokens enabled (ALLOW_DEV_TOKENS_TEST=true)

### Connectivity
- [ ] Database: psql connection works
- [ ] Lambda: Returns 200 OK for /api/algo/portfolio
- [ ] Alpaca: Returns portfolio data
- [ ] Dashboard: All 26 fetchers load
- [ ] Markets: Current price data displayed

### Trading
- [ ] Signals being generated (buy_sell_daily table > 0 rows)
- [ ] Portfolio shows Alpaca account
- [ ] Positions show open trades
- [ ] Orchestrator scheduled (EventBridge)
- [ ] No errors in Lambda logs

## 🎯 Production Readiness

When ready to go live:

1. **Switch to Cognito auth:**
   ```bash
   terraform apply -var="allow_dev_tokens_test=false"
   gh workflow run deploy-api-lambda.yml
   ```

2. **Create production users:**
   - In AWS Cognito console, create users
   - Add users to appropriate groups (trader, analyst, admin)
   - Distribute credentials securely

3. **Enable live trading (if desired):**
   ```bash
   # Change Alpaca base URL to live API
   # terraform apply -var="alpaca_api_base_url=https://api.alpaca.markets"
   # CRITICAL: This uses REAL MONEY - be extremely careful
   ```

4. **Monitor in production:**
   - CloudWatch dashboards for API latency
   - SNS alerts for errors and cost
   - Data freshness monitoring
   - Portfolio monitoring

## 📞 Support

For issues:
1. Check troubleshooting section above
2. Review Lambda logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
3. Check RDS connection: `psql -h <rds-host> -U stocks -d stocks -c "SELECT 1"`
4. Verify Secrets Manager: `aws secretsmanager list-secrets --region us-east-1`

---

**Status:** System ready for live trading after Alpaca credentials are configured.
**Critical Path:** Set Alpaca credentials → Deploy → Verify → Start trading.
