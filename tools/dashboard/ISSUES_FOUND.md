# Dashboard.py Comprehensive Issue Analysis
**Generated:** 2026-06-10  
**Scope:** Full review of `tools/dashboard/dashboard.py` (4304 lines)  
**Objective:** Identify all data accuracy, integration, and display issues

---

## CRITICAL ISSUES (Production-Blocking)

### 1. **AWS/Database Credential Handling — NO VALIDATION**
**Severity:** CRITICAL | Location: `_get_db_credentials()` (line 201-232)

**Issue:**
- Falls back gracefully to environment variables but doesn't validate they're actually set
- `_get_db_credentials()` can return incomplete credentials (missing host, user, password, or dbname)
- `get_conn()` exits with error but only AFTER attempting connection timeout (10 seconds wasted)
- AWS Secrets Manager fetch doesn't retry on transient failures

**Impact:** 
- Slow startup if AWS credentials are invalid (10 sec timeout before exit)
- No indication which credential field is missing
- Operator doesn't know if AWS auth failed or env vars are incomplete

**Evidence:**
```python
# Line 235-238: only checks if ANY credential is missing, exits generically
miss = [k for k, v in creds.items() if not v]
if miss:
    sys.exit(f"Missing DB credentials: {', '.join(miss)}")
```

**Fix Needed:**
- Validate credentials immediately in `_get_db_credentials()`
- Add structured logging showing which credential source is being used (env vs AWS)
- Fail fast if AWS Secrets Manager is configured but fails
- Log specific error for each credential type

---

### 2. **Table Schema Validation INCOMPLETE — Silent Failures**
**Severity:** CRITICAL | Location: `validate_schema()` (line 256-310)

**Issue:**
- Only checks if columns exist, not if they have correct types
- Doesn't verify foreign key relationships
- Logs warnings for empty tables but continues anyway
- No validation of data types (e.g., if a price column contains text)
- Falls back to running dashboard even when critical tables are empty
- `col_count` query (line 282) may not count all required columns correctly

**Evidence:**
```python
# Line 290-296: warns about empty tables but doesn't halt
if result and result.get("col_count") != len(cols):
    msg = f"Schema validation {severity.upper()}: {table} missing columns"
    logger.error(msg)
    if severity == "critical":
        sys.exit(...)  # Only exits if MISSING, not if EMPTY
else:
    row_count = q1(c, f"SELECT COUNT(*) as cnt FROM {table}")
    if row_count and row_count.get("cnt") == 0:
        logger.warning(f"... exists but is EMPTY...")  # Just warns
```

**Fix Needed:**
- Validate column types match expectations
- Exit if critical tables are empty (no data at all)
- Check for required indexes
- Verify date column formats

---

### 3. **Market Data Staleness — No Hard Thresholds**
**Severity:** CRITICAL | Location: `fetch_market()` (lines 647-799)

**Issue:**
- SPY price data staleness logged (line 747-753) but doesn't halt dashboard
- `exp_age` can be > 1 day old but dashboard still uses it
- Breadth momentum threshold check (line 756) uses `mkt_health_age` but never actually uses `exp_age` for validity
- Distribution days staleness (line 764-771) has different thresholds (3d vs 10d on Monday) but inconsistently applied
- Dashboard shows stale data with only visual warning — operator may not notice

**Evidence:**
```python
# Line 747-753: warns but no halt
if spy_age is None and not spy_rows:
    logger.warning(f"VALIDATION: SPY price data is MISSING...")
    stale_alerts.append("SPY data missing")
elif spy_age is not None and spy_age > 1:
    logger.warning(f"VALIDATION: SPY price data is {spy_age} days old...")  # Just logs
    stale_alerts.append(f"SPY {spy_age}d stale")
# ... dashboard continues with stale SPY price
```

**Fix Needed:**
- Define maximum acceptable ages for each data source
- Return error dict if data exceeds staleness threshold (market stage, SPY, exposure)
- Don't display market tier if underlying data is too old
- Halt all trading decisions when critical market data is stale

---

### 4. **Positions Query Returns Wrong Data — DISTINCT ON Semantics**
**Severity:** CRITICAL | Location: `fetch_positions()` (lines 987-1046)

**Issue:**
- Uses `DISTINCT ON (symbol)` but ordering is incorrect for deduplication
- Line 998: `ORDER BY symbol, trade_date DESC, entry_time DESC`
  - DISTINCT ON uses only the FIRST expression in ORDER BY
  - Should be `ORDER BY symbol, trade_date DESC` but symbol order is wrong
