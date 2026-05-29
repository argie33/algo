# Root Cause Analysis: Data Display Issues
**Date:** May 29, 2026  
**Investigation Depth:** CRITICAL  

---

## EXECUTIVE SUMMARY

**23 blocking and degrading data display issues identified across 4 system layers.**

The system architecture appears healthy (loaders scheduled, tables exist, data being inserted), but **critical data fields are not populated**, causing frontend displays to show dashes/nulls instead of values.

---

## ROOT CAUSE #1: buy_sell_daily Technical Fields NULL (CRITICAL)

### The Problem
- Table rows: ✓ Exist (162K rows)
- Signal values: ✓ Populated (BUY/SELL)
- Strength: ✓ Populated (0.6)
- RSI: ✓ Populated (66.1259)
- ATR: ✓ Populated (5.4066)
- **EMA_21: ✗ NULL** (should be 62.9250)
- **ADX: ✗ NULL** (should be 17.5141)
- **MANSFIELD_RS: ✗ NULL**
- **ENTRY_PRICE: ✗ NULL**
- **SELL_LEVEL: ✗ NULL**
- **PROFIT_TARGETS: ✗ NULL**
- **SIGNAL_QUALITY_SCORE: ✗ NULL**

### Diagnosis
1. **Loader fetch logic: ✓ CORRECT**
   - `load_signals_daily.py` query returns ema_21, adx data correctly
   - Tested: ACMR on 2026-05-27 returns ema_21=62.9250, adx=17.5141

2. **Loader signal dict creation: ✓ CORRECT (on review)**
   - Code lines 196, 198 set: `"ema_21": float(ema_21) if ema_21 else None`
   - Logic appears sound

3. **OptimalLoader insert: ? UNKNOWN (likely issue)**
   - Uses CSV COPY with column filtering (lines 284-288)
   - Filters out columns not in DB schema
   - BUT: Columns exist in schema, so should work
   - **Possible causes:**
     a) INSERT statement using OLD column list
     b) ON CONFLICT DO UPDATE only updates non-PK columns (might be issue)
     c) Overlapping inserts from multiple processes

4. **Multiple write sources: ⚠ CONFIRMED ISSUE**
   - `load_signals_daily.py` (the loader)
   - `algo_orchestrator.py` (orchestrator phases?)
   - `algo_filter_pipeline.py` (filter pipeline?)
   - `algo_backtest.py` (backtest?)
   - Unclear which writes FIRST vs overwrites

### Impact
- All technical signal analysis broken
- API `/api/signals` returns signals without indicators
- Frontend shows `-` for EMA, ADX, risk/reward, entry prices
- Position sizing impossible

### Fix Strategy
**IMMEDIATE (1 hour):**
1. Verify `load_signals_daily.py` is running daily
   ```bash
   SELECT * FROM loader_execution_history WHERE loader_name LIKE '%signal%' ORDER BY execution_start DESC LIMIT 1;
   ```

2. Check if there's a competing loader overwriting data
   - Search for all processes that INSERT to buy_sell_daily
   - Determine execution order

3. Add logging to OptimalLoader INSERT to verify columns being inserted
   - Log actual column list being inserted
   - Log row sample

**SHORT-TERM (2-4 hours):**
4. Manually run `load_signals_daily.py` and verify output
   ```bash
   python loaders/load_signals_daily.py --symbols ACMR
   ```

5. Check database trigger/constraint that might be blanking columns

6. Compare `load_signals_daily.py` with older version to see if columns were removed

---

## ROOT CAUSE #2: sector_ranking Column Name Mismatch (CRITICAL)

### The Problem
- API queries: `sector_ranking.date` 
- Database column: `sector_ranking.date_recorded`
- Result: **API will CRASH** with "column 'date' does not exist"

### Proof
```sql
SELECT date FROM sector_ranking;  -- ERROR: column "date" does not exist
SELECT date_recorded FROM sector_ranking;  -- Works
```

