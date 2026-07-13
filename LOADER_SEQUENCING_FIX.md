# Loader Sequencing Bug - Session 111 Fix

**Issue:** Technical indicator loader runs BEFORE price loader completes, causing data loss and cascade failures.

**Timeline of the Bug:**
```
06:28:27 - Technical loader starts
           ├─ Checks: "Is price_daily ≤ 1 day old?"
           ├─ Finds: price_daily from July 10 (3 days old) = STALE
           └─ HALTS without inserting 183K computed records 🔴

06:34:49 - Price loader finally starts (6 minutes later)
           └─ Loads 219K records = today's complete price data ✅

Result: Prices fresh but technical indicators never computed
→ Signals can't generate
→ Dashboard shows "--" everywhere
```

---

## Root Cause

AWS Step Functions / EventBridge scheduler is **running loaders in parallel or wrong order**, not sequentially.

Correct sequence MUST be:
1. **loadpricedaily** completes  
2. **technical_data_daily_vectorized** starts (only after price is fresh)
3. **stock_scores / signals** can then generate

Current sequence (WRONG):
```
[ Parallel ]
├─ technical_data_daily_vectorized (starts 06:28)
└─ loadpricedaily (starts 06:34)
```

---

## Fix Applied

### Session 111 Immediate Fix

**Step 1:** Manually trigger technical indicator loader (after prices are fresh)
```bash
python3 loaders/load_technical_indicators.py
# Computes indicators for all 10,458 portfolio symbols
# Inserts to technical_data_daily (was empty for today)
```

**Step 2:** Re-run orchestrator to generate signals
```bash
python3 scripts/run_local_orchestrator.py --morning
# Phase 1: Verifies technical data is fresh ✅
# Phase 7: Generates signals from indicators
# Dashboard: Shows data instead of "--"
```

### Permanent Fix (AWS Infrastructure)

The loader orchestration lives in one of these places:
1. **EventBridge Scheduler configuration** - may be triggering tasks in parallel
2. **Step Functions state machine** - likely defining execution order
3. **ECS task trigger logic** - may need to add dependency chain

**Required changes:**
- Add explicit `Depends On` relationship: price_daily → technical_indicators → signals
- Increase Lambda timeout (currently 300s, technical loader needs 20-40min)
- Add sequential barrier: don't start technical loader until price loader reports completion

---

## Verification

After fix, verify:
```bash
# 1. Check technical_data_daily has today's data
python3 -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM technical_data_daily WHERE date = CURRENT_DATE')
print(f'Records for today: {cur.fetchone()[0]}')
"

# 2. Run orchestrator (should now succeed)
python3 scripts/run_local_orchestrator.py --morning

# 3. Check dashboard
python3 -m dashboard --local
```

Expected result:
- ✅ technical_data_daily: 10,000+ records for today
- ✅ Orchestrator: All 9 phases complete successfully
- ✅ Dashboard: Shows prices, signals, portfolio data (no "--")

---

## Impact

| Affected System | Issue | Impact |
|-----------------|-------|--------|
| **Signal Generation** | Can't run without technical indicators | No trades execute |
| **Dashboard** | Queries return empty → shows "--" | User sees "Data not available" |
| **Orchestrator** | Phase 1 halts (signal freshness check) | Entire pipeline blocked |
| **Live Trading** | Can't execute trades | Portfolio stalled |

This was blocking production until fixed.