- This means for a given symbol, it may return arbitrary trade_date if multiple have same date
- Latest trade per symbol is NOT guaranteed
- Positions can show obsolete trade data (closed position marked as open)

**Evidence:**
```python
# Line 990-998: DISTINCT ON ordering is WRONG
SELECT DISTINCT ON (symbol)
    symbol, trade_id, entry_quantity, entry_price, ...
FROM algo_trades
WHERE status IN ('open', 'filled', 'partially_filled', 'active')
ORDER BY symbol, trade_date DESC, entry_time DESC  # symbol order matters
```

**Fix Needed:**
- Change ORDER BY to: `symbol DESC, trade_date DESC, entry_time DESC`
- Add comment explaining why symbol comes first in ORDER BY
- Add test case verifying latest trade is returned per symbol
- Consider using window functions instead: `ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC, entry_time DESC)`

---

### 5. **Performance Analytics Missing Data — No Fallback**
**Severity:** HIGH | Location: `fetch_perf()` (lines 862-932)

**Issue:**
- Sharpe ratio requires >5 returns, but no validation that enough data exists
- If less than 10 snapshots, `sharpe` remains None but displays as "--"
- Max drawdown calculated from `daily_return_pct` but this only includes snapshots, not intraday drops
- Comment (line 900) acknowledges "intraday gaps invisible" but still shows value as truth
- Recent returns (line 917) drops to empty list if < 5 data points — dashboard shows nothing instead of partial data

**Evidence:**
```python
# Line 893-899: Sharpe only meaningful with >5 returns, but dashboard shows "--" silently
if len(rets) > 5:
    mn = statistics.mean(rets)
    sd = statistics.stdev(rets)
    if sd > 0: sharpe = round(mn / sd * (252 ** 0.5), 2)
# ... if < 5 returns, sharpe stays None
```