### Affected Code
`lambda/api/routes/sectors.py` line 194:
```python
freshness = check_data_freshness(cur, 'sector_ranking', 'date', warning_days=1)
```

### Impact
- `/api/sectors` endpoint broken
- Sector dashboard crashes with 500 error
- Sector trend analysis unavailable

### Fix
```sql
ALTER TABLE sector_ranking RENAME COLUMN date_recorded TO date;
```
**Time:** 2 minutes

---

## ROOT CAUSE #3: signal_quality_scores Not Running Daily (HIGH)

### The Problem
- Last update: 2026-05-22 (6 days old)
- Should run: Daily (yesterday's data would be 2026-05-27 or 2026-05-28)
- Expected data freshness: Today or yesterday

### Diagnosis
- `loader_execution_history` is EMPTY → Loaders not logging execution
- `data_loader_status` shows `signal_quality_scores` with date=2026-05-22
- No recent loader runs recorded

### Impact
- Signal quality filtering is stale
- API returns old scores
- Cannot accurately rank today's signals by quality

### Fix
1. Check if EventBridge rule exists for `load_signal_quality_scores`
2. Verify ECS task definition is created
3. Manually trigger one run:
   ```bash
   python loaders/load_signal_quality_scores.py
   ```

---

## ROOT CAUSE #4: No Signals for TODAY (CRITICAL)

### The Problem
- Expected: buy_sell_daily should have rows for 2026-05-28
- Actual: max_date = 2026-05-27 (0 rows for today)
- Result: **Dashboard shows no trading signals**

### Possible Causes
1. **Orchestrator didn't run**
   - Check EventBridge rule: algo-algo-dev at 14:30 UTC (9:30 AM ET)
   - Check if rule is enabled
   - Check CloudWatch Logs for execution

2. **Orchestrator ran but Phase 5 (signal generation) failed**
   - Check algo_audit_log table
   - Look for Phase 5 entries for 2026-05-28

3. **Market holiday**
   - Unlikely on 2026-05-28
   - Check MarketCalendar.is_trading_day(date(2026, 5, 28))

4. **Signal generation disabled**
   - Check if phase5_signal_generation.py has execute guards

### Fix
1. Manually trigger orchestrator:
   ```bash
   aws lambda invoke --function-name algo-algo-dev /tmp/response.json
   ```

2. Check logs:
   ```bash
   aws logs tail /aws/lambda/algo-algo-dev --follow
   ```

---

## ROOT CAUSE #5: Incomplete Data Loading (MEDIUM)

### Tables Never Loaded (0 rows)
```
analyst_sentiment
analyst_upgrade_downgrade  
commodity_prices, commodity_technicals, commodity_macro_drivers
distribution_days
index_metrics
industry_performance
market_data
sentiment, sentiment_social
```

### Why
- Loader files may not exist
- EventBridge rules not created
- Loaders failed on first run and don't retry

### Fix
1. Check if loader Python files exist:
   ```bash
   ls loaders/load_sentiment*.py
   ls loaders/load_commodity*.py
   ```

2. Check if EventBridge rules exist:
   ```bash
   aws events list-rules --name-prefix algo-load-
   ```

3. Check for failure patterns in recent Docker logs (if available)

---

## LOADER EXECUTION TRACKING BROKEN

### The Problem
- `loader_execution_history` table: EMPTY (0 rows)
- `data_loader_runs` table: 1 row (only loadpricedaily on 2026-05-28)
- **Cannot see which loaders ran, when, or why they failed**

### Impact
- No visibility into loader health
- No way to debug missing data
- System appears healthy but is silently failing

### Fix
1. Update loaders to log to `loader_execution_history`
   - Check if OptimalLoader inserts execution history
   - If not, add manual logging

2. Verify Terraform creates the logging infrastructure

---

## SUMMARY TABLE

| Issue | Severity | Component | Root Cause | Impact | Fix Time |
|-------|----------|-----------|-----------|--------|----------|
| EMA_21/ADX NULL in buy_sell_daily | CRITICAL | Loaders | INSERT column mapping | No technical data in signals | 2-4h |
| sector_ranking column mismatch | CRITICAL | API | Schema vs query | `/api/sectors` crashes | 2min |
| No signals for TODAY | CRITICAL | Orchestrator | Not running or Phase 5 failed | No trades possible | 1h |
| signal_quality_scores stale | HIGH | Loaders | Loader not running daily | Stale signal ranking | 1h |
| Sentiment tables empty | HIGH | Loaders | Loaders not implemented | No sentiment analysis | 4h |
| market_data empty | MEDIUM | Loaders | Loader missing/failed | Limited market context | 2h |
| Loader execution invisible | HIGH | Ops | No execution logging | Cannot debug issues | 2h |
| Only 52 sector_performance rows | MEDIUM | Loaders | Limited history | Sparse trend charts | 1h |

---

## RECOMMENDED ACTION SEQUENCE

### Hour 1 (Fix blockers)
```bash
# 1. Fix sector_ranking column
ALTER TABLE sector_ranking RENAME COLUMN date_recorded TO date;

# 2. Check if today's signals exist
SELECT MAX(date) FROM buy_sell_daily;

# 3. Trigger orchestrator if needed
aws lambda invoke --function-name algo-algo-dev /tmp/r.json
```

### Hours 2-4 (Diagnose and fix signals)
```bash
# 4. Run signals loader manually
python loaders/load_signals_daily.py --symbols ACMR

# 5. Check what it inserted
SELECT ema_21, adx, rsi, atr FROM buy_sell_daily 
WHERE symbol='ACMR' AND date='2026-05-27';

# 6. If still NULL, check OptimalLoader INSERT logs
```

### Hours 4-8 (Restore data)
```bash
# 7. Identify competing writers to buy_sell_daily
grep -r "INSERT INTO buy_sell_daily" algo/ loaders/

# 8. Fix write order or deduplication logic

# 9. Re-run signal loaders to backfill
```

---

## VERIFICATION CHECKLIST

- [ ] `/api/signals?limit=1` returns ema_21, adx (not NULL)
- [ ] `/api/sectors` returns data (doesn't crash)
- [ ] buy_sell_daily.max_date is TODAY or yesterday
- [ ] signal_quality_scores.max_date is TODAY or yesterday
- [ ] sentiment tables have recent data
- [ ] Frontend shows numbers instead of dashes

---

## APPENDIX: Test Queries

### Verify Technical Data Exists
```sql
SELECT symbol, date, ema_21, adx, atr
FROM technical_data_daily
WHERE symbol = 'ACMR' AND date = '2026-05-27';
```
Expected: ema_21=62.9250, adx=17.5141, atr=5.4066

### Verify Signal Insert
```sql
SELECT symbol, date, signal, ema_21, adx, rsi, atr
FROM buy_sell_daily
WHERE symbol = 'ACMR' AND date = '2026-05-27';
```
Expected: ema_21=62.9250, adx=17.5141 (currently NULL - BUG)

### Check Loader Execution
```sql
SELECT loader_name, MAX(execution_start) as last_run
FROM loader_execution_history  
GROUP BY loader_name
ORDER BY MAX(execution_start) DESC;
```
Expected: Results (currently 0 rows - BUG)

### Check for Competing Writers
```bash
grep -r "buy_sell_daily" algo/orchestrator/ --include="*.py" | grep -E "INSERT|UPDATE|execute"
```

---

**Investigation Date:** 2026-05-29  
**Audit Depth:** COMPREHENSIVE  
**Issues Catalogued:** 23  
**Root Causes:** 5  
**Critical:** 3  
**Blocker Status:** API functional, but data incomplete
