# Loader Maintenance Playbook - Bulletproof Operations

**Goal:** Keep loaders bulletproof - fresh real data, explicit errors, no silent fallbacks.

---

## DAILY OPERATIONAL HEALTH CHECK

Run this every morning to ensure data loaded correctly overnight:

```bash
# Check data freshness
python check_system_health.py

# Expected output:
#   [OK]   price_daily:           8M+ rows, latest: 0-1d ago
#   [OK]   technical_data_daily:  200k+ rows, latest: 0-1d ago
#   [OK]   stock_scores:          4,700+ rows, latest: 0-1d ago
#   [OK]   buy_sell_daily:        100+ rows, latest: 0-1d ago
#   [OK]   All metrics (growth/quality/value): latest 0d ago

# If any critical loader is STALE or NULL:
#   1. Check orchestrator runs: SELECT * FROM algo_orchestrator_runs ORDER BY started_at DESC LIMIT 5
#   2. Look for error_message or halt_reason
#   3. Check specific loader status: SELECT * FROM data_loader_status WHERE table_name = 'price_daily'
#   4. Run recovery: python scripts/run_local_orchestrator.py --morning
```

---

## STUCK LOADER RECOVERY

### When a loader gets stuck (RUNNING state > 30 minutes)

```bash
# Step 1: Identify which loader is stuck
python3 -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('SELECT table_name, status, execution_started FROM data_loader_status WHERE status IN (\"RUNNING\", \"FAILED\")')
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]} since {row[2]}')
cur.close()
"

# Step 2: Check if loader is actually running or just stuck
ps aux | grep python | grep load_  # Check for running processes

# Step 3: Reset if truly stuck (>30 min in RUNNING state)
python3 << 'PYEOF'
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Find loaders stuck > 30 minutes
cur.execute("""
SELECT table_name, execution_started 
FROM data_loader_status 
WHERE status = 'RUNNING' 
  AND execution_started < NOW() - INTERVAL '30 minutes'
""")

stuck_loaders = cur.fetchall()
for table, started in stuck_loaders:
    print(f"[STUCK] {table} since {started}")
    # Reset to READY to allow retry
    cur.execute("""
    UPDATE data_loader_status 
    SET status = 'READY', execution_started = NULL, execution_completed = NULL
    WHERE table_name = %s
    """, (table,))
    print(f"[RESET] {table} to READY")

conn.commit()
conn.close()
PYEOF

# Step 4: Trigger manual run if critical
python scripts/run_local_orchestrator.py --morning  # For critical path
```

---

## STALE DATA RECOVERY

### When a critical loader hasn't updated in 24+ hours

```bash
# Check staleness
python scripts/monitor_data_staleness.py

# For each stale critical loader (price_daily, stock_scores, etc):

# Option A: Run full orchestrator (all phases)
python scripts/run_local_orchestrator.py --run-all

# Option B: Run specific loader manually
# Example: Manually run stock_scores if it's stale
python loaders/load_stock_scores.py

# Option C: Check orchestrator logs for why it failed
SELECT overall_status, halt_reason, execution_time_seconds 
FROM algo_orchestrator_runs 
WHERE started_at > NOW() - INTERVAL '24 hours' 
ORDER BY started_at DESC;
```

---

## BROKEN API RECOVERY

### When an external API fails (like aaii_sentiment)

**Example: aaii_sentiment API permanently down**

1. **Identify impact:**
   ```bash
   # Check if loader is in critical path
   grep -r "aaii_sentiment" loaders/orchestrator.py  # Should NOT be there
   
   # Impact: bullish/bearish/neutral percentages in market_sentiment will be NULL
   # This is OK - these are OPTIONAL enrichment fields
   ```

2. **Verify graceful degradation:**
   ```sql
   -- Should show NULL for bullish/bearish (not invented values)
   SELECT date, fear_greed_index, bullish_pct, bearish_pct, data_unavailable, reason
   FROM market_sentiment
   ORDER BY date DESC LIMIT 5;
   ```

3. **Document the outage:**
   - Update CLAUDE.md with known issues
   - Document fallback strategy
   - Plan replacement (if critical)

4. **Replace or deprecate:**
   - For optional APIs: Mark as deprecated, update docs
   - For critical APIs: Implement fallback or alternative source

