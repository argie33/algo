# Active Monitoring Checklist - Deployment & Live Trading

## RIGHT NOW - Deployment is in progress

### Step 1: Monitor GitHub Actions Deployment (5 minutes)

**Open this URL in browser:**
```
https://github.com/argie33/algo/actions
```

**Watch for these steps (in order):**
```
✓ resolve-infra          (1-2 min)  — Get infrastructure names
✓ deploy-algo-lambda     (2 min)    — Upload Lambda code
✓ Configure Algo Lambda Environment Variables (1 min) ← CRITICAL STEP
  Look for credentials being set:
  - APCA_API_KEY_ID: PK3CYOVDIZ7T35XMNUJX6CIONG
  - APCA_API_SECRET_KEY: [configured]
  ✓ deploy-api-lambda    (2 min)    — Upload API code
✓ deploy-frontend        (2-3 min)  — Build & deploy React
```

**If any step fails (shows ❌):**
- Note the error message
- Go to GitHub Actions page and click "Re-run jobs"
- Wait 2-3 minutes for retry to complete

---

## AFTER Deployment Completes - Verify Credentials Injected

### Step 2: Verify Lambda Configuration (2 minutes)

**Run this command:**
```bash
aws lambda get-function-configuration \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --query 'Environment.Variables'
```

**Expected output:**
```json
{
  "APCA_API_KEY_ID": "PK3CYOVDIZ7T35XMNUJX6CIONG",
  "APCA_API_SECRET_KEY": "DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28",
  "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
  "ORCHESTRATOR_DRY_RUN": "false"
}
```

**If credentials are NOT present:**
- Credentials weren't injected
- GitHub Actions step may have failed silently
- **Fix**: Re-run GitHub Actions workflow or manually update via AWS Console:
  ```bash
  aws lambda update-function-configuration \
    --function-name algo-algo-dev \
    --environment Variables={APCA_API_KEY_ID=PK3CYOVDIZ7T35XMNUJX6CIONG,APCA_API_SECRET_KEY=DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28,APCA_API_BASE_URL=https://paper-api.alpaca.markets,ORCHESTRATOR_DRY_RUN=false}
  ```

---

## 9:20am ET (10 minutes before market open) - Pre-Market Testing

### Step 3: Run Phase 6 Readiness Test

**Test that Phase 6 will execute:**
```bash
# Test 1: Check credentials are in Lambda
aws lambda get-function-configuration \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --query 'Environment.Variables.[APCA_API_KEY_ID,APCA_API_SECRET_KEY]' \
  --output text

# Expected: PK3CYOVDIZ7T35XMNUJX6CIONG DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28

# Test 2: Check database connectivity
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM buy_sell_daily;"

# Expected: Number > 0

# Test 3: Check market stage
psql -h localhost -U stocks -d stocks -c \
  "SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1;"

# Expected: 2 or higher (allows trading)
```

**If any test fails:**
- Note the error
- See LIVE_MONITORING_GUIDE.md section "Critical Issues" for fix
- Fix and retest before market open

---

## 9:28am ET (2 minutes before market open) - Final Readiness

### Step 4: Open Monitoring Dashboards

**Open these in browser tabs (keep open during trading):**

1. **AWS Lambda Logs**
   ```
   https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%2Faws%2Flambda%2Falgo-algo-dev
   ```

2. **Your Dashboard**
   ```
   https://your-domain.com/dashboard
   ```

3. **Alpaca Account**
   ```
   https://paper.alpaca.markets/account
   ```

4. **GitHub Actions** (to see deployment logs)
   ```
   https://github.com/argie33/algo/actions
   ```

---

## 9:30am ET (MARKET OPEN) - Active Monitoring

### Step 5: Watch Orchestrator Execution

**Monitor these in real-time:**

**A. CloudWatch Logs (Real-time)**
```bash
# Watch logs as they appear
aws logs tail /aws/lambda/algo-algo-dev --follow

# You should see:
# - Orchestrator starting
# - Phase 1 running
# - Phase 2 running
# - Phase 3a running ← RECONCILIATION (NEW)
# - Phase 5 running
# - Phase 6 running ← ENTRY EXECUTION (NEW, PLACES ORDERS)
# - Phase 7 running
# - Final report
```

**B. Database Queries (Check every 10 seconds)**
```bash
# Check if trades executed
psql -h localhost -U stocks -d stocks -c \
  "SELECT symbol, action, quantity, price FROM algo_trades_daily 
   WHERE date = CURRENT_DATE AND created_at >= NOW() - INTERVAL '2 minutes';"

# Check positions
psql -h localhost -U stocks -d stocks -c \
  "SELECT symbol, quantity, avg_price FROM algo_positions_daily 
   WHERE date = CURRENT_DATE;"

# Check for errors
psql -h localhost -U stocks -d stocks -c \
  "SELECT phase, status, message FROM algo_audit_log 
   WHERE date = CURRENT_DATE ORDER BY created_at DESC LIMIT 20;"
```

