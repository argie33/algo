# System-Wide Fix Plan
**Goal:** Fix all "weird things" preventing correct operation

---

## ISSUE #1: Entry Price Confusion
**Status:** CRITICAL | **Scope:** buy_sell_daily.entry_price field

### What's Wrong
- `entry_price` column stores `buylevel` (theoretical), not market price
- 83% of signals have entry_price != close price
- 5.7% have entry_price outside daily [low, high] range
- This breaks any trading logic expecting real market prices

### Where It Happens
1. **Signal generation** - calculating entry_price incorrectly
2. **Trade execution** - using entry_price as if it's market close
3. **Data schema** - field name is misleading

### The Fix
**Option A (Quick fix):**
```sql
UPDATE buy_sell_daily 
SET entry_price = close 
WHERE entry_price IS NOT NULL AND entry_price != close;
```

**Option B (Correct fix - recommended):**
- Rename field: `entry_price` → `buy_zone_price` or delete it
- Signal generation should NOT create entry_price
- Trade generation should use market close price from price_daily table
- Check: WHERE does buy_sell_daily.entry_price get SET?

### Code to Review
- Where is buy_sell_daily being updated?
- `algo_signal_*.py` files
- SQL scripts that populate buy_sell_daily
- Trade execution logic

---

## ISSUE #2: Same-Day Entry/Exit
**Status:** CRITICAL | **Scope:** Trade orchestration flow

### What's Wrong
```
ALL 39 closed trades: signal_date = exit_date
Result: 0% P&L because entry and exit at same price
```

This should NEVER happen. Trades must have multi-day lifecycle.

### Where It Happens
1. **Exit detection** - checking exit conditions on signal_date
2. **Orchestrator** - not enforcing day separation
3. **Exit rules** - "Minervini trend break" firing immediately

### The Fix
**Exit logic MUST wait for next trading day:**

```python
# WRONG (current):
if signal_date:
    if check_minervini_break(signal_date):
        exit_today()

# CORRECT:
if signal_date:
    exit_check_date = signal_date + 1 trading day
    if check_minervini_break(exit_check_date):
        exit_on_that_date()
```

### Code to Review
- `algo_exit_engine.py` - WHERE is the trend break logic?
- `algo_orchestrator.py` - how does it sequence entry/exit?
- Trade closure logic - WHAT sets exit_date?

---

## ISSUE #3: Exit Detection on Wrong Data
**Status:** CRITICAL | **Scope:** Minervini trend break rule

### What's Wrong
```
Exit rule checks: "closed below key MA on volume"
Current: Checking signal_date's data
Should: Check next trading day's data

signal_date = 2026-05-05, close = $8.38
exit_date = 2026-05-05, close = $8.38 ← SAME DAY, SAME PRICE
```

The rule triggers immediately because it's using signal day's own data.

### The Fix
```python
# Signal generated on Day 1
signal_date = 2026-05-05

# Exit check on Day 2
exit_check_date = 2026-05-06  # Next trading day
entry_price = day1_close  # = $8.38

# On Day 2, check:
day2_data = get_price_data(symbol, exit_check_date)
if day2_close < day2_sma(150) AND volume > avg_volume:
    exit_on_day2()
    exit_price = day2_close
```

### Code to Review
- `algo_exit_engine.py` - the trend break checking function
- How exit_date is determined
- What data is passed to exit rules

---

## ISSUE #4: Trade Entry Timing
**Status:** CRITICAL | **Scope:** Trade execution sequence

### What's Wrong
```
Trades entering at signal_date using same day's data
Should: Enter at signal_date OR next day
Must: Use real market data, not theoretical prices
```

### The Fix
```python
# Trade entry should use market data:
signal_date = 2026-05-05
entry_date = signal_date  # or signal_date + 1
entry_price = price_daily.close WHERE date = entry_date
  (NOT buy_sell_daily.entry_price!)

# Only proceed if:
# 1. price_daily record exists for entry_date
# 2. entry_price is within [low, high] of that day
# 3. volume > 0
```

### Code to Review
- Where algo_trades.entry_price gets set
- How it gets the market price
- Is it using buy_sell_daily.entry_price? (WRONG)
- Should it use price_daily.close instead? (RIGHT)

---

## ISSUE #5: Null Entry Prices
**Status:** MAJOR | **Scope:** buy_sell_daily signal generation

### What's Wrong
```
240 BUY signals (0.06%) have NULL entry_price
These can't be traded without knowing entry price
```

