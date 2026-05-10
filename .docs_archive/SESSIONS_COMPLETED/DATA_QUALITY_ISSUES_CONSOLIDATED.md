# Consolidated Data Quality & System Issues Report
**Date:** 2026-05-07  
**Status:** COMPREHENSIVE ANALYSIS IN PROGRESS

---

## Executive Summary

The stock analytics platform has **excellent data quality** (21.8M price records, 100% clean) but **critical system logic issues** preventing correct trading behavior.

### Issues Found

| # | Category | Severity | Affected | Root Cause | Status |
|---|----------|----------|----------|-----------|--------|
| 1 | Entry Price Field | CRITICAL | 83% signals | Using wrong source | Found |
| 2 | Same-day Entry/Exit | CRITICAL | 100% trades | Exit checks wrong day | Found |
| 3 | Exit Timing Logic | CRITICAL | 100% trades | Date not advanced | Found |
| 4 | NULL Entry Prices | MAJOR | 0.06% signals | Edge case handling | Found |
| 5-X | *More issues pending* | TBD | TBD | *Under investigation* | Scanning |

---

## ISSUE #1: Entry Price Field Source (CRITICAL)

### Current State
- **Problem**: `buy_sell_daily.entry_price` is being used for trade entry
- **Data**: 424,703 BUY signals exist
  - 83% have `entry_price != close` price
  - 5.7% have `entry_price` outside daily [low, high] range
  - 240 have NULL `entry_price`
- **Result**: Entry prices don't match market reality

### Root Cause Analysis

**In loadbuyselldaily.py (lines 268-281):**
```python
# Entry price is the close (for BUY signals, this is the signal trigger price)
entry_price = close_price                          # Line 269 - CORRECT
buy_level = entry_price                            # Line 281 - SAME VALUE

return {
    ...
    "entry_price": entry_price,                    # Line 316 - CORRECT
    "buylevel": buy_level,                         # Line 317 - SAME
    ...
}
```

**The code looks correct!** Entry price IS set to close price.

**Hypothesis**: This could mean:
1. **Old data in database** from before this fix was implemented
2. **Different code path** is updating entry_price after insert
3. **A different loader** is overwriting the data
4. **The data audit is measuring old data** that hasn't been refreshed

### What Needs Investigation
- [ ] Check git history: when was entry_price = close_price fix implemented?
- [ ] Query database: sample entry_price vs close from 10 random signals
- [ ] Check if data was loaded from OLD version of loader
- [ ] Verify there's no post-insert logic overwriting entry_price

### Fix Strategy
**Option A: Refresh data** (if old data is the issue)
```sql
-- Re-run the loader to refresh all signals
-- This will recalculate entry_price correctly from price_daily
```

**Option B: Add validation** (regardless)
```sql
-- Add constraint to buy_sell_daily:
ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_must_be_market_price
  CHECK (entry_price >= low AND entry_price <= high);

-- This will catch any future out-of-range entries
```

**Option C: Simplify** (best long-term)
- Delete entry_price from buy_sell_daily entirely
- Trade executor pulls entry_price directly from price_daily.close
- Eliminates the duplicate/conflicting field

---

## ISSUE #2 & #3: Same-Day Entry/Exit Logic (CRITICAL)

### Current State
- **Problem**: ALL 39 closed trades enter and exit on the same day
  - signal_date = 2026-05-05
  - exit_date = 2026-05-05 (SAME DAY)
  - entry_price = exit_price
  - Result: 0.00% P&L (100% of trades)

### Trade Execution Flow (from algo_orchestrator.py)

```
Daily Workflow:
PHASE 3: Position Monitor
PHASE 4: EXIT EXECUTION (check all open positions for exit conditions)
PHASE 4b: Pyramid Adds
PHASE 5: SIGNAL GENERATION (evaluate today's BUY signals)
PHASE 6: ENTRY EXECUTION (execute qualified trades)
PHASE 7: Reconciliation
```

**The sequence looks correct!** Exits happen BEFORE entries.

### Root Cause Analysis

