# Jun 6, 2026 — Comprehensive Action Guide

**Status:** LIVE SYSTEM VERIFICATION  
**Date:** Friday, Jun 6, 2026  
**Deadline:** 4:05 PM ET (Data Freshness Critical Check)  
**Owner:** User (Claude Code assisting)

## Timeline & Critical Actions

### 🕐 3:25-3:30 AM — Morning Prep Pipeline Start

**Action: Monitor pipeline trigger**
```bash
# Watch for morning-prep-pipeline task to start
aws logs tail /ecs/algo-loader --since 10m | grep "morning-prep-pipeline\|stock_prices_daily"
```

**Expected:** Task moves from PROVISIONING → PENDING → RUNNING within 1 minute

**Track:**
- [ ] Pipeline started at 3:30 AM ✓ or ✗
- [ ] No immediate task failures

---

### 🕐 8:00-8:30 AM — Morning Prep Completion Check

**Action: Verify all morning loaders completed**
```bash
# Check total duration and completion
aws logs tail /ecs/algo-loader --since 30m | grep -E "completed|duration|Failed"
```

**Success Criteria:**
- [ ] stock_prices_daily: Completed (90-120 min typical)
- [ ] technical_data_daily: Completed
- [ ] buy_sell_daily: Completed
- [ ] signal_quality_scores: Completed
- [ ] swing_trader_scores: Completed
- **Target: Completed by 8:00 AM (95-min buffer before 9:30 AM market open)**

**If Delayed:** Check RDS connections and yfinance API status.

---

### 🕐 9:30 AM — Market Open: Phase 1 Data Freshness Check

**Action: Monitor orchestrator Phase 1 startup**
```bash
aws logs tail /lambda/algo-algo-dev --since 5m | grep -E "Phase 1|HALT|freshness"
```

**Verify:**
- [ ] No "HALT" messages before Phase 1 completes
- [ ] All data freshness checks pass
- [ ] swing_trader_scores confirmed fresh (same day)

**What to watch for:**
- "SPY price data fresh" ✓
- "Market health data fresh" ✓  
- "Trend template data fresh" ✓

**If HALT occurs:** Check CloudWatch logs for specific data age. Escalate if halting at market open.

---

### 🕐 10:00 AM — Dev Server Chart Rendering Test

**Action: Start dev server and test charts**
```bash
cd webapp/frontend && npm run dev
# Opens on localhost:5180
```

**Navigate to:** `http://localhost:5180/markets`

**Test:** 
- [ ] Open DevTools Console (F12)
- [ ] Navigate through all pages (Markets, Dashboard, Sectors, Signals)
- [ ] Verify NO console warnings containing: "width", "height", "Recharts", "negative"
- [ ] Test responsive resize (drag window edge)

**Success:** Zero chart sizing warnings, all charts visible

**Escalation:** If warnings appear, revert commit c476d577 or check deployment.

---

### 🕐 4:05 PM — ⚠️ CRITICAL DEADLINE: Data Freshness Staleness Columns

**⚠️ THIS IS THE MOST IMPORTANT CHECK ⚠️**

**Action: Execute data freshness verification script**
```powershell
cd C:\Users\arger\code\algo
./scripts/check-data-freshness.ps1
```

**Expected Output:**
```
✓ SUCCESS: All staleness columns fully populated!
  Data patrol completed successfully.
```

**Record Results:**
- [ ] buy_sell_daily_age_days: __ (should be > 0)
- [ ] technical_data_age_days: __ (should be > 0)
- [ ] trend_template_age_days: __ (should be > 0)
- [ ] Timestamp: __

**If SUCCESS:** ✅ Data patrol completed. Phase 1 has freshness validation.

**If FAILURE (NULL values):**
```
✗ FAILURE: Some staleness columns are NULL
```

**Immediate Action if FAILURE:**
1. [ ] Check CloudWatch `/ecs/algo-loader` for Phase 5 errors
2. [ ] Check `/lambda/algo-algo-dev` for signal_quality_scores failures
3. [ ] Check RDS CPU/connections for saturation
4. [ ] Check yfinance API status
5. [ ] Document failure in memory for escalation

---

### 🕐 4:30 PM — EOD Pipeline Completion Check

**Action: Verify Step Functions execution completed**
```bash
# Check Step Functions state machine
aws stepfunctions describe-execution --execution-arn <execution-arn> --query 'status'
# Expected: SUCCEEDED

# Or check logs for Phase 5
aws logs tail /lambda/algo-algo-dev --since 30m | grep "Phase 5\|COMPLETED"
```

**Track:**
- [ ] All 9 core loaders completed
- [ ] Pipeline duration: __ minutes (target: <90 min)
- [ ] No "FAILED" status in Step Functions

---

### 🕐 5:00 PM — Signal Quality Baseline Check

**Action: Check Phase 5 filter rejection analysis**
```bash
aws logs tail /lambda/algo-algo-dev --since 2h | grep -A 5 "FILTER REJECTION ANALYSIS"
```

**Record:**
- [ ] Rejection count: __ (baseline was 8,756)
- [ ] Qualified signals: __ (baseline was 0-2/day)
- [ ] % reduction: __

**Success Criteria:**
- Rejection count down 30%+ from baseline
- Qualified signals trending upward

---

### 🕐 5:30 PM — Intraday Orchestrator Run

