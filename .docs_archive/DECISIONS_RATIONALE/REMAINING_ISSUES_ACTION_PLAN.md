# Remaining Data Quality Issues - Action Plan
**Status:** CRITICAL BLOCKERS ACTIVE  
**Date:** 2026-05-07

---

## CURRENT STATUS SNAPSHOT

```
ISSUE                          STATUS              COUNT           SEVERITY
Same-day entry/exit           BROKEN              39/39 trades     CRITICAL
All trades at 0% P&L          BROKEN              39/39 closed      CRITICAL
NULL entry prices             BROKEN              239 signals       MAJOR
Entry price out of range      BROKEN              24,309 (5.7%)     CRITICAL
Open/Pending positions        PENDING             11 trades         INFO

FIXED BY OTHERS:
Entry price field source      IN PROGRESS         -                 (someone else)
```

---

## CRITICAL ISSUE #1: SAME-DAY ENTRY/EXIT (39 TRADES)

### Current State
- **39 closed trades all have trade_date = exit_date**
- **Average hold: 0.00 days**
- **All P&L: 0.00%**

### Why It's Happening
1. Trade enters at market close (e.g., 2026-05-05)
2. Same day, exit engine checks Minervini break rule
3. Oversold bounce (RSI < 30) is still below 50-DMA on same day
4. Minervini rule triggers immediately → exit same day

### THE FIX (Simple - 2 minutes)

**File:** `algo_exit_engine.py`  
**Location:** Line 113, inside `check_and_execute_exits()`  
**Change:** Add 1-day minimum hold check

```python
# BEFORE:
days_held = (current_date - trade_date).days

exit_signal = self._evaluate_position(...)

# AFTER:
days_held = (current_date - trade_date).days

# CRITICAL: Prevent same-day exits (all trades currently at 0% P&L)
if days_held < 1:
    print(f"  {symbol}: need 1d hold (held {days_held}d)")
    continue

exit_signal = self._evaluate_position(...)
```

**Then test:**
```sql
-- Verify no same-day trades after fix
SELECT COUNT(*) FROM algo_trades 
WHERE status = 'closed' AND trade_date = exit_date;
-- Should return: 0 (currently 39)
```

---

## CRITICAL ISSUE #2: ENTRY PRICE OUT OF RANGE (24,309 signals - 5.7%)

### Current State
- Entry prices exist outside daily [low, high] range
- Example: daily range [$25.21-$26.54], entry_price=$25.01
- Makes it impossible to enter at those prices

### Why It's Happening
- Entry price being set to `buylevel` instead of market close price
- **NOTE:** Someone else is fixing this, but we need to verify the fix

### What to Do When Entry Price Fix Is Complete
1. Re-run signal loader: `python3 loadbuyselldaily.py --parallelism 8`
2. Verify: `SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND (entry_price < low OR entry_price > high);` → should return 0
3. Commit: "Verify: Entry price out-of-range issue resolved after loader fix"

---

## MAJOR ISSUE #3: NULL ENTRY PRICES (239 signals)

### Current State
- 239 BUY signals (0.06%) have NULL entry_price
- These cannot be traded

### The Fix (5 minutes)

**Step 1: Find why these signals have NULL**
```sql
SELECT symbol, date, close, entry_price, buylevel, rsi, macd
FROM buy_sell_daily
WHERE signal = 'BUY' AND entry_price IS NULL
LIMIT 10;
```

**Step 2: Understand the root cause**
- Are close prices NULL? → Indicator warmup issue
- Are early signals? → Not enough history
- Pattern? → Edge case in calculation

**Step 3: Fix in code**

**File:** `loadbuyselldaily.py`  
**Location:** Line 237, method `_generate_signal_row()`  
**Change:** Validate entry_price before returning

```python
# BEFORE:
if not signal_str:
    return None

def _f(v):
    return float(v) if v is not None and not pd.isna(v) else None

# ... calculate entry_price ...
entry_price = close_price

return {
    "signal": signal_str,
    "entry_price": entry_price,  # Could be None!
    ...
}

# AFTER:
if not signal_str:
    return None

# Validate all required fields
entry_price = close_price
if entry_price is None or entry_price <= 0:
    return None  # Skip signals with invalid entry prices

return {
    "signal": signal_str,
    "entry_price": entry_price,  # Guaranteed non-NULL
    ...
}
```

**Step 4: Clean existing data**
```sql
DELETE FROM buy_sell_daily 
WHERE signal = 'BUY' AND entry_price IS NULL;

-- Verify
SELECT COUNT(*) FROM buy_sell_daily 
WHERE signal = 'BUY' AND entry_price IS NULL;
-- Should return: 0
```

**Step 5: Test**
```bash
# Re-run loader to generate fresh signals
python3 loadbuyselldaily.py --symbols AAPL,MSFT --parallelism 2

# Verify no NULL entry prices in new signals
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
print(f"NULL entry prices: {cur.fetchone()[0]}")
EOF
```

---

## INFRASTRUCTURE ISSUE #4: ADD VALIDATION CONSTRAINTS

### Why This Matters
Database should enforce impossible states automatically, not rely on application code.

### The Fix (Database Level - 10 minutes)

```sql
-- Add constraints to prevent impossible states

-- 1. No same-day trades
ALTER TABLE algo_trades
ADD CONSTRAINT min_hold_one_day 
  CHECK (status != 'closed' OR (exit_date - trade_date) >= 1);

-- 2. Entry price in valid range
ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_in_range
  CHECK (signal != 'BUY' OR (entry_price >= low AND entry_price <= high));

-- 3. Entry price not NULL
ALTER TABLE buy_sell_daily
ADD CONSTRAINT entry_price_required
  CHECK (signal != 'BUY' OR entry_price IS NOT NULL);

-- 4. Exit after entry
ALTER TABLE algo_trades
ADD CONSTRAINT exit_after_entry
  CHECK (status != 'closed' OR exit_date > trade_date);
```

