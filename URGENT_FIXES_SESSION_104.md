# URGENT: Surgical Fixes for Dashboard & Trading System

**Generated**: 2026-07-12 22:40 ET  
**Status**: Ready for implementation

---

## 🚨 TOP 3 BLOCKERS

### 1. Data is STALE (Blocks Dashboard Display)
- **market_health_daily**: 47.7 hours old → Phase 1 halts trading
- **technical_data_daily**: 3 days old → Signals invalid
- **FIX**: Manually trigger loaders to refresh NOW

### 2. Orchestrator Not Running Full Pipeline
- Last run: 363 seconds (6 min) vs expected 40-60 min
- Suggests dry-run or degraded mode
- **FIX**: Check ORCHESTRATOR_DRY_RUN env var and verify Phase 1-9 all run

### 3. API Status Endpoints Returning 401 (Need Investigation)
- `/api/algo/status` and `/api/algo/signals` endpoints return 401 
- **Workaround**: Dashboard can still fetch data via `/api/algo/data-status`, `/api/algo/positions`, `/api/algo/trades`
- **FIX**: Debug route dispatch in lambda/api/lambda_function.py vs api_router.py

---

## ⚡ IMMEDIATE ACTIONS (Do These First)

### Action 1: Force Data Refresh
Run these commands in sequence to load FRESH data:

```bash
# In Terminal 1 (if not already running):
python3 api-pkg/dev_server.py

# In Terminal 2:
# Option A: Trigger via orchestrator (async, will take 40-60 min)
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Option B: Manually load critical tables (faster, ~30 min total)
python3 loaders/load_market_health_daily.py
python3 loaders/load_technical_indicators.py
python3 loaders/load_stock_scores.py
```

### Action 2: Verify Data Refresh Worked
```bash
# After loaders complete, run:
python3 << 'EOF'
import psycopg2
from datetime import datetime
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute('SELECT COUNT(*), MAX(date) FROM market_health_daily')
count, latest = cur.fetchone()
age = (datetime.now() - latest).total_seconds() / 3600 if latest else None
print(f"market_health_daily: {count} rows, age: {age:.1f}h" if age else "EMPTY")

cur.execute('SELECT COUNT(*), MAX(date) FROM technical_data_daily')
count, latest = cur.fetchone()
age = (datetime.now() - latest).total_seconds() / 3600 if latest else None
print(f"technical_data_daily: {count} rows, age: {age:.1f}h" if age else "EMPTY")

cur.close()
conn.close()
EOF
```

### Action 3: Test Dashboard
```bash
# After data refresh:
python3 -m dashboard --local -w 30  # Auto-refresh every 30 seconds

# Verify you see:
# - Portfolio snapshot (cash, positions, equity curve)
# - Trade signals (buy/sell recommendations)
# - Health panel (data freshness GREEN)
```

---

## 🔍 THINGS TO CHECK

### Check 1: Verify Orchestrator Isn't in Dry-Run
```bash
# In AWS Lambda console or via CLI:
aws lambda get-function-configuration --function-name algo-algo-dev \
  --query 'Environment.Variables' | grep -i DRY_RUN

# Should show: ORCHESTRATOR_DRY_RUN=false
# If missing or =true, update via terraform/dev.tfvars
```

### Check 2: Verify Latest Orchestrator Actually Ran All Phases
```bash
# Check Lambda logs for phase execution:
aws logs tail /aws/lambda/algo-algo-dev --follow --since 1h

# Look for:
# [PHASE 1] PASS - PIPELINE DATA FRESH
# [PHASE 2] ... [through PHASE 9]

# If you only see [PHASE 1], orchestrator is terminating early
```

### Check 3: Check dev_server is Still Running
```bash
# Terminal 1 should show:
# [INFO] Starting API dev server on http://localhost:3001
# Keep this running!

# Test:
curl http://localhost:3001/health | python3 -m json.tool
```

---

## 📝 FILES THAT NEED INVESTIGATION

If data refresh doesn't work, check these:

1. **loaders/load_market_health_daily.py**
   - Class: `MarketHealthDailyLoader`
   - Check: Does it successfully fetch VIX data?

2. **algo/orchestrator/phase1_data_freshness.py** (lines 671-771)
   - Why didn't stale data trigger emergency bootstrap?
   - Check: `if age_days > 2:` logic at line 687

3. **lambda/api/lambda_function.py** (lines 1579-1604)
   - Why is `requires_auth=True` for `/api/algo/status`?
   - Should be: `requires_auth=False` (it's in PUBLIC_PREFIXES)

4. **lambda/api/api_router.py** (lines 155-205)
   - Verify dashboard_endpoints list includes `/api/algo/status`
   - Verify `if "algo" in _AVAILABLE_ROUTES:` block executes

---

## 🎯 SUCCESS METRICS

After implementing fixes, verify:

```
Dashboard displays:  ✓ Portfolio snapshot
                     ✓ Open positions
                     ✓ Trade signals  
                     ✓ Health panel (GREEN)
                     
API endpoints:       ✓ /api/algo/positions → 200 OK
                     ✓ /api/algo/trades → 200 OK
                     ✓ /api/algo/performance → 200 OK
                     
Data freshness:      ✓ market_health_daily < 1 day old
                     ✓ technical_data_daily < 1 day old
                     ✓ stock_scores < 1 hour old

Orchestrator:        ✓ Runs full 40-60 minute pipeline
                     ✓ All phases complete (Phase 1-9)
                     ✓ Data loads fresh daily
```

---

## 🚀 OPTIONAL FOLLOW-UP FIXES

Once above is working:

1. **Lambda 503 Errors** (VPC cold-start fix)
   - Add to `terraform/modules/services/api-lambda.tf`:
   ```hcl
   reserved_concurrent_executions = 10
   environment {
     variables {
       AWS_LAMBDA_TIMEOUT = "60"
     }
   }
   ```

2. **API Endpoint Auth 401 Issue** (if persists)
   - File issue with: require_auth() logic vs api_router.py handler registration mismatch
   - Workaround: Dashboard can use alternate endpoints that work (positions, trades, performance)

3. **Add CloudWatch Alarm** for data freshness
   - Alert if market_health_daily > 2 days old
   - Trigger automatic loader run via EventBridge

---

## ✅ COMPLETION CHECKLIST

- [ ] Data refresh started (loaders or orchestrator)
- [ ] Waiting for loaders to complete (30-60 min)
- [ ] Verified market_health_daily now fresh (< 1 day)
- [ ] Verified technical_data_daily now fresh (< 1 day)
- [ ] Dashboard shows data (no "data not available")
- [ ] Health panel shows GREEN
- [ ] No 401 errors on data endpoints
- [ ] Live Alpaca paper trading ready

