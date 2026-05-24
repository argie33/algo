# Fix RDS Database Connectivity - IMMEDIATE ACTION

## Current Status
✅ Infrastructure deployed (API Gateway, Lambda, CloudFront, RDS, VPC)  
✅ Security groups configured  
✅ Network connectivity working  
❌ RDS database not initialized or unreachable  

## The Issue
API endpoint `https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api` returns:
```
{
  "error": "database_unavailable",
  "debug": {
    "db_host_configured": true,
    "db_secret_arn_configured": true,
    "message": "Unable to establish database connection..."
  }
}
```

This means:
- Lambda can execute ✓
- Database configuration exists ✓
- But connection fails ✗

## Solution: Initialize Database via GitHub Actions

### Step 1: Ensure GitHub has valid AWS credentials
The GitHub Actions workflow `deploy-code.yml` uses OIDC (not static credentials).

Go to: https://github.com/argie33/algo/settings/secrets/actions

Verify `AWS_ACCOUNT_ID` secret exists (needed for OIDC role assumption)

### Step 2: Run database initialization workflow
1. Go to: https://github.com/argie33/algo/actions
2. Click: **`deploy-code`** workflow
3. Click: **Run workflow** (use main branch)
4. Wait for job: **`deploy-db-init-lambda`**
   - This deploys Lambda to initialize RDS schema
   - Creates tables: price_daily, technical_data_daily, stock_scores, etc.
   - Takes 3-5 minutes

### Step 3: Verify database initialized
Once complete, test the API again:
```bash
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/signals
```

Should return JSON with trading signals (or empty array if no data yet).

### Step 4: Populate with real data
Once RDS works, run data loaders:

1. Go to: https://github.com/argie33/algo/actions
2. Click: **`manual-invoke-loaders`** workflow  
3. Select 2-3 loaders to start (e.g., `load_yfinance`, `load_technical_indicators`)
4. Wait 10 minutes for data to populate

### Step 5: Verify frontend loads with data
Once API returns data:
```bash
# Test API
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/signals | jq .

# Check frontend  
curl https://d5j1h4wzrkvw7.cloudfront.net  # Or visit in browser
```

## What Will Happen

Once this is done, you'll have:

**All Pages in AWS:**
- Dashboard (homepage) → Shows portfolio overview from API
- Signals page → Shows today's buy/sell signals
- Portfolio page → Shows current positions and P&L  
- Stock detail pages → Individual stock analysis
- Audit log → All trades executed

**Real Data Flowing:**
- Price data (yfinance, 5-min updates)
- Technical indicators (RSI, SMA, EMA, MACD)
- Fundamental metrics (P/E, debt ratios)
- Sentiment (AAII, Fear & Greed, NAAIM)
- Analyst ratings

**Live Trading Ready:**
- Orchestrator configured to run at 9:30A ET
- Alpaca integration live (just needs ALGO_LIVE_TRADING env var)
- Position monitoring and exit logic ready
- Circuit breakers in place

## If Database Init Fails

Common reasons and fixes:

**"VPC cold start timeout"**
- Expected on first deploy
- Rerun workflow — Lambda VPC ENI will be pre-warmed
- Should succeed on 2nd attempt

**"Failed to fetch credentials from Secrets Manager"**
- Check RDS_PASSWORD in GitHub Secrets (repo Settings → Secrets)
- Verify it matches what was set during Terraform apply

**"Connection timeout to RDS"**
- RDS might still be starting (takes 5-10 minutes)
- Wait 10 minutes and rerun

**"Duplicate key value violation"**
- Schema already initialized
- Safe to ignore — just means 2nd init attempt

## Expected Timeline

| Step | Time |
|------|------|
| Run deploy-code workflow | 3-5 min |
| Database schema initialized | Auto |
| Run data loaders | 10 min |
| Pages load with data | Auto |
| Ready for live trading | Now |

**Total: ~20 minutes to fully operational system**

## Command Line Check (if you have AWS CLI credentials)

```bash
# Verify API is responding
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/signals | jq .

# Check RDS is running (requires AWS CLI)
aws rds describe-db-instances --region us-east-1 | jq '.DBInstances[] | {ID: .DBInstanceIdentifier, Status: .DBInstanceStatus}'

# Check Lambda logs
aws logs tail /aws/lambda/algo-api-dev --follow --region us-east-1
```

---

**Action required:** Run GitHub Actions workflow `deploy-code.yml` to initialize the database.

Once done, the system will be fully operational with real data and live trading enabled.