**Verify constraints were added:**
```sql
SELECT constraint_name FROM information_schema.table_constraints
WHERE table_name IN ('algo_trades', 'buy_sell_daily') 
  AND constraint_type = 'CHECK'
ORDER BY constraint_name;
```

---

## OPTIONAL: INFRASTRUCTURE IMPROVEMENTS #5-8

**These are improvements but not critical blockers:**

### #5: Connection Pooling
```python
# Instead of: conn = psycopg2.connect(...)
# Use connection pool to reuse connections
from psycopg2 import pool

db_pool = pool.SimpleConnectionPool(1, 5, **DB_CONFIG)
conn = db_pool.getconn()
# ... use conn ...
db_pool.putconn(conn)
```

### #6: Add Data Freshness Timestamps to API
```python
# API response should include:
{
    'success': True,
    'data': {...},
    'loaded_at': '2026-05-07T15:30:00Z',
    'data_age_minutes': 2
}
```

### #7: Real-time Position Reconciliation
```python
# Current: nightly only
# Upgrade: every 30 minutes during market hours
# Run: algo_reconciliation.py every 30 min
```

### #8: Add Type Validation in Frontend
```javascript
// Current: checks structure only
// expect(data).toHaveProperty('price')

// Upgrade: validate types too
// expect(typeof data.price).toBe('number')
```

---

## IMPLEMENTATION ORDER

### Phase 1: IMMEDIATE (Same Day - 30 minutes)
- [ ] **FIX #1:** Add 1-day minimum hold to exit engine
- [ ] Test: Verify no same-day trades
- [ ] Commit: "Fix: Prevent same-day entry/exit with 1-day minimum hold"

### Phase 2: THIS WEEK (Next 1-2 hours)
- [ ] **FIX #3:** Validate NULL entry prices in loader code
- [ ] Clean database of existing NULL entries
- [ ] Re-run loader to generate fresh signals
- [ ] Test: Verify 0 NULL entry prices
- [ ] Commit: "Fix: Validate and eliminate NULL entry prices"

### Phase 3: WAIT FOR (Someone else)
- [ ] **FIX #2:** Entry price field correction (in progress)
- [ ] When done: Re-run loader and verify out-of-range entries resolved

### Phase 4: INFRASTRUCTURE (This week)
- [ ] **FIX #4:** Add database constraints
- [ ] **FIX #5-8:** Infrastructure improvements (optional)
- [ ] Commit: "Infra: Add database constraints for data integrity"

---

## DETAILED STEPS FOR FIX #1 (Same-Day Exit)

```bash
# 1. Edit the file
nano algo_exit_engine.py

# 2. Find line 113:
# days_held = (current_date - trade_date).days

# 3. Add these 3 lines after it:
# if days_held < 1:
#     print(f"  {symbol}: need 1d hold")
#     continue

# 4. Save (Ctrl+X, Y, Enter in nano)

# 5. Test the change
python3 << 'EOF'
from algo_exit_engine import ExitEngine
from algo_config import get_config
config = get_config()
engine = ExitEngine(config)
exits = engine.check_and_execute_exits()
print(f"Exits executed: {exits}")
EOF

# 6. Verify database
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status='closed' AND trade_date=exit_date")
print(f"Same-day trades: {cur.fetchone()[0]} (should be 0 after fix)")
EOF

# 7. Commit
git add algo_exit_engine.py
git commit -m "Fix: Prevent same-day entry/exit with 1-day minimum hold"
```

---

## DETAILED STEPS FOR FIX #3 (NULL Entry Prices)

```bash
# 1. Edit loadbuyselldaily.py
nano loadbuyselldaily.py

# 2. Find _generate_signal_row() method (around line 237)

# 3. After calculating entry_price, add validation:
# if entry_price is None or entry_price <= 0:
#     return None

# 4. Save file

# 5. Clean existing NULL entries
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("DELETE FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
conn.commit()
print(f"Deleted {cur.rowcount} NULL entry_price signals")
EOF

# 6. Re-run loader
python3 loadbuyselldaily.py --symbols AAPL,MSFT --parallelism 2

# 7. Verify
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect(...)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND entry_price IS NULL")
null_count = cur.fetchone()[0]
print(f"NULL entry prices: {null_count} (should be 0)")
EOF

# 8. Commit
git add loadbuyselldaily.py
git commit -m "Fix: Validate and eliminate NULL entry prices in signals"
```

---

## SUCCESS CRITERIA

After completing ALL fixes:

```
METRIC                          BEFORE      AFTER       TARGET
Same-day entry/exit trades      39          0           0
P&L all zero                    39/39       0/39        <5
Average hold days               0.00        2-7         3+
NULL entry prices               239         0           0
Out of range entries            24,309      <100        0
Database constraints            0           4+          8+
```

---

## NEXT STEPS

1. **Read this document** ✓
2. **Do FIX #1 now** (5 min) → prevents more 0% trades
3. **Do FIX #3 this week** (15 min) → prevents new NULL signals
4. **Wait for entry price fix** (someone else)
5. **Add constraints** (10 min) → permanent safety net
6. **Test end-to-end** (30 min) → verify all working

**Total time to resolution: 1-2 hours**