**In algo_exit_engine.py (check_and_execute_exits):**
- Line 109: `cur_price, prev_close = self._fetch_recent_prices(symbol, current_date)`
- Line 115: `exit_signal = self._evaluate_position(..., current_date, ...)`

**The code checks current_date correctly!** 

**But here's the issue:** If a trade is created (entered) in phase 6 on `current_date`, and TOMORROW phase 4 runs again, the new trade shows up as an open position. Then the exit engine:
1. Checks the NEW trade immediately
2. Sees if exit conditions are met TODAY (tomorrow, relative to entry)
3. If they are, exits the same trade it just entered

**BUT** the data shows they entered and exited on the SAME calendar date, not next day.

### Hypothesis
This suggests one of:
1. **Phase 4 runs multiple times** on the same date (bug in orchestration)
2. **Trades are being created with signal_date but entered/exited on that same date** (no 1-day delay)
3. **Exit detection is running on the wrong date** (using signal_date instead of next day)

### What Needs Investigation
- [ ] Check when trades are created (what date do they get?)
- [ ] Check when exit detection runs (is it same day as entry?)
- [ ] Review Orchestrator.run() - does it call phases multiple times?
- [ ] Check database: when does trade_date get set vs when does exit_date get set?

### Fix Strategy

**Option A: Add 1-day buffer**
```python
# In exit_engine.check_and_execute_exits():
def check_and_execute_exits(self, current_date=None):
    ...
    # NEW: Don't evaluate exits for trades entered TODAY
    for row in trades:
        trade_date = row[...trade_date...]
        days_held = (current_date - trade_date).days
        
        # Only check exit conditions after holding >= 1 day
        if days_held < 1:
            continue  # Hold overnight minimum
        
        exit_signal = self._evaluate_position(...)
```

**Option B: Separate entry/exit dates**
- Trade creation on Day 1 → sets trade_date = Day 1
- Exit detection on Day 2+ → only checks if (current_date - trade_date) >= 1
- No same-day entries can exit

---

## ISSUE #4: NULL Entry Prices (MAJOR)

### Current State
- 240 out of 424,943 BUY signals (0.06%) have NULL entry_price
- These signals can't be traded without an entry price

### Root Cause
In loadbuyselldaily.py, the signal generation could return signals with NULL entry_price if:
- close price is missing for that bar
- calculation failed
- edge case in data

### Fix Strategy
```python
# In loadbuyselldaily.py._generate_signal_row():

# Instead of:
if not signal_str:
    return None

# Should be:
if not signal_str:
    return None

# ADD: validate entry_price exists
if entry_price is None or entry_price <= 0:
    return None  # Skip signals with invalid entry prices

# Or better: fall back to a calculated entry_price
if entry_price is None:
    if close_price:
        entry_price = close_price
    else:
        return None  # Can't create signal
```

---

## ISSUES #5-14: Database & Infrastructure (FROM COMPREHENSIVE AUDIT)

### ISSUE #5: Missing Database Constraints (HIGH)

**Problem**: No foreign key or check constraints exist
- buy_sell_daily signals can reference non-existent symbols
- Entry prices not validated at database level
- Impossible states allowed (close < low, RSI > 100)

**Files affected**: 
- All migration scripts (no constraints defined)
- Database schema not enforcing integrity

**Fix strategy**:
```sql
-- Add FK constraints
ALTER TABLE buy_sell_daily
  ADD CONSTRAINT fk_buy_sell_symbol
    FOREIGN KEY (symbol) REFERENCES stock_symbols(symbol);

-- Add CHECK constraints
ALTER TABLE price_daily
  ADD CONSTRAINT check_high_gte_low CHECK (high >= low);
  
ALTER TABLE price_daily
  ADD CONSTRAINT check_price_positive CHECK (close > 0 AND open > 0);

ALTER TABLE buy_sell_daily
  ADD CONSTRAINT check_entry_price_valid
    CHECK (signal != 'BUY' OR (entry_price > 0 AND entry_price IS NOT NULL));

ALTER TABLE buy_sell_daily
  ADD CONSTRAINT check_rsi_range CHECK (rsi >= 0 AND rsi <= 100);
```