**Fix Needed:**
- Return confidence flag with Sharpe ratio ("high_confidence" if >20 snapshots, "low" if <10)
- Display max drawdown with warning if data is sparse
- Include at least 1 recent return even if < 5 available (don't drop to empty)
- Log warning if equity_vals < 3

---

### 6. **Circuit Breaker Logic — None Value Handling Bug**
**Severity:** CRITICAL | Location: `fetch_circuit()` (lines 1581-1691)

**Issue:**
- Line 1681: `b["fired"] = b["cur"] is not None and b["cur"] >= b["thr"]`
  - VIX can be None (line 1635) but comparison still tries to compare None >= threshold
  - If VIX is None, this will cause TypeError (comparing NoneType to float)
- Line 1672: VIX "available" flag added but not used consistently in rendering
- Daily loss (line 1612): converts negative return to float but may be None
- Weekly loss (line 1623): breaks silently if trading_rets < 5, uses max(0.0, -sum(...)) which will be 0.0 — false negative

**Evidence:**
```python
# Line 1635: VIX can be None
vix = float(vix_v) if vix_v is not None else None
# ... later ...
# Line 1681: Direct comparison to threshold
for b in bs: b["fired"] = b["cur"] is not None and b["cur"] >= b["thr"]
# This works IF cur is not None, but VIX could be None and bs will have None for vix
```

**Fix Needed:**
- Ensure all bs dict entries validate `cur is not None` before comparison
- Test with missing VIX data explicitly
- Return proper error if circuit breaker can't be calculated (insufficient data)

---

## HIGH SEVERITY ISSUES (Data Accuracy / Behavior)

### 7. **Unrealized P&L Calculation — Default 0 Hides Missing Data**
**Severity:** HIGH | Location: `panel_positions()` (line 2403)

**Issue:**
- Line 2403: `pnl = float(...) if ... else 0  # Default to 0 for display`
  - When `unrealized_pnl_pct` is missing (None), defaults to 0% gain
  - Operator sees "P&L: +0.0%" and thinks position is flat, when actually data is missing
  - Should show "--" instead
  - Comment acknowledges tracking missing but then uses default anyway

**Evidence:**
```python
# Line 2403: BAD — hides missing data
pnl = float(p.get("unrealized_pnl_pct")) if p.get("unrealized_pnl_pct") is not None else 0
# ... line 2413: used in display
pc = G if pnl >= 0 else R
# If pnl is missing, display shows green "0.00%" — false confidence
```

**Fix Needed:**
- Keep as None if missing, display as "--"
- Only default to 0 if we know position is actually flat (entry_price == current_price)

---

### 8. **Win Rate Calculation — Breakeven Trades Excluded**
**Severity:** HIGH | Location: `fetch_perf()` (line 876)

**Issue:**
- Line 870-872: Breakeven trades excluded from win rate calculation
  - 100 trades with 40 wins, 50 losses, 10 breakeven → win rate = 40/90 = 44%
  - But should this count as a win or neutral? Comment says "only wins vs (wins + losses)"
  - Inconsistent with expectancy calculation (line 913) which includes breakeven in PnL
  - If many breakeven trades, win rate appears worse than it is
- Streak calculation (line 877-885) breaks on first breakeven, doesn't count as either win or loss

**Evidence:**
```python
# Line 870-876: Excludes breakeven
wins = [t for t in trades if ... float(...) > 0]
losses = [t for t in trades if ... float(...) < 0]
breakeven = [t for t in trades if ... float(...) == 0]
counted_trades = len(wins) + len(losses)
wr = len(wins) / counted_trades * 100 if counted_trades > 0 else 0
```

**Fix Needed:**
- Document breakeven handling in dashboard legend
- Consider including breakeven in win rate as neutral (third category)
- Log warning if breakeven trades > 5% of total

---

### 9. **Swing Score Display — Colors Arbitrary**
**Severity:** MEDIUM | Location: Multiple locations

**Issue:**
- Swing score thresholds vary across file:
  - Line 2427: Green if >= 80, Yellow if >= 60
  - Line 2546: Green if >= 80, Yellow if >= 60
  - Signals panel uses 70 as min_swing_score threshold
  - But coloring uses 80/60 split
- Inconsistency: A score of 75 shows yellow (below 80) but passes min_score of 70
- No centralized constant for swing score thresholds

**Fix Needed:**
- Create constants: SWING_SCORE_GOOD=80, SWING_SCORE_OK=60
- Use consistently across all panels
- Align with actual min_swing_score from config

---

### 10. **Positions Table Missing Critical Data**
**Severity:** HIGH | Location: `fetch_positions()` (line 1038)

**Issue:**
- Joins with `company_profile` on `ticker` (line 1043) but joins `algo_trades.symbol` as the key
- If ticker != symbol (e.g., "BRK.A" vs "BRK" issue), sector lookup fails silently
- No validation that sector was actually retrieved
- Position shows "--" for sector when data exists but key mismatch occurs
- No logging of join failures

**Evidence:**
```python
# Line 1043: Joins on ticker=symbol, but symbols may not match exactly
LEFT JOIN company_profile cp ON cp.ticker = ot.symbol
# If symbol is "BRK.B" and ticker in company_profile is "BRK", join fails
```

**Fix Needed:**
- Add comment explaining ticker vs symbol
- Log warning if sector is missing (indicates join failure)
- Validate company_profile has entries for all open positions' symbols

---

### 11. **RDS Connection Exhaustion Risk**
**Severity:** HIGH | Location: `load_all()` (line 1812-1837)

**Issue:**
- ThreadPoolExecutor with 8 workers loads 28 fetchers
- Each fetcher opens a new connection
- If even 3 fetchers timeout, RDS could hit connection limit
- No connection pooling — each fetch opens/closes separate connection
- Timeout is 45 seconds (line 1821) but doesn't guarantee connection cleanup
- `finally` block (line 1809-1811) closes connection but swallows exceptions

**Evidence:**
```python
# Line 1815: 8 workers for 28 fetchers
max_workers = min(len(FETCHERS), os.cpu_count() or 4, 8)
# ... no connection pooling, each worker opens new connection
# ... line 1821: 45 sec timeout but connections may leak
```

**Fix Needed:**
- Implement connection pool (psycopg2.pool.SimpleConnectionPool)
- Set max_workers = 4 (not 8) to avoid RDS exhaustion
- Add explicit connection timeout (not just statement timeout)
- Log warning if queued fetchers > number of workers

---

### 12. **Date Parsing Inconsistency**
**Severity:** MEDIUM | Location: Multiple locations

**Issue:**
- `_parse_event_date()` (line 492-513) handles date parsing with fallbacks
- But `fmt_age()` (line 314-331) parses dates differently (no timezone conversion)
- `fetch_market()` (line 705-737) parses SPY dates with timezone handling
- Three different date parsing patterns across file
- Event date parsing (line 830) uses `_parse_event_date()` but economic calendar doesn't validate result
- If parsing fails silently, dashboard shows wrong dates

**Evidence:**
```python
# Different patterns:
# Pattern 1: line 319 (fmt_age)
if isinstance(ts, str):
    try:
        ts = datetime.fromisoformat(ts)

# Pattern 2: line 502 (parse_event_date)
return datetime.strptime(ed[:10], "%Y-%m-%d").date()

# Pattern 3: line 717 (fetch_market)
spy_date = spy_rows[0]["date"] if isinstance(..., datetime) else datetime.fromisoformat(...)
```

**Fix Needed:**
- Create single `_parse_datetime()` function with all fallback logic
- Use consistently throughout
- Add unit tests for each date format

---

## MEDIUM SEVERITY ISSUES (Edge Cases / Display)

### 13. **Signal Quality Score Missing Validation**
**Severity:** MEDIUM | Location: `fetch_signals()` (line 1122-1124)

**Issue:**
- Logs warning if signal is missing both `signal_quality_score` and `entry_quality_score`
- But doesn't prevent display or mark signal as invalid
- Signal table shows "--" for quality, operator may think it's valid
- No minimum threshold enforced (should require quality >= 50 at minimum?)

**Evidence:**
```python
# Line 1122-1124: Just warns, doesn't affect display
for sig_row in buy_sigs:
    if sig_row.get("signal_quality_score") is None and sig_row.get("entry_quality_score") is None:
        logger.warning(f"VALIDATION: Signal {sig_row.get('symbol')} missing both...")
# Signal still shows in table as valid
```

**Fix Needed:**
- Filter out signals with missing quality scores before display
- Set minimum quality threshold
- Log count of rejected signals due to missing data

---

### 14. **Sector Ranking — Missing Data Silently Skipped**
**Severity:** MEDIUM | Location: `panel_sector_compact()` (line 2683-2684)

**Issue:**
- Line 2683-2684: Filters out srank entries if srank itself is dict with "_error"
- But doesn't validate individual rank entries for required fields (current_rank, sector_name)
- If sector_name is missing, display shows blank
- No logging of data quality issues

**Fix Needed:**
- Validate each srank entry has current_rank and sector_name
- Skip incomplete entries with warning
- Log count of skipped rankings

---

### 15. **Economic Calendar — Duplicate Event Deduplication**
**Severity:** LOW | Location: `panel_economic_pulse()` (line 2817-2824)

**Issue:**
- Line 2822: Creates dedup key as `(str(ed) + full_nm[:24]).lower()`
- But if event_date is None, str(None) = "None" — all None dates collide
- Limits to 6 events (line 2818) but deduplication can silently remove valid events
- No logging of deduplicated events

**Evidence:**
```python
# Line 2822: If ed is None, all None events collide
key = (str(ed) + full_nm[:24]).lower()
if key in seen_keys: continue  # Skips second event with same date/name
```

**Fix Needed:**
- Handle None event_date explicitly
- Log count of deduplicated events
- Show all events if < 6, don't limit until after dedup

---

### 16. **Exposure Factors Schema Incomplete**
**Severity:** MEDIUM | Location: `fetch_exposure_factors()` (line 818-828)

**Issue:**
- Validates expected_keys exist (line 819) but many factors optional
- If factor dict is incomplete, display shows blank values
- No distinction between "data not available" vs "calculation failed"
- factor_detail() (line 2870-2910) returns "" for missing factors silently

**Fix Needed:**
- Track which factors have data vs missing
- Display "(no data)" for missing factors instead of blank
- Log count of missing factors

---

### 17. **Load All Timeout — Doesn't Log Which Fetcher**
**Severity:** MEDIUM | Location: `load_all()` (line 1829-1836)

**Issue:**
- Line 1834: Logs "Fetcher {k} timed out" but k is keyed from future_to_key dict
- Order of futures completion != order of FETCHERS dict
- No visibility into which fetchers are still running vs timed out
- If several fetchers time out, dashboard shows partial data without warning

**Fix Needed:**
- Track fetcher start time, log elapsed time when timeout
- Log which fetchers are still running when timeout fires
- Mark timed-out fetchers in dashboard display

---

### 18. **Position Days Since Entry — Edge Cases**
**Severity:** LOW | Location: `fetch_positions()` (line 1020-1022)

**Issue:**
- Calculates `days_since_entry` as `(CURRENT_DATE - entry_time::date)::INT`
- But trades may be created today (days = 0) vs intraday (days = 0 but opened minutes ago)
- Display shows "0" — operator doesn't know if position is minutes or hours old
- No fractional days (would need to calculate hours for same-day entries)

**Fix Needed:**
- Return hours/minutes for same-day entries (e.g., "2h 15m" instead of "0")
- Or add entry_time to positions so dashboard can calculate

---

### 19. **Alert/Notification Colors — Inconsistent**
**Severity:** LOW | Location: Multiple locations

**Issue:**
- Circuit breaker alert colors vary:
  - Line 2106: Red if fired, otherwise yellow/green based on ratio
  - Line 1667-1674: Red if >= threshold
- Market health colors use different thresholds
- No central color scheme document
- Makes dashboard hard to read consistently

**Fix Needed:**
- Create ALERT_COLORS dict with consistent rules
- Use throughout

---

### 20. **Positions Negative Entry Price — No Validation**
**Severity:** LOW | Location: `fetch_positions()` (line 1029)

**Issue:**
- Line 1029-1031: Calculates unrealized_pnl_pct but doesn't validate entry_price > 0
- If entry_price = 0, division by zero returns 0 (but silently wrong)
- No validation that current_price is reasonable (>0)

**Fix Needed:**
- Validate entry_price > 0 before calculation
- Return None if invalid, display as "--"

---

## LOGGING & OBSERVABILITY ISSUES

### 21. **Inconsistent Log Levels**
**Severity:** MEDIUM | Location: Throughout

**Issue:**
- Some validation issues logged as ERROR (line 618, 755)
- Others as WARNING (line 295, 750-753)
- No clear rule: when does validation issue become ERROR vs WARNING?
- Makes it hard to set log level for alerts

**Fix Needed:**
- Define: ERROR = halts dashboard, WARNING = data incomplete but show anyway, DEBUG = informational
- Apply consistently

---

### 22. **Missing Data Quality Metrics**
**Severity:** MEDIUM | Location: Throughout

**Issue:**
- `_log_data_quality()` called but doesn't track cumulative stats
- If fetcher returns 0 rows, logs as EMPTY (warning) not ERROR
- No dashboard panel showing data loader health across all tables
- Operator can't see "which fetcher is broken"

**Fix Needed:**
- Add `fetch_health()` function that returns loader status per table (fresh/stale/error/empty)
- Display in dashboard
- Log data quality summary on startup

---

## INTEGRATION ISSUES (AWS/RDS)

### 23. **No Graceful Degradation on Partial Failures**
**Severity:** HIGH | Location: Throughout

**Issue:**
- If 1 fetcher fails (e.g., fetch_signals), dashboard still renders with partial data
- No indication which panels are stale/missing
- Operator may make decisions based on incomplete data
- No "data freshness" summary

**Fix Needed:**
- Mark each panel with data age / freshness status
- Show warning banner if any critical fetcher failed
- Define "critical" fetchers (run, positions, market)

---

### 24. **No Connection Retry with Backoff**
**Severity:** MEDIUM | Location: `load_all()` (line 1799-1804)

**Issue:**
- Retries up to 2 times but with fixed delay (0.5 * attempt)
- No exponential backoff
- If RDS is temporarily slow, all 28 fetchers retry simultaneously (thundering herd)
- No jitter to spread retries

**Fix Needed:**
- Add exponential backoff: `sleep(2 ** attempt + random(0, 1))`
- Limit retries to 1 for non-connection errors (statement errors won't improve with retry)

---

## TEST COVERAGE GAPS

### 25. **No Test Data Generator**
**Severity:** MEDIUM | Location: `generate_test_data()` (line 1770-1784)

**Issue:**
- Function is placeholder (returns "not_implemented")
- No way to test dashboard locally without live AWS RDS
- Makes development slow (need real data to iterate)

**Fix Needed:**
- Implement test data generator for all critical tables
- Create seed script that populates test database

---

## SUMMARY BY CATEGORY

| Category | Count | Critical | High | Medium |
|----------|-------|----------|------|--------|
| Data Accuracy | 12 | 6 | 4 | 2 |
| AWS/Database | 5 | 2 | 2 | 1 |
| Display/UX | 4 | 1 | 1 | 2 |
| Logging | 3 | 0 | 1 | 2 |
| Testing | 1 | 0 | 0 | 1 |
| **TOTAL** | **25** | **9** | **8** | **8** |

---

## IMMEDIATE ACTION ITEMS

**Before Production Deployment:**
1. Fix DISTINCT ON ordering in fetch_positions() (CRITICAL)
2. Add market data staleness hard thresholds (CRITICAL)
3. Fix circuit breaker None comparison bug (CRITICAL)
4. Implement credentials validation (CRITICAL)
5. Add table schema/data type validation (CRITICAL)
6. Implement graceful degradation with data freshness display (HIGH)
7. Fix unrealized P&L default value (HIGH)
8. Add connection pooling & retry with backoff (HIGH)

**Next Phase:**
9. Create comprehensive data quality dashboard panel
10. Implement test data generator
11. Add unit tests for date parsing, win rate calculation, etc.

---

## RELATED MEMORY

See `[[phase7_reconciliation_patterns]]` for context on how exits affect win rate calculations.

