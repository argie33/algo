# System Activation Guide - Stock Analytics Platform (Algo)

## Current Status (May 24, 2026)

✅ **Code**: Deployed and working
✅ **API**: Lambda function tested, returns real data
✅ **Frontend**: React app built and ready (port 5173)
✅ **Database**: Connected, schema initialized
✅ **Loaders**: All 24 loaders configured with real data sources
❌ **Data**: 2 days old (May 22) - needs refresh
⚠️ **Live Trading**: Ready to enable (requires manual configuration)

---

## Quick Start: 3 Steps to Live Trading

### Step 1: Refresh Data (Today - May 24)

**Via GitHub Actions (Recommended):**
1. Go to: https://github.com/argie33/algo/actions
2. Select workflow: `Manual - Invoke Loaders`
3. Click `Run workflow`
4. Select `all` loaders
5. Wait ~5 minutes for loaders to complete
6. Verify: `SELECT MAX(date) FROM price_daily;` → should show today's date

**OR run locally (longer but works):**
```bash
python3 loaders/load_stock_prices_daily.py  # ~2-3 min
```

### Step 2: Verify Fresh Data in API

```bash
# Check API is returning today's data
curl -s http://localhost:3001/api/algo/swing-scores?limit=5 | jq '.data[0]'
# Should show real stocks with today's date
```

### Step 3: Enable Live Trading

**Prerequisites:**
- [ ] Data is fresh (from Step 1)
- [ ] Alpaca account is LIVE (not paper) with buying power > $0
- [ ] API keys rotated in last 90 days

**Enable Live Mode:**

In PowerShell, set these environment variables:
```powershell
$env:ALPACA_PAPER_TRADING = "false"
$env:ALGO_LIVE_TRADING = "I_UNDERSTAND_REAL_MONEY"
$env:APCA_API_BASE_URL = "https://api.alpaca.markets"
```

**Test with small trade:**
```bash
# Invoke orchestrator once (GitHub Actions → test-orchestrator.yml)
# or local: python3 algo/algo_orchestrator.py
```

Check Alpaca dashboard: Should see 1-5 share order placed.

---

## Detailed Steps by Component

### 1. DATA PIPELINE - Get Fresh Data

**Why**: Data is 2 days old. Fresh data is required for accurate signals.

**Option A: GitHub Actions (Best)**
- Workflow: `.github/workflows/manual-invoke-loaders.yml`
- Triggers: ECS Fargate tasks to load from real APIs (yfinance, FRED, SEC, etc.)
- Time: ~5 minutes
- Parallelism: Runs 6 loaders simultaneously
- Cost: ~$0.10 per run

**Option B: Local (Works but slow)**
- Command: `python3 loaders/load_stock_prices_daily.py`
- Requires: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, FRED_API_KEY
- Time: 15-30 minutes (full historical data)
- Cost: Free but uses your bandwidth

**Verify Success:**
```sql
-- Check latest data date
SELECT MAX(date) FROM price_daily;     -- should be today
SELECT MAX(date) FROM technical_data_daily;  -- should be today
SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;  -- should be > 0
```

### 2. FRONTEND - Verify Real Data Display

**Start Dev Servers:**
```bash
# Terminal 1: API
cd lambda/api && python3 dev_server.py
# API runs on http://localhost:3001

# Terminal 2: Frontend  
cd webapp/frontend && npm run dev
# Frontend runs on http://localhost:5173
```

**Visit Frontend:**
- URL: http://localhost:5173
- Should see: Real stock symbols with prices from today
- NOT "-" symbols (which indicate missing data)

**Test Pages:**
- Dashboard: Shows swing scores
- Portfolio: Shows P&L (empty until trades placed)
- Sector rotation: Shows sector strength
- Algo status: Shows last run details

### 3. DEPLOY TO AWS - Move to Production

**Prerequisite:**
- AWS account configured with OIDC (already set up)
- Terraform state in S3 (stocks-terraform-state bucket)

