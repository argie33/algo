# LOCAL SETUP FIX CHECKLIST

## Immediate (Fix the 3 critical data gaps)

### [ ] 1. Fix Technical Indicators Loader (Currently STUCK/STALE)
**Problem:** Loader status shows RUNNING but data is 4 days old (2026-07-14)
**Impact:** Phase 7 risk scoring fails, 24% of symbols dropped

```bash
# Check loader status
python -c "
import psycopg2
cur = psycopg2.connect('dbname=stocks user=stocks host=localhost').cursor()
cur.execute(\"SELECT table_name, status, execution_started, execution_completed FROM data_loader_status WHERE table_name='technical_data_daily'\")
print(cur.fetchone())
"

# If status=RUNNING for >1 hour, it's stuck. Kill and rerun:
python -c "
from algo.data.loaders.technical_indicators_loader import TechnicalIndicatorsLoader
loader = TechnicalIndicatorsLoader()
loader.run(force_refresh=True)
"
```
**Expected:** technical_data_daily updated to TODAY with all symbols

---

### [ ] 2. Refresh BUY Signals (Currently 1 day old)
**Problem:** buy_sell_daily signals from 2026-07-16, but today is 2026-07-17
**Impact:** Phase 7 falls back to degraded stock_scores-only ranking

```bash
# Run full orchestrator morning pipeline (includes buy_sell_daily generation)
python scripts/run_local_orchestrator.py --morning

# Verify new signals created
python -c "
import psycopg2
from datetime import date
cur = psycopg2.connect('dbname=stocks user=stocks host=localhost').cursor()
cur.execute(\"SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND date = %s\", (date.today(),))
print(f'BUY signals for today: {cur.fetchone()[0]}')
"
```
**Expected:** 100+ fresh BUY signals for today

---

### [ ] 3. Complete Stock Scores (Currently 99.6%, 17 missing)
**Problem:** 17 symbols missing composite_score
**Impact:** Those symbols can't be ranked in Phase 7

```bash
# Run stock scores loader
python -c "
from algo.data.loaders.stock_scores_loader import StockScoresLoader
loader = StockScoresLoader()
loader.run()
"

# Verify completion
python -c "
import psycopg2
cur = psycopg2.connect('dbname=stocks user=stocks host=localhost').cursor()
cur.execute(\"SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL\")
scored = cur.fetchone()[0]
cur.execute(\"SELECT COUNT(*) FROM stock_scores\")
total = cur.fetchone()[0]
print(f'Stock scores: {scored}/{total} ({100*scored/total:.1f}%)')
"
```
**Expected:** 100% coverage

---

## Data Refresh (Do once, gets everything fresh)

```bash
# One command to fix all data issues:
python scripts/run_local_orchestrator.py --run-all

# This does:
# - Phase 1: Validates data freshness
# - Phases 2-6: Risk checks
# - Phase 7: GENERATES FRESH SIGNALS ← KEY
# - Phase 9: Final reconciliation

# Monitor progress:
# - Watch for: "Phase 7 success: X signals qualified"
# - If Phase 7 succeeds, all upstream data is good
# - Phase 8 will halt (Alpaca creds missing) - expected
# - Phase 9 completes anyway
```

---

## Verify Everything Works

```bash
# 1. Check orchestrator completed successfully
python -c "
import psycopg2
cur = psycopg2.connect('dbname=stocks user=stocks host=localhost').cursor()
cur.execute(\"SELECT overall_status FROM algo_orchestrator_runs ORDER BY started_at DESC LIMIT 1\")
print(f'Latest run status: {cur.fetchone()[0]}')
"

# 2. Check Phase 7 generated signals
python -c "
import psycopg2
cur = psycopg2.connect('dbname=stocks user=stocks host=localhost').cursor()
cur.execute(\"SELECT COUNT(*) FROM algo_trade_signals WHERE signal_date = CURRENT_DATE AND signal_type = 'BUY'\")
count = cur.fetchone()[0]
print(f'Fresh BUY signals from Phase 7: {count}')
"

# 3. Verify data freshness
python check_system_health.py
```

---

## Run Full Local Flow (After data is fixed)

```bash
# Terminal 1:
python lambda/api/dev_server.py
# Wait for: "[INFO] Starting API dev server on http://localhost:3001"

# Terminal 2 (after 10 seconds):
python scripts/run_local_orchestrator.py --morning

# Terminal 3 (after Terminal 2 completes):
python dashboard.py --local
```

**Expected Output:**
- Dashboard loads without errors
- Shows fresh portfolio/positions/signals
- Phase 7 generated: X qualified signals
- All system logs: Clean

---

## Known Issues (Won't fully fix today, but understand the workarounds)

### Phase 8 Halts (Missing Alpaca Credentials)
- Expected behavior in local dev
- Phase 9 still runs (no actual trades needed for reconciliation)
- Workaround: Keep paper mode (already default)

### Dashboard Auth Required
- Local mode still checks authentication
- Workaround: dev_server proxy handles auth (just use it through dev_server)
- Real fix: Add localhost bypass in dashboard/credentials_provider.py

### Technical Loader Sometimes Gets Stuck
- Loader status shows RUNNING for >1 hour with no progress
- Workaround: Kill and rerun with force_refresh=True
- Real fix: Add timeout + auto-restart logic

### EOD Pipeline Only Runs Manually Locally
- No automatic 4:05 PM ET scheduler
- Signals get 1 day old overnight
- Workaround: Run --run-all each morning
- Real fix: Add local APScheduler config

---

## Success Criteria

After completing all steps above, verify:

- [ ] technical_data_daily: All 13 symbols have ATR/SMA (100% coverage)
- [ ] buy_sell_daily: 100+ BUY signals from TODAY
- [ ] stock_scores: 4786/4786 with composite_score (100%)
- [ ] orchestrator: Latest run status = "success"
- [ ] Phase 7: Generated 2+ qualified signals
- [ ] dashboard: Loads and shows fresh data
- [ ] system health: No CRITICAL issues

**STATUS: System Ready for Local Testing**
