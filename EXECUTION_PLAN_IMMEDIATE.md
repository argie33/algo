# Immediate Execution Plan - Data Quality & System Fixes
**Status:** READY FOR IMPLEMENTATION  
**Priority:** CRITICAL (all trading halted until fixed)

---

## QUICK SUMMARY

You have **3 critical defects** preventing correct system operation:

1. **Entry Price Source**: Signals use wrong entry_price field (or old data)
2. **Same-Day Entry/Exit**: All 39 closed trades enter and exit same day
3. **NULL Entry Prices**: 240 signals (0.06%) missing entry price

All 3 must be fixed before trading can resume.

---

## PART 1: INVESTIGATE ENTRY PRICE ISSUE (1-2 hours)

### Step 1.1: Check Current Data in Database

```sql
-- What does the data actually look like?
SELECT 
    symbol, date, close, entry_price, buylevel,
    (entry_price - close) as diff,
    CASE 
        WHEN entry_price IS NULL THEN 'NULL'
        WHEN entry_price < low OR entry_price > high THEN 'OUT_OF_RANGE'
        WHEN entry_price = close THEN 'MATCHES_CLOSE'
        WHEN entry_price = buylevel THEN 'MATCHES_BUYLEVEL'
        ELSE 'OTHER'
    END as category
FROM buy_sell_daily
WHERE signal = 'BUY'
LIMIT 1000;

-- Count by category
SELECT 
    CASE 
        WHEN entry_price IS NULL THEN 'NULL'
        WHEN entry_price < low OR entry_price > high THEN 'OUT_OF_RANGE'
        WHEN entry_price = close THEN 'MATCHES_CLOSE'
        WHEN entry_price = buylevel THEN 'MATCHES_BUYLEVEL'
        ELSE 'OTHER'
    END as category,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct
FROM buy_sell_daily
WHERE signal = 'BUY'
GROUP BY category
ORDER BY count DESC;
```

**What to look for:**
- Are most showing `MATCHES_CLOSE` or `MATCHES_BUYLEVEL` or `OUT_OF_RANGE`?
- If `MATCHES_CLOSE`, the loader is working correctly (issue might be OLD data)
- If `MATCHES_BUYLEVEL` or `OUT_OF_RANGE`, the loader has a bug

### Step 1.2: Check Loader Code Version

```bash
# Compare loadbuyselldaily.py in main repo vs lambda-deploy
diff loadbuyselldaily.py lambda-deploy/loadbuyselldaily.py

# Look specifically for entry_price assignment
grep -n "entry_price\s*=" loadbuyselldaily.py
grep -n "entry_price\s*=" lambda-deploy/loadbuyselldaily.py
```

**Expected output:**
- Line ~269 in both: `entry_price = close_price`
- If different, lambda version might have the bug

### Step 1.3: Check Git History

```bash
# When was entry_price logic last changed?
git log -p --follow -S "entry_price = close" loadbuyselldaily.py | head -100

# What data was loaded when?
git log --oneline | grep -i "signal\|load" | head -20
```

### DECISION TREE

```
If entry_price = close in the data:
    → Loader is correct, data is fresh
    → Skip to PART 2

If entry_price != close OR out of range:
    → OLD DATA ISSUE: Re-run loader to refresh
    → Run: python3 loadbuyselldaily.py --parallelism 8
    → Then verify data again with Step 1.1 query

If lambda-deploy version is different:
    → CODE DIVERGENCE ISSUE
    → Update lambda-deploy version to match main
    → Commit: "Fix: Sync loadbuyselldaily with main version"
```

---

## PART 2: FIX SAME-DAY ENTRY/EXIT (2-3 hours)

### Step 2.1: Understand Current Trade Lifecycle

First, let's trace a single trade through the system:

```sql
-- Pick a trade that closed with 0% P&L
SELECT 
    trade_id, symbol, trade_date, status,
    entry_price, exit_price,
    (exit_price - entry_price) as diff,
    entry_date, exit_date,
    (exit_date - entry_date) as days_held
FROM algo_trades
WHERE status = 'closed' AND exit_price = entry_price
LIMIT 1;

-- Get the symbol and dates for detailed investigation
-- Example: symbol=PLTR, entry_date=2026-05-03, exit_date=2026-05-04
```

### Step 2.2: Trace Signal to Trade Creation

Using the symbol/date from Step 2.1:

```sql
-- Where did this trade come from?
SELECT * FROM buy_sell_daily 
WHERE symbol = 'PLTR' 
  AND date >= '2026-05-03' AND date <= '2026-05-04'
  AND signal = 'BUY';

-- When was the trade created?
SELECT 
    trade_id, symbol, entry_date, exit_date,
    created_at, updated_at
FROM algo_trades
WHERE symbol = 'PLTR'
  AND entry_date >= '2026-05-03'
ORDER BY created_at;

-- When did exit happen?
SELECT * FROM algo_audit_log
WHERE trade_id = 'YOUR_TRADE_ID'
ORDER BY timestamp;
```

### Step 2.3: Check Orchestrator Flow

```bash
# Look at where exits and entries are called
grep -n "phase_4\|phase_6\|check_and_execute_exits\|execute_trade" algo_orchestrator.py

# Expected: exits BEFORE entries
# Actual: ?
```

### Step 2.4: Add 1-Day Hold Minimum

**FIX:** Modify exit_engine.py to enforce minimum hold time:

```python
# In algo_exit_engine.py, method check_and_execute_exits()

# Find this section (around line 115):
days_held = (current_date - trade_date).days

# ADD immediately after:
# Don't evaluate exits for trades entered today
if days_held < 1:
    print(f"  {symbol}: too new (held {days_held} days, need >= 1)")
    continue

exit_signal = self._evaluate_position(...)
```

**Then test:**
```bash
# Create a test case
python3 -c "
from algo_exit_engine import ExitEngine
from datetime import date, timedelta
from algo_config import get_config

config = get_config()
engine = ExitEngine(config)

# Test with a trade entered today
# It should NOT find an exit
"
```

---

## PART 3: FIX NULL ENTRY PRICES (1 hour)

### Step 3.1: Find Which Signals Have NULL

```sql
SELECT 
    symbol, date, close, buylevel, entry_price, 
    signal, rsi, macd, signal_line
FROM buy_sell_daily
WHERE signal = 'BUY' AND entry_price IS NULL
ORDER BY date DESC
LIMIT 20;
```

### Step 3.2: Understand Why

Look at the query result and check:
- Are close prices NULL? (check `close` column)
- Are these at the start of date history? (likely indicator warmup)
- Pattern in dates?

### Step 3.3: FIX in Code

**In loadbuyselldaily.py, method _generate_signal_row():**

```python
# Current code (line 268-270):
entry_price = close_price

# Change to:
entry_price = close_price
if entry_price is None or entry_price <= 0:
    return None  # Skip signals with invalid entry prices

# Add this check before returning the dict (line 305+):
# Validate all required fields
if not all([
    entry_price is not None and entry_price > 0,
    signal_str in ('BUY', 'SELL'),
    close_price is not None and close_price > 0,
]):
    return None
```

### Step 3.4: Clean Existing Data

```sql
-- Remove the 240 NULL entry_price signals
DELETE FROM buy_sell_daily 
WHERE signal = 'BUY' AND entry_price IS NULL;

-- Verify they're gone
SELECT COUNT(*) FROM buy_sell_daily 
WHERE signal = 'BUY' AND entry_price IS NULL;
-- Should return: 0
```

---

## PART 4: ADD VALIDATION LAYER (2 hours)

Create a new validation module:

**File: data_quality_validator.py**

```python
#!/usr/bin/env python3
"""Data quality validation and integrity checks."""

class DataQualityValidator:
    """Validate data before it's used for trading."""
    
    @staticmethod
    def validate_buy_signal(row):
        """Validate a signal row."""
        errors = []
        
        # Check entry_price
        if row.get('entry_price') is None:
            errors.append('entry_price is NULL')
        elif row['entry_price'] <= 0:
            errors.append(f'entry_price <= 0: {row["entry_price"]}')
        elif row.get('low') and row.get('high'):
            if row['entry_price'] < row['low'] or row['entry_price'] > row['high']:
                errors.append(f'entry_price outside [low,high]: ${row["entry_price"]} not in [${row["low"]}, ${row["high"]}]')
        
        # Check date
        if row.get('date') is None:
            errors.append('date is NULL')
        
        # Check signal type
        if row.get('signal') not in ('BUY', 'SELL'):
            errors.append(f'invalid signal: {row.get("signal")}')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    @staticmethod
    def validate_trade(trade):
        """Validate a trade record."""
        errors = []
        
        # Entry/exit dates
        if trade.get('entry_date') and trade.get('exit_date'):
            days = (trade['exit_date'] - trade['entry_date']).days
            if days < 1:
                errors.append(f'same-day trade (days={days})')
        
        # Entry/exit prices
        if trade.get('entry_price') == trade.get('exit_price'):
            if trade.get('status') == 'closed':
                errors.append('entry_price == exit_price for closed trade')
        
        # Position size
        pos_size = trade.get('position_size_pct', 0)
        if pos_size <= 0 or pos_size > 100:
            errors.append(f'invalid position_size_pct: {pos_size}')
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
```