### The Fix
Either:
1. **Calculate** entry_price for all signals (should be close price)
2. **Delete** these records (if they're invalid)
3. **Skip** them explicitly (set to NULL means "skip", with reason)

### Code to Review
- Signal generation logic - why are some entry_price NULL?
- Should this field exist at all?

---

## ISSUE #6: Entry Price Outside Daily Range
**Status:** CRITICAL | **Scope:** Data validation

### What's Wrong
```
24,309 signals have entry_price outside [low, high]
Example: daily range [$25.21-$26.54], entry_price=$25.01

This is impossible in real trading
```

### The Fix
1. **Validate** all entry_price values against daily OHLC range
2. **Flag** any out-of-range entries as invalid
3. **Fix** the source - why is entry_price calculated wrong?

### Code to Review
- Where entry_price is calculated
- How it's validated (probably not validated at all)
- Add: IF entry_price < low OR entry_price > high THEN flag error

---

## ISSUE #7: Exit Reason Mislabeling
**Status:** MAJOR | **Scope:** Trade classification

### What's Wrong
```
ALL 39 closed trades have same exit reason:
"Minervini trend break: closed below key MA on volume"

But they ALL exited SAME DAY they entered
This reason is clearly wrong - can't have trend break in 1 day
```

### The Fix
- Exit reason MUST match actual exit logic
- If same-day, reason should be "ERROR: same-day exit"
- If different-day, reason should describe what actually happened

---

## ISSUE #8: Position Size Calculation
**Status:** MAJOR | **Scope:** Risk management

### What's Wrong
```
1 out of 51 trades has invalid position_size_pct
Should be: 0 < position_size_pct <= 100
Currently: Some NULL or out of range
```

### The Fix
- Add validation: ALL trades must have valid position_size_pct
- If missing, calculate it based on risk rules

---

## Implementation Order

### PHASE 1: Stop The Bleeding (Day 1)
1. Identify: WHERE does entry_price get set in buy_sell_daily?
2. Identify: WHERE does exit_date get set in algo_trades?
3. Identify: WHERE is the "Minervini trend break" logic?
4. Create: Data backup BEFORE making changes

### PHASE 2: Fix Entry Logic (Day 2-3)
1. Fix entry_price to use market close (not buylevel)
2. Verify: trades would use price_daily.close instead
3. Validate: all entry prices now match daily ranges

### PHASE 3: Fix Exit Logic (Day 3-4)
1. Fix exit detection to check next trading day
2. Implement: proper date advancement
3. Verify: no more same-day entry/exit

### PHASE 4: Fix Trade Execution (Day 4-5)
1. Use correct entry prices (from price_daily)
2. Wait for next day before checking exit
3. Match entry price to actual market data

### PHASE 5: Validation & Testing (Day 5-6)
1. Run full backtest with fixed logic
2. Verify trades span multiple days
3. Verify P&L calculation works
4. Check for any remaining "weird things"

---

## Critical Questions to Answer

1. **buy_sell_daily.entry_price:**
   - Where is this field SET? (SQL file? Python script? Formula?)
   - Is it supposed to be close price?
   - Why isn't it being validated?

2. **Exit detection (Minervini rule):**
   - What file contains the check?
   - What date does it use? (signal_date? next day?)
   - How is exit_date determined?

3. **Trade entry logic:**
   - Does it use buy_sell_daily.entry_price?
   - Should it use price_daily.close instead?
   - Is there validation?

4. **Trade orchestration:**
   - How many days between entry and exit detection?
   - Should there be a minimum (e.g., >= 2 days)?
   - What enforces this?

---

## Success Criteria

After fixes:
- [ ] No trades with entry_date = exit_date
- [ ] All entry prices match price_daily.close
- [ ] All entry prices within [low, high] range
- [ ] Exit reasons match actual exit logic
- [ ] P&L is non-zero for most trades
- [ ] Backtest shows realistic returns
- [ ] No "weird things" left

---

## Files to Audit

**High Priority:**
- [ ] Where buy_sell_daily.entry_price is calculated
- [ ] algo_exit_engine.py - exit detection logic
- [ ] algo_orchestrator.py - execution sequencing
- [ ] Where algo_trades are created
- [ ] Price data queries (price_daily usage)

**Medium Priority:**
- [ ] Signal generation scripts
- [ ] Trade reconciliation logic
- [ ] Data validation rules
- [ ] Test files (if any)

**Low Priority:**
- [ ] Dashboard/reporting
- [ ] Monitoring scripts
- [ ] Historical data

