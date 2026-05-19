# Live Trading Deployment Checklist — Market Opens in ~8 Hours

**Status:** Code ✅ ready | Security ✅ verified | Deployment ⏳ in progress

## Phase 1: Credentials & AWS Setup (1 hour)

### Alpaca Paper Trading Keys
- [ ] Log in to https://app.alpaca.markets/settings/api-keys (paper trading)
- [ ] Verify paper keys exist (create new ones if needed, old keys compromised in git history)
- [ ] Copy `API_KEY_ID` and `API_SECRET_KEY`

### Store in AWS Secrets Manager
```bash
# Set AWS credentials first
aws configure  # or use GitHub Actions role

# Create/update Alpaca secret
aws secretsmanager create-secret \
  --name algo/alpaca \
  --secret-string '{"api_key":"YOUR_PAPER_KEY","api_secret":"YOUR_PAPER_SECRET"}' \
  --region us-east-1

# Verify
aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1
```

### FRED API Key
- [ ] Verify FRED key is current (fred.stlouisfed.org)
- [ ] Store in AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name algo/fred \
  --secret-string '{"api_key":"YOUR_FRED_KEY"}' \
  --region us-east-1
```

### Database Secrets
- [ ] Verify `algo/database` exists in AWS Secrets Manager with RDS endpoint, user, password
- [ ] Database should already be running (check AWS RDS console)

---

## Phase 2: Deploy to AWS (2 hours)

### Option A: Push to main (automatic CI/CD)
```bash
git add .
git commit -m "feat: ready for live trading"
git push origin main
# Wait for GitHub Actions to complete (check .github/workflows/deploy-code.yml)
```

### Option B: Manual deploy
```bash
# Build Lambda packages
cd lambda/algo_orchestrator && zip -r ../algo_lambda.zip . && cd ../..
cd lambda/api && zip -r ../api_lambda.zip . && cd ../..

# Deploy using AWS CLI
aws lambda update-function-code \
  --function-name stocks-algo-dev \
  --zip-file fileb://lambda_algo.zip \
  --region us-east-1

aws lambda update-function-code \
  --function-name stocks-api-dev \
  --zip-file fileb://lambda_api.zip \
  --region us-east-1
```

### Verify Deployment
```bash
# Check both Lambdas deployed
aws lambda get-function-configuration --function-name stocks-algo-dev --region us-east-1
aws lambda get-function-configuration --function-name stocks-api-dev --region us-east-1

# Check env vars include:
# - ORCHESTRATOR_DRY_RUN=false (or unset, defaults to false)
# - EXECUTION_MODE=paper
# - DB_SECRET_ARN (should point to algo/database)
```

---

## Phase 3: Configuration (30 min)

### Lambda Environment Variables
Both `stocks-algo-dev` and `stocks-api-dev` should have:
```
ORCHESTRATOR_DRY_RUN = false    (enables live trading mode)
EXECUTION_MODE = paper           (paper trading vs live)
DB_SECRET_ARN = arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:algo/database-XXXXX
```

### EventBridge Schedule (if using scheduled runs)
- [ ] Verify EventBridge rule exists that triggers algo Lambda
- [ ] Default: 9:30 AM ET weekdays (market open)
- [ ] Check rule is enabled

---

## Phase 4: Pre-Market Testing (1.5 hours)

### API Health Checks
```bash
# Test API is responding
curl -X GET https://YOUR_API_ENDPOINT/api/health

# Should return: {"status": "healthy"}
```

### Database Connectivity
```bash
# Test Lambda can connect to RDS
aws lambda invoke --function-name stocks-api-dev \
  --payload '{}' \
  --region us-east-1 \
  /tmp/response.json

cat /tmp/response.json
```

### Orchestrator Test Run
```bash
# Trigger algo Lambda manually
aws lambda invoke \
  --function-name stocks-algo-dev \
  --region us-east-1 \
  /tmp/test_run.json

cat /tmp/test_run.json
# Should show: "success": true, "dry_run": false
```

### Dashboard Connectivity
- [ ] Frontend loads (check CloudFront distribution)
- [ ] Can log in (Cognito or dev auth)
- [ ] API endpoints respond with data
- [ ] Signals display

---

## Phase 5: Go Live (market open)

### Confirm System Ready
- [ ] All tests passing ✅
- [ ] No errors in CloudWatch logs
- [ ] API responding normally
- [ ] Dashboard shows current day's data
- [ ] Orchestrator ready to run

### Monitor First Run
- [ ] Watch CloudWatch Logs for algo Lambda execution
- [ ] Check for any ERROR level logs
- [ ] Verify positions/trades execute in Alpaca paper account
- [ ] Check dashboard for signal generation

### Key Metrics to Watch
- Data freshness: all loaders running
- Signal generation: buy/sell candidates listed
- Trade execution: positions opening/closing
- P&L: paper account showing activity

---

## Troubleshooting Quick Reference

### Database Connection Fails
```
Check: DB_SECRET_ARN is correct and exists in Secrets Manager
Check: Lambda has VPC permissions to reach RDS
Check: RDS security group allows Lambda subnets
```

### Secrets Manager Not Found
```
Verify secret name: algo/alpaca, algo/fred, algo/database
Check: Secrets in us-east-1 region
Check: Lambda IAM role has secretsmanager:GetSecretValue permission
```

### Alpaca Connection Fails
```
Verify: API keys are valid (test in Alpaca dashboard)
Verify: Base URL is correct for paper trading
Verify: Not using live trading base URL by mistake
```

### Signal Generation Issues
```
Check: buy_sell_daily table is populated
Check: Price data is fresh (< 2 days old)
Check: Technical indicators computed (sma_50, rsi, etc.)
```

---

## Post-Market Checklist

- [ ] First trading day complete
- [ ] No major errors in logs
- [ ] Portfolio positions matched between Alpaca and dashboard
- [ ] Document any issues for next day improvement

---

## Critical Path Timeline
- **Now**: Set credentials (30 min)
- **+30 min**: Deploy to AWS (30 min)
- **+60 min**: Test connectivity (30 min)
- **+90 min**: Stress test edge cases (30 min)
- **+120 min**: Monitor system health (30 min)
- **+180 min**: Ready for market open ✅

**Deadline: Market opens in 8 hours**