**C. Alpaca Dashboard**
- Refresh https://paper.alpaca.markets/account every 30 seconds
- Should show new positions and orders if Phase 6 executed

**D. Your Dashboard**
- Should update automatically with trades, positions, P&L

---

## 9:35am ET - Verification

### Step 6: Confirm Everything Worked

**Check success criteria:**
```
✓ Lambda invoked at 9:30:00 (check CloudWatch logs timestamp)
✓ Phase 1-7 all show [OK] or [SUCCESS]
✓ Phase 3a shows [OK] (not [SKIP]) ← Must be present
✓ Phase 6 shows [OK] (not [SKIP]) ← Must place orders
✓ Trade count > 0 in database (if signals passed filters)
✓ Orders visible in Alpaca account
✓ Dashboard shows positions and P&L
```

**If Phase 6 shows [SKIP]:**
- Credentials not found in Lambda
- Check: `aws lambda get-function-configuration`
- Fix: Re-inject credentials and wait 30 seconds

**If no trades executed (but Phase 6 [OK]):**
- Signals were filtered out (normal if no qualifying signals)
- Check market stage: If < 2, circuit breaker working as designed
- Check filter logs: `SELECT * FROM algo_filter_pipeline_log WHERE date = CURRENT_DATE;`

---

## Issue Detection & Quick Fixes

### Common Issues During Deployment

| Issue | Detection | Fix |
|-------|-----------|-----|
| Credentials not injected | Phase 6 shows [SKIP] | Re-run GitHub Actions or manually update Lambda config |
| Database connection failed | Phase 1 [ERROR] | Ensure PostgreSQL is running locally |
| Market stage = 1 | Phase 2 [HALT] | Normal - circuit breaker working. Wait for stage change |
| No trades executed | Phase 6 [OK] but 0 trades | Check if signals passing all 6 filter tiers |
| Alpaca API errors | Phase 6 [ERROR] with HTTP error | Check credentials valid, check Alpaca status, check rate limits |

### Quick Fix Procedures

**Rerun Full Pipeline:**
```bash
# If something failed, rerun orchestrator manually
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  /tmp/response.json && \
cat /tmp/response.json
```

**Restart from Scratch (if needed):**
```bash
# 1. Clear any locks
rm /tmp/algo_orchestrator.lock 2>/dev/null

# 2. Re-deploy credentials
aws lambda update-function-configuration \
  --function-name algo-algo-dev \
  --environment Variables={APCA_API_KEY_ID=PK3CYOVDIZ7T35XMNUJX6CIONG,APCA_API_SECRET_KEY=DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28}

# 3. Wait 30 seconds for Lambda to update
sleep 30

# 4. Rerun
aws lambda invoke --function-name algo-algo-dev --region us-east-1 /tmp/response.json
```

---

## Success Criteria

**System is LIVE & WORKING when:**
1. ✅ GitHub Actions workflow completes with no errors
2. ✅ Lambda has APCA credentials in environment variables
3. ✅ At 9:30am: Lambda invoked (check logs timestamp)
4. ✅ At 9:30am: Phase 3a shows [OK]
5. ✅ At 9:30am: Phase 6 shows [OK]
6. ✅ At 9:30am: Orders in Alpaca account (if signals qualified)
7. ✅ Dashboard updates with trades and P&L

---

## Timeline Summary

| Time | Action | Estimated Duration |
|------|--------|-------------------|
| NOW | Deploy via GitHub Actions | 5 minutes |
| +5 min | Verify credentials injected | 2 minutes |
| +7 min | Ready for testing | - |
| 9:20am | Pre-market testing (optional) | 5 minutes |
| 9:28am | Open monitoring dashboards | 2 minutes |
| 9:30am | MARKET OPEN - Active monitoring | Continuous |
| 9:30:40 | Orchestrator completes | - |
| 9:35am | Verify success | 5 minutes |

---

## Your Role as Active Monitor

**You must:**
1. ✅ Watch GitHub Actions workflow complete
2. ✅ Verify credentials are injected into Lambda
3. ✅ Monitor Lambda logs at 9:30am
4. ✅ Watch for any Phase showing [ERROR] or [SKIP] unexpectedly
5. ✅ Check database for executed trades
6. ✅ Be ready to re-deploy or fix issues immediately

**You have:**
- LIVE_MONITORING_GUIDE.md (troubleshooting reference)
- CREDENTIAL_MANAGEMENT_AUDIT.md (credential info)
- GO_LIVE_INSTRUCTIONS.md (deployment steps)
- This checklist (step-by-step actions)

---

## Let's Go Live

System is deployed and ready.
You are monitoring.
We fix issues as they appear.

**This is it. Let's watch this thing run.**