---

## ERROR HANDLING VERIFICATION

Every week, verify that errors are EXPLICIT (not silent):

```python
# Check for silent fallback patterns (should be ZERO):
# 1. Empty list returns without markers
# 2. Empty dict returns without markers
# 3. Hardcoded 0 for financial data
# 4. Silent None returns

# Run pre-commit hook to enforce:
python .pre-commit-scripts/check-silent-fallbacks.py loaders/

# Expected output:
# [OK] No silent fallback patterns detected

# If violations found, fix immediately:
# - Don't use: return []  or  return {}
# - DO use:    return {"data_unavailable": True, "reason": "..."}
# - Don't use: return 0 for financial metrics
# - DO use:    return None (then handle upstream)
```

---

## DATA QUALITY VERIFICATION

### Weekly validation (every Friday)

```bash
# 1. Check for NaN/NULL pollution
python3 << 'PYEOF'
import psycopg2
import math

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Check critical tables for NaN
tables = ['stock_scores', 'buy_sell_daily', 'growth_metrics', 'value_metrics', 'quality_metrics']
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE score IS NULL OR score = 'NaN'")
    null_count = cur.fetchone()[0]
    if null_count > 0:
        print(f"[WARN] {table}: {null_count} NULL/NaN values - investigate!")
    else:
        print(f"[OK] {table}: No NaN/NULL pollution")

conn.close()
PYEOF

# 2. Check for stale data patterns
python scripts/monitor_data_staleness.py

# 3. Verify no duplicate rows (watermarks working)
python3 << 'PYEOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Check for duplicate symbols/dates (watermark failures)
cur.execute("""
SELECT symbol, date, COUNT(*) as cnt
FROM price_daily
GROUP BY symbol, date
HAVING COUNT(*) > 1
LIMIT 10;
""")

dupes = cur.fetchall()
if dupes:
    print(f"[ERROR] {len(dupes)} duplicate price rows detected! Watermark failed.")
else:
    print("[OK] No duplicate price rows (watermarks working)")

conn.close()
PYEOF
```

---

## ORCHESTRATOR PHASE VERIFICATION

### When orchestrator halts, verify phase sequence:

```bash
# Check which phase failed
SELECT overall_status, halt_reason, execution_time_seconds
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '24 hours'
ORDER BY started_at DESC LIMIT 1;

# Expected for DATA LOADING phases (1-3):
# Phase 1: all_tables_fresh    - prices, technicals, market health loaded
# Phase 2: circuit_breakers     - risk checks pass
# Phase 3: position_monitor     - positions sync'd from broker
# (Phases 4-9 may fail if broker credentials missing - that's OK)

# If Phase 1 fails:
# - Check price_daily staleness (should be 0-1 days old)
# - Check market_health_daily (VIX data loaded?)
# - Run: python scripts/run_local_orchestrator.py --morning

# If Phase 2 fails:
# - Check circuit breaker thresholds in algo/risk/circuit_breakers.py
# - Verify portfolio state in database
# - Run: python check_system_health.py
```

---

## LOADER SCHEDULE REFERENCE

### Daily Critical Path (Must complete before trading)
- **Morning (2:00 AM ET):** price_daily, technical_data_daily, market_health_daily
- **EOD (4:05 PM ET):** growth_metrics, quality_metrics, value_metrics, positioning_metrics, stock_scores, buy_sell_daily

### Optional/Historical (On-demand only)
- **Financial statements:** annual_balance_sheet, quarterly_income_statement (manual trigger)
- **SEC filings:** insider_holdings_sec, analyst_sentiment_analysis (manual trigger)
- **Pattern analysis:** vcp_patterns, sector_performance (monthly)
- **Sentiment:** aaii_sentiment (broken), fear_greed_index (manual)

### Rule of Thumb
**Critical loaders:** Run every morning/EOD, must complete before trading  
**Historical loaders:** Run monthly or on-demand, OK to be weeks old  
**Sentiment/enrichment:** Optional, NOT blocking trading signals  

---

## MONITORING SETUP

### CloudWatch Metrics (If AWS credentials available)
```bash
# Metrics sent automatically during orchestrator runs
# Check CloudWatch → Logs → /algo/loaders
# Should see:
#   - loader_symbols_succeeded (per loader)
#   - loader_symbols_failed (per loader)
#   - loader_execution_time_seconds
#   - orchestrator_phase_status (0=success, 1=failed)
```