**Deploy Code:**
```bash
# Simple: Just code changes
git push main  
# → Triggers deploy-code.yml automatically
# → Tests, scan, code deploy to Lambda in 3-5 minutes

# With Infrastructure: Terraform + Lambda + ECS  
# 1. Make terraform changes in terraform/
# 2. git push main
# 3. Go to GitHub Actions
# 4. Manually trigger deploy-all-infrastructure.yml
# 5. Wait 10-15 minutes for terraform apply
```

**Verify Deployment:**
```bash
# Check Lambda function
aws lambda get-function --function-name algo-api-dev --region us-east-1

# Check RDS connectivity
aws rds describe-db-clusters --region us-east-1

# Check ECS cluster
aws ecs list-clusters --region us-east-1
```

### 4. LIVE TRADING - Enable Real Money Trading

**Safety Checklist (read before enabling):**

- [ ] Data is fresh (< 1 day old)
- [ ] Tested trade execution with paper mode first
- [ ] Alpaca account is LIVE (not paper)
- [ ] Buying power > $1,000 (minimum)
- [ ] API keys rotated in last 90 days
- [ ] Understands risk: Algo can trade real money
- [ ] Stop-loss rules are in place
- [ ] Position limits are conservative (< 5% per trade)

**Step-by-Step Enablement:**

1. **Set Environment Variables:**
```powershell
# PowerShell (persists in profile)
$env:ALPACA_PAPER_TRADING = "false"
$env:ALGO_LIVE_TRADING = "I_UNDERSTAND_REAL_MONEY"
$env:APCA_API_BASE_URL = "https://api.alpaca.markets"
```

2. **Test Single Trade (GitHub Actions):**
   - Go to https://github.com/argie33/algo/actions
   - Run workflow: `Manual - Test Orchestrator`
   - Check CloudWatch logs for trade execution
   - Verify Alpaca dashboard shows 1 small order (1-5 shares)

3. **Enable Scheduled Trading (EventBridge):**
   - Go to AWS → EventBridge
   - Enable rules: `algo-morning-trading` (9:30A ET)
   - Enable rules: `algo-evening-trading` (5:30P ET)
   - Orchestrator will automatically run and place trades

4. **Monitor:**
   - Check CloudWatch logs after each run
   - Monitor Alpaca dashboard daily
   - Track P&L on frontend Dashboard page

**Emergency Stop:**
- Disable EventBridge rules: `algo-morning-trading`, `algo-evening-trading`
- Unset `ALGO_LIVE_TRADING`
- Manually close positions in Alpaca dashboard
- Rotate API keys
- Post-mortem in GitHub Issues

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Database unavailable" | Check DB_HOST, DB_PASSWORD in env vars |
| No data showing on frontend | Run loaders first (Step 1) |
| Trades not executing | Check ALPACA_PAPER_TRADING=false (not true) |
| API returns 401 | Check Cognito config (dev mode skips auth) |
| Loaders timeout | Check RDS security group allows ECS tasks |
| Oscillating prices | Wait for loaders to complete (5 min) |

---

## File Reference

| Component | Key Files |
|-----------|-----------|
| Orchestrator | `algo/algo_orchestrator.py` (7-phase runner) |
| API | `lambda/api/lambda_function.py` + routes in `routes/` |
| Frontend | `webapp/frontend/src/` (React, Vite) |
| Loaders | `loaders/load_*.py` (24 total) |
| Database | `terraform/modules/database/init.sql` (schema) |
| Terraform | `terraform/main.tf` + `bootstrap.tf` |
| Workflows | `.github/workflows/` (GitHub Actions) |

---

## Next Steps

1. **NOW (May 24):** Trigger loaders via GitHub Actions
2. **THEN:** Verify fresh data on frontend 
3. **THEN:** Confirm small test trade works
4. **THEN:** Enable scheduled trading (optional, requires ALPACA_LIVE_TRADING)
5. **MONITOR:** Check CloudWatch + Alpaca daily

---

**Questions?** Check steering doc: `steering/algo.md`  
**Emergency?** Check troubleshooting table above