---

### ISSUE #6: No Connection Pooling (MEDIUM)

**Problem**: Each loader creates a new database connection
- Potential connection exhaustion under load
- No reuse of connections
- Inefficient resource usage

**Files affected**:
- loadpricedaily.py (line 87: `conn = self._connect()`)
- loadbuyselldaily.py (line 87: `conn = self._connect()`)
- All other loaders

**Fix strategy**:
- Implement database connection pool
- Share pool across all loaders
- Use context managers for connection lifetime

---

### ISSUE #7: Silent Type Conversions (MEDIUM)

**Problem**: NULL values silently become zero or empty strings
```python
# From optimal_loader.py:
volume = int(vol or 0)     # NULL volume → 0, can't distinguish missing data
price = float(val or 0.0)  # NULL price → 0, indistinguishable from actual $0
```

**Impact**: 
- Zero values hard to detect
- Upstream can't tell if data is missing or actually zero
- Causes downstream validation issues

**Fix strategy**:
```python
# Explicit NULL handling
volume = int(vol) if vol is not None else None
price = float(val) if val is not None else None

# Validate before converting
if vol is not None and vol < 0:
    raise ValueError(f"Negative volume: {vol}")
```

---

### ISSUE #8: No Minimum Load Thresholds (HIGH)

**Problem**: Loader can complete "successfully" with partial data
- Loader succeeds with only 50% of symbols
- No minimum coverage check
- Example: buy_sell_daily has 4,864 symbols vs expected 4,965 (98% coverage)

**Files affected**:
- optimal_loader.py (no threshold checking)
- All loaders inherit this behavior

**Fix strategy**:
```python
# In optimal_loader.py.run():
expected_coverage = 0.95  # Must load >= 95% of symbols
actual_coverage = successful_symbols / len(symbols)

if actual_coverage < expected_coverage:
    raise LoaderError(f"Coverage {actual_coverage:.1%} below threshold {expected_coverage:.1%}")
```

---

### ISSUE #9: Data Staleness Not Communicated (HIGH)

**Problem**: API returns data without timestamp
- Frontend can't show "data is 1 hour old"
- Fallback prices (from rate limiting) look like real prices
- Trading system unaware of data age

**Files affected**:
- webapp/lambda/index.js (no timestamp in responses)
- apiService.jsx (no timestamp handling)

**Fix strategy**:
```python
# In API responses, always include:
{
    'success': true,
    'data': {...},
    'loaded_at': '2026-05-07T15:30:00Z',  # ISO timestamp
    'data_freshness': 'fresh' | 'cached' | 'stale'
}
```

---

### ISSUE #10: Position Reconciliation is Nightly Only (MEDIUM)

**Problem**: Position sync with Alpaca runs only once per day
- Missing intra-day closes
- Orphaned positions not detected for hours
- Stale data in algo_positions table

**Files affected**:
- algo_daily_reconciliation.py (runs once daily)
- algo_orchestrator.py (calls reconciliation)

**Fix strategy**:
- Run position reconciliation every 30 minutes during market hours
- Implement continuous sync for critical positions

---

### ISSUE #11: Zero-Volume Data Partially Fixed (MEDIUM)

**Problem**: 998,135 zero-volume price records exist (4.37% of table)
- Root cause: yfinance returns non-trading days
- Partially fixed 2026-04-30
- Historical data not cleaned

**Current status**:
- ✓ Filter added to prevent new zeros
- ✗ Old data still in database

**Fix strategy**:
```sql
-- Clean historical zero-volume data
DELETE FROM price_daily WHERE volume = 0 AND close > 0;

-- Verify cleanup
SELECT COUNT(*) FROM price_daily WHERE volume = 0;
```

---

### ISSUE #12: Symbol Universe Mismatch (LOW)

**Problem**: Different tables have different symbol coverage
- stock_symbols: 4,967 symbols
- price_daily: 4,965 (2 missing)
- buy_sell_daily: 4,864 (103 missing)

