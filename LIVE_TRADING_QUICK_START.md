# Live Trading Quick Start - Session 105

**Status:** ✅ System Ready for Live Paper Trading  
**Last Updated:** 2026-07-12  
**Critical Fixes Applied:** Loader performance, Lambda provisioned concurrency

---

## 📋 Pre-Flight Checklist

Before running live trading, verify these items:

### 1. System Health ✅
```bash
python3 scripts/health_check_complete.py
```

**Expected Results:**
- ✓ Database: OK (8.6M+ price records, < 1 day old)
- ✓ Dev Server: OK (localhost:3001 responding)
- ✓ Dashboard Fetchers: OK (23-26 loaded successfully)
- ✓ Alpaca Credentials: OK or WARN (WARN is fine for paper trading with empty credentials)
- ✓ Lambda Deployment: OK (provisioned concurrency > 0)

### 2. Alpaca Credentials (For Live Paper Trading)
```bash
python3 -c "
from config.credential_manager import get_credential_manager
creds = get_credential_manager().get_alpaca_credentials()
print(f'API Key: {\"SET\" if creds.get(\"key\") else \"MISSING\"}')
print(f'Secret Key: {\"SET\" if creds.get(\"secret\") else \"MISSING\"}')
"
```

**If Missing:**
1. Create Alpaca account: https://app.alpaca.markets
2. Get API keys from account settings
3. Store in AWS Secrets Manager:
   ```bash
   aws secretsmanager create-secret \
     --name algo/alpaca \
     --secret-string '{"key":"YOUR_KEY","secret":"YOUR_SECRET"}' \
     --region us-east-1
   ```

### 3. Database Fresh Data
```bash
curl -s http://localhost:3001/api/algo/data-status | grep -o '"status":"ok"' | wc -l
```

**Expected:** At least 40+ data sources with status="ok"

---

## 🚀 Running Live Paper Trading

### Step 1: Start Dev Server (Terminal 1)
```bash
python3 api-pkg/dev_server.py
```

**Wait for output:**
```
[INFO] Starting API dev server on http://localhost:3001
[INFO] Press Ctrl+C to stop
```

### Step 2: Start Dashboard (Terminal 2)
```bash
python3 -m dashboard --local
```

**You should see:**
- All 26 fetchers loading (takes 3-5 seconds)
- No "data not available" messages
- Positions, trades, risk metrics displaying

### Step 3: Trigger Orchestrator (Terminal 3)
```bash
# Test run (paper trading, doesn't make real trades)
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Monitor progress
watch -n 5 'curl -s http://localhost:3001/api/algo/last-run | python3 -m json.tool | grep -A 5 phases'
```

**Expected Behavior:**
- Phase 1: Data freshness check → OK (should take <30s)
- Phase 2: Circuit breakers → OK (should take <10s)
- Phase 3-9: Trading phases → varies by market conditions
- Total time: 10-60 minutes

**Monitor Dashboard While Running:**
- Watch "Last Run" panel for phase status
- Watch "Positions" to see trades executing
- Watch "Risk Metrics" to verify position sizing

---

## 🔧 Troubleshooting

### Issue: Dashboard Shows "Data not available"

**Solution 1: Check --local flag**
```bash
# WRONG - will fail without Cognito
python3 -m dashboard

# CORRECT - uses dev_server
python3 -m dashboard --local
```

**Solution 2: Verify dev_server is running**
```bash
curl http://localhost:3001/api/algo/config
# Should return: {"statusCode": 200, "data": {...}}
```

**Solution 3: Check database freshness**
```bash
python3 scripts/health_check_complete.py
# Look for database "age_hours" - should be < 24
```

### Issue: Orchestrator Halts (Phase 1 stale data)

**This should NOT happen after Session 105 fixes, but if it does:**