**Use it in algo_filter_pipeline.py:**

```python
from data_quality_validator import DataQualityValidator

# In evaluate_signals(), validate each signal:
for symbol, signal_date, _signal, entry_price in signals:
    row = {'entry_price': entry_price, 'date': signal_date, 'signal': _signal, ...}
    validation = DataQualityValidator.validate_buy_signal(row)
    
    if not validation['valid']:
        print(f"  SKIP {symbol}: data quality issues: {validation['errors']}")
        tracker.log_rejection(...)
        continue
    
    # Process signal...
```

---

## PART 5: TESTING & VERIFICATION (1-2 hours)

### Test 5.1: Entry Price Correctness

```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()

# Check: all entry prices should match close
cur.execute("""
    SELECT COUNT(*) as bad_count
    FROM buy_sell_daily
    WHERE signal = 'BUY' 
      AND entry_price != close
""")

bad = cur.fetchone()[0]
print(f"Entry prices not matching close: {bad}")
assert bad == 0, f"FAILED: {bad} signals have entry_price != close"
print("PASS: All entry prices match close")
EOF
```

### Test 5.2: Same-Day Exit Prevention

```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()

# Check: no closed trades with entry_date == exit_date
cur.execute("""
    SELECT COUNT(*) as bad_count
    FROM algo_trades
    WHERE status = 'closed'
      AND entry_date = exit_date
""")

bad = cur.fetchone()[0]
print(f"Same-day entry/exit trades: {bad}")
assert bad == 0, f"FAILED: {bad} trades have entry_date == exit_date"
print("PASS: No same-day trades")
EOF
```

### Test 5.3: NULL Entry Price Prevention

```bash
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()

# Check: no signals with NULL entry_price
cur.execute("""
    SELECT COUNT(*) as bad_count
    FROM buy_sell_daily
    WHERE signal = 'BUY' AND entry_price IS NULL
""")

bad = cur.fetchone()[0]
print(f"Signals with NULL entry_price: {bad}")
assert bad == 0, f"FAILED: {bad} signals have NULL entry_price"
print("PASS: No NULL entry prices")
EOF
```

---

## IMPLEMENTATION CHECKLIST

### Investigation Phase
- [ ] Part 1.1: Run SQL to check current entry_price data
- [ ] Part 1.2: Check loader code version
- [ ] Part 1.3: Check git history
- [ ] Part 1: DECISION → decide action

### Fixes Phase
- [ ] Part 2.1-2.4: Fix same-day entry/exit (add 1-day hold)
- [ ] Part 3.1-3.4: Fix NULL entry prices
- [ ] Part 4: Add validation layer
- [ ] Commit: "Fix: Add data validation and same-day trade prevention"

### Testing Phase
- [ ] Part 5.1: Test entry prices
- [ ] Part 5.2: Test no same-day trades
- [ ] Part 5.3: Test no NULL prices
- [ ] Run backtest to verify P&L now non-zero
- [ ] Commit: "Test: Verify all data quality fixes pass"

### Deployment Phase
- [ ] Update lambda-deploy/ versions
- [ ] Restart orchestrator
- [ ] Monitor next 3 trading days
- [ ] Commit: "Deploy: Data quality fixes to production"

---

## ESTIMATED TIME

- Investigation: 1-2 hours
- Fixes: 3-4 hours  
- Testing: 1-2 hours
- **TOTAL: 5-8 hours**

---

## CRITICAL SUCCESS CRITERIA

After fixes are complete, verify:

1. **All entry_prices match market data**
   - entry_price should equal close price OR calculated fairly
   - ALL entry_prices within daily [low, high] range

2. **No same-day entry/exit**
   - No trades with entry_date == exit_date
   - Minimum hold time: 1 day

3. **No NULL entry prices**
   - 0 signals with NULL entry_price
   - All signals have valid, positive entry_price

4. **P&L is non-zero**
   - Backtest results show realistic returns
   - Not all trades at exactly 0%

5. **System is ready to trade**
   - No circuit breakers firing
   - Orchestrator runs without errors
   - Can execute new trades on next market day