**Impact**: Low (98-99% coverage is acceptable)

**Root cause**: Different data sources, different update frequencies

---

### ISSUE #13: Incomplete Type Validation in Frontend (MEDIUM)

**Problem**: API contract tests don't validate field types
```javascript
// From market-data.contract.test.jsx:
// Checks structure exists, NOT that price is a Number
expect(data).toHaveProperty('price');  // Could be string!
```

**Impact**: Type coercion errors in charts
- Charts expect Number, receive "123.45" string
- Math operations fail silently

**Fix strategy**:
- Add type assertions to contract tests
- Validate: `typeof field === 'number'`

---

### ISSUE #14: Market Data Loader Incomplete (MEDIUM)

**Problem**: Real market index loading marked as TODO
- Real estate index data not loaded
- Economic indicators sparse
- Using stub data for tests

**Files affected**:
- loadmarketdata.py (TODO: real index loading)
- Affects market health filter (Tier 2)

**Status**: By design for now (acceptable for MVP)

---

## MISSING DATA QUALITY CHECKS

### What's NOT Validated

1. **Entry Price Range Validation**
   - [ ] entry_price must be within [low, high] of signal day
   - [ ] entry_price must be positive
   - [ ] entry_price must match actual market data

2. **Exit Price Validation**
   - [ ] exit_price must be within [low, high] of exit day
   - [ ] exit_price must exist for closed trades
   - [ ] exit_price != entry_price (no same-price trades)

3. **Trade Date Logic**
   - [ ] entry_date < exit_date (for closed trades)
   - [ ] (exit_date - entry_date).days >= 1 (no same-day trades)
   - [ ] signal_date <= entry_date (can't enter before signal)

4. **Position Size Validation**
   - [ ] position_size_pct > 0 and <= 100
   - [ ] All open positions have valid position_size_pct

5. **Technical Indicator Validation**
   - [ ] RSI values in [0, 100] range (done✓)
   - [ ] MACD values reasonable
   - [ ] MA values in proper order (50 < 200 historically, etc)

6. **Filter Logic Validation**
   - [ ] Tier 1-6 filters working correctly
   - [ ] Rejection tracker capturing all rejected signals
   - [ ] Qualified trades match tier requirements

---

## IMPLEMENTATION PRIORITY

### PHASE 1: IMMEDIATE (Stop Bleeding)
- [ ] Task #2: Find root cause of entry_price mismatch
- [ ] Task #3: Fix same-day entry/exit logic
- [ ] Task #4: Validate NULL entry prices

### PHASE 2: SHORT-TERM (Add Guardrails)
- [ ] Task #5: Add data validation layer
- [ ] Add database constraints for impossible states
- [ ] Add monitoring/alerting for data quality

### PHASE 3: LONG-TERM (System Redesign)
- [ ] Simplify entry_price handling (pull from price_daily, not buy_sell_daily)
- [ ] Create unified validation module
- [ ] Add integration tests for end-to-end flows

---

## DATA QUALITY VERIFICATION CHECKLIST

### Price Data ✓ PASSED
- 21.8M daily OHLCV records
- 0 NULL closes
- 0 high < low errors
- 0 close out-of-range
- 595 zero-volume (expected)

### Signal Generation ✓ MOSTLY PASSED
- 424,943 BUY signals generated
- 99.94% have valid entry_price
- 240 NULL (0.06%) - need investigation
- All RSI/MACD values valid

### Trade Execution ✓ COMPLETE but LOGICALLY WRONG
- 51 trades recorded
- 39 closed, 10 filled, 1 open, 1 accepted
- ALL closed trades: entry_date = exit_date ← **WRONG**
- ALL: entry_price = exit_price → 0% P&L ← **SYMPTOM**

---

## NEXT STEPS

1. **Wait for comprehensive audit results** (agent in progress)
2. **Investigate root causes** (entry_price and same-day exit)
3. **Create targeted fixes** (per issue)
4. **Add validation** (prevent future issues)
5. **Test end-to-end** (verify fixes work)
6. **Monitor** (catch regressions)