**Action: Monitor 5:30 PM orchestrator execution**
```bash
aws logs tail /lambda/algo-algo-dev --since 5m | grep -E "Phase 1|HALT"
```

**Verify:**
- [ ] Phase 1 passes (with or without warnings)
- [ ] No halt flags set
- [ ] All 7 phases complete

---

### 🕐 6:00 PM — End-of-Day Summary & Escalation Check

**Action: Fill out verification checklist**

## Verification Checklist (Complete by 6 PM)

### 1. Morning Prep Pipeline
- [ ] Started at 3:30 AM
- [ ] Completed by 8:00 AM
- **Actual Duration:** __ minutes
- **Status:** ✓ PASS / ✗ FAIL

### 2. Data Freshness (CRITICAL)
- [ ] Script executed at 4:05 PM
- [ ] buy_sell_daily_age_days: ✓ NON-NULL / ✗ NULL
- [ ] technical_data_age_days: ✓ NON-NULL / ✗ NULL
- [ ] trend_template_age_days: ✓ NON-NULL / ✗ NULL
- **Status:** ✓ ALL POPULATED / ✗ HAS NULLS

### 3. Chart Rendering (Dev Server)
- [ ] Tested at 10:00 AM
- [ ] Console warnings: __ (target: 0)
- [ ] All charts visible: ✓ YES / ✗ NO
- **Status:** ✓ PASS / ✗ FAIL

### 4. Signal Quality
- [ ] Rejection count: __
- [ ] Qualified signals: __
- [ ] % change from baseline: __
- **Status:** ✓ IMPROVING / ✗ STATIC / ✗ DECLINING

### 5. System Health (Overall)
- [ ] Phase 1 halts: 0 / __ count
- [ ] Loader failures: ✓ NONE / ✗ __ failures
- [ ] RDS connection issues: ✓ NONE / ✗ __ issues
- [ ] Chart rendering: ✓ CLEAN / ✗ __ warnings

---

## Escalation Criteria (Stop & Investigate If...)

### 🔴 CRITICAL — Halt Monitoring

**If any of these occur, STOP and investigate immediately:**

1. **Data Freshness Check FAILS (4:05 PM)**
   - Staleness columns contain NULL values
   - Indicates: Data patrol did not run
   - Action: Check EOD pipeline logs for failures, verify loaders completed
   - Impact: Phase 1 will NOT validate data freshness; trades may proceed with stale data

2. **Morning Prep Exceeds 5 Hours**
   - Not completed by 8:00 AM
   - Indicates: Pipeline bottleneck or RDS contention
   - Action: Check per-loader durations, RDS CPU/connections
   - Impact: May miss 9:30 AM window; Phase 1 grace period allows 1-day stale data only

3. **Any Loader Fails** (non-timeout)
   - CloudWatch logs show ERROR status
   - Indicates: Code issue or data issue
   - Action: Check specific error message in logs, investigate data format

4. **Chart Console Warnings** (localhost:5180)
   - "width(-1) or height(-1)" or similar sizing errors
   - Indicates: Recharts fix didn't work or was reverted
   - Action: Check commit c476d577 is deployed, restart dev server

5. **Phase 1 Halts for Data Reasons**
   - "Data is stale" error
   - Indicates: Freshness checks triggered failsafe
   - Action: Verify morning prep completed, check staleness columns populated

### 🟡 WARNING — Monitor Closely

- Morning prep takes 4.5+ hours (safe but tight margin)
- RDS connections exceed 50 (indicates load pressure)
- API Lambda shows 401/403 errors (IAM configuration issue)
- Signal rejection rate does NOT trend downward

---

## Post-Jun 6 Deliverables (by EOD)

**Update in memory:**
1. [ ] All verification checklist items filled
2. [ ] Any escalations documented with timestamps
3. [ ] Links to CloudWatch logs for evidence
4. [ ] Plan for Jun 7-11 if any issues found

**Files to update:**
- `monitoring_window_jun_5_11.md` → Add Jun 6 results under "Jun 6 (Fri) — Day 1"

---

## Key Contacts & Escalation

**If system FAILS to verify:**
- Check CloudWatch logs for root cause
- Verify RDS Proxy is active: `aws rds describe-db-proxies --query 'DBProxies[?DBProxyName==\`algo-rds-proxy-dev\`].Status'`
- Check yfinance API status: `curl -s https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL`
- Review commit history for recent changes

**Monitoring Commands Quick Reference:**
```bash
# Morning prep logs
aws logs tail /ecs/algo-loader --grep "stock_prices_daily\|technical_data_daily"

# Orchestrator logs (all phases)
aws logs tail /lambda/algo-algo-dev --since 1h

# RDS connection pool health
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=algo-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) --period 300 --statistics Maximum

# Halt flag status
python scripts/check_halt_flag.py
```

---

## Success Definition

**Jun 6 is SUCCESSFUL if:**
1. ✓ Morning prep completes by 8:00 AM
2. ✓ Data freshness staleness columns are ALL non-NULL by 4:05 PM
3. ✓ Phase 1 never halts for data reasons
4. ✓ Charts render without console warnings
5. ✓ Signal rejection count trends downward
6. ✓ No phase 5 errors logged

**Next Step (Jun 7-11):** Daily monitoring of same metrics. Goal is to establish stable baseline for signal quality optimization.