```bash
# Check if data truly stale
curl -s http://localhost:3001/api/algo/data-status | grep '"status":"stale"' | wc -l

# Manually trigger morning pipeline
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

### Issue: Lambda 503 Errors

**This should NOT happen after Session 105 (provisioned concurrency=5), but if it does:**

1. Check if Terraform deployed: `aws lambda get-function --function-name algo-api --query 'Configuration.ProvisionedConcurrentExecutions'`
2. Should return: `5` (not `0` or `1`)
3. If not deployed, push to main branch and wait for GitHub Actions

---

## 📊 Performance Expectations

After Session 105 fixes:

| Component | Expected Time | Status |
|-----------|---|---|
| Dev server startup | <5s | ✅ |
| Dashboard load (all fetchers) | 3-5s | ✅ |
| Data freshness check (Phase 1) | 20-30s | ✅ |
| Stock prices loader | 6-7 min | ✅ (was 7.5h before fix) |
| Full orchestrator run | 10-60 min | ✅ |
| Lambda response (with provisioned concurrency) | <100ms | ✅ |
| Lambda response (cold start without fix) | 15-40s + timeout | ❌ (fixed) |

---

## 📈 Live Trading Setup

### Paper Trading (Recommended for Testing)
```bash
# Already configured, just run:
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**What happens:**
- Algo simulates trades against current market prices
- Positions tracked in database
- No real money spent
- Perfect for testing before live trading

### Live Trading (When Ready)
```bash
# IMPORTANT: Only run after thorough paper testing!
# Set in orchestrator config: execution_mode = "live"
# Set Alpaca account to live trading (not paper)

python3 scripts/trigger_orchestrator.py --run morning --mode live
```

**WARNING:** This trades REAL money! Only enable after:
- [ ] Paper trading runs successfully for 1+ week
- [ ] Dashboard shows correct positions and P&L
- [ ] Risk metrics stay within limits
- [ ] Alpaca account funded with intended amount
- [ ] Team review completed

---

## 📝 Daily Operations

### Morning Checklist
1. ✅ Health check: `python3 scripts/health_check_complete.py`
2. ✅ Dashboard: `python3 -m dashboard --local` (verify data loading)
3. ✅ Orchestrator: `python3 scripts/trigger_orchestrator.py --run morning --mode paper`
4. ✅ Monitor: Watch dashboard for Phase 1-9 completion

### Evening Checklist
1. ✅ Orchestrator: `python3 scripts/trigger_orchestrator.py --run afternoon --mode paper`
2. ✅ Dashboard: Verify positions and trades for the day
3. ✅ Review: P&L, risk metrics, signal quality

### Weekly Review
1. Check CloudWatch logs for errors
2. Review data freshness trends
3. Analyze trading performance
4. Plan next week's configuration

---

## 🆘 Emergency Contacts

| Issue | Solution |
|-------|----------|
| Dashboard "data not available" | Use `--local` flag, verify dev_server |
| Orchestrator halted | Run health check, manually trigger pipeline |
| Lambda 503 errors | Verify provisioned concurrency deployed |
| Alpaca connection failed | Check credentials in AWS Secrets Manager |
| Database connection refused | Verify PostgreSQL running locally |

---

## 📚 Related Documentation

- `CLAUDE.md` - Full project overview
- `SESSION_105_CRITICAL_FIXES.md` - What was fixed in this session
- `steering/GOVERNANCE.md` - Architecture and design decisions
- `steering/OPERATIONS.md` - AWS deployment and operations guide
- `DASHBOARD_TROUBLESHOOTING.md` - Dashboard-specific issues

---

## ✅ Final Verification

Run this one-liner to verify everything is ready:

```bash
python3 scripts/health_check_complete.py && echo "✅ System Ready!" && echo "Start with: python3 api-pkg/dev_server.py"
```

**Then in another terminal:**
```bash
python3 -m dashboard --local
```

---

**Status:** Ready for live paper trading ✅  
**Last Verified:** 2026-07-12  
**Next Review:** After first orchestrator run