### Local Health Monitoring (Always available)
```bash
# Run every hour
python check_system_health.py

# OR run with watch interval
python scripts/monitor_data_staleness.py --watch 3600
```

---

## INCIDENT PLAYBOOK - Common Scenarios

### Scenario 1: "Data not available" on dashboard

```
1. Check health: python check_system_health.py
2. If dev_server not running: python lambda/api/dev_server.py
3. If prices stale (>1d): python scripts/run_local_orchestrator.py --morning
4. If specific metric missing: Check data_loader_status for that table
5. If in AWS mode: Verify Alpaca/AWS credentials valid
```

### Scenario 2: Orchestrator halts at Phase 4+

```
This is EXPECTED if Alpaca credentials missing.
Phase 1-3 (data loading) working fine.
To test full orchestrator: Set ALPACA_PAPER_TRADING=true
```

### Scenario 3: One loader fails, others still work

```
1. Find failed loader: SELECT * FROM data_loader_status WHERE status='FAILED'
2. Check error_message: Was it API error? Timeout? Data issue?
3. If API error: Check if loader has fallback (positioning_metrics has tiered fallback)
4. If timeout: Reset to READY and retry (will work next scheduled run)
5. If data issue: Check source data (SEC EDGAR down? yfinance rate limited?)
```

### Scenario 4: "Silent fallback" pattern detected by pre-commit

```
If commit fails with "silent fallback pattern detected":

1. Find the problematic code: git diff HEAD
2. Replace with explicit error handling:
   BEFORE: return [] or return {}
   AFTER:  return {"data_unavailable": True, "reason": "..."}
   
   BEFORE: return 0 (for financial metric)
   AFTER:  return None (then handle upstream)
   
3. Add reason/logging so operator sees what happened
4. Verify downstream code handles None gracefully
5. Commit with explicit error message
```

---

## BULLETPROOF PRINCIPLES

1. **No Silent Fallbacks** - All errors explicit (fail-fast or data_unavailable marker)
2. **No Invented Data** - Never return 0, false, or fake values for financial data
3. **Explicit Markers** - All optional/missing data marked with data_unavailable flag
4. **Watermarks** - Prevent duplicate inserts, enable incremental loading
5. **Timeouts** - Long-running queries capped at 30 sec max
6. **Trading-Day Aware** - Freshness checks use is_trading_day(), not calendar days
7. **Real Data Only** - All data from authoritative sources (not mocks or fallbacks)
8. **Operator Visibility** - All decisions logged and traceable in status tables

---

## QUICK REFERENCE

| Issue | Command | Expected |
|-------|---------|----------|
| Check health | `python check_system_health.py` | [OK] for all critical loaders |
| Monitor staleness | `python scripts/monitor_data_staleness.py` | Exit code 0 (fresh data) |
| Run morning pipeline | `python scripts/run_local_orchestrator.py --morning` | Phases 1-3 OK |
| Run EOD pipeline | `python scripts/run_local_orchestrator.py --afternoon` | Phases 1-9 OK (8-9 may fail on Alpaca creds) |
| Reset stuck loader | SQL: `UPDATE data_loader_status SET status='READY' WHERE ...` | Loader ready to retry |
| Check pre-commit | `python .pre-commit-scripts/check-silent-fallbacks.py loaders/` | [OK] No violations |
| Verify watermarks | SQL: `SELECT COUNT(*) FROM table GROUP BY pk HAVING COUNT(*) > 1` | Zero duplicates |

---

## NEXT STEPS

1. **Run health check daily** - Catch issues before they grow
2. **Review orchestrator runs weekly** - Look for patterns in failures
3. **Audit loader schedule quarterly** - Update if requirements change
4. **Update this playbook** - Add scenarios you encounter
5. **Test recovery procedures** - Don't learn in production

The system is bulletproof when:
- ✅ All critical loaders fresh (today or yesterday)
- ✅ No stuck processes (RUNNING > 30 min)
- ✅ All errors explicit (no silent returns)
- ✅ Health check passes
- ✅ Orchestrator Phases 1-3 passing

Keep it that way!
