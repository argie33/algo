# Implementation Plan - Fix All Issues
**Goal:** Rewrite the system to follow the correct professional design  
**Scope:** 7 critical components, ~40 code changes  
**Expected Result:** Multi-day trades with realistic P&L, professional risk management

---

## PHASE 1: Fix Entry Price Corruption (Days 1-2)

### 1.1: Stop Using buy_sell_daily.entry_price for Trade Execution
**Files to change:** 
- `algo_filter_pipeline.py:83` - Stop pulling entry_price
- `algo_run_daily.py:93` - Stop using entry_price from signals

**Changes:**
```python
# WRONG (current):
entry_price = trade['entry_price']  # From buy_sell_daily.entry_price

# RIGHT:
# Fetch fresh market data on entry day
cur.execute("""
    SELECT close FROM price_daily 
    WHERE symbol = %s AND date = %s
""", (symbol, entry_date))
row = cur.fetchone()
entry_price = float(row[0]) if row else None
```

**Verification:**
- [ ] entry_price now comes from price_daily, not buy_sell_daily
- [ ] entry_price always matches a market close price
- [ ] entry_price is within [low, high] of that day

### 1.2: Update algo_filter_pipeline.py
**What to change:**
- Line 83-84: Change SELECT to NOT fetch entry_price
- Line 110-113: Don't use entry_price from signals
- Add new logic: On Day 1, fetch price_daily for entry_price

**New flow:**
```python
# Line 81-89: Changed
cur.execute("""
    SELECT symbol, date, signal
    FROM buy_sell_daily
    WHERE date = %s AND signal = 'BUY'
    ORDER BY symbol
""", (eval_date,))  # Only fetch symbol, date, signal

# Later: When evaluating, fetch entry_price fresh
for symbol, signal_date, _signal in signals:
    # Get fresh market data for entry day (signal_date + 1)
    entry_date = signal_date + timedelta(days=1)
    # Skip weekends (find next trading day)
    entry_date = self._find_next_trading_day(entry_date)
    
    # Fetch Day 1 close price
    entry_price = self._get_close_price(symbol, entry_date)
```

---

## PHASE 2: Fix Entry/Exit Timing (Days 2-3)

### 2.1: Separate signal_date from entry_date
**Files:** `algo_run_daily.py`, `algo_trade_executor.py`

**Changes:**
```python
# WRONG (current - lines 139-142):
signal_date = eval_date  
result = executor.execute_trade(
    ...
    signal_date=signal_date
)

# RIGHT:
signal_date = signal_generated_date  # From signal
entry_date = eval_date  # When trade actually enters
result = executor.execute_trade(
    ...
    signal_date=signal_date,
    entry_date=entry_date  # Add this parameter
)
```

### 2.2: Fix algo_trade_executor.py to enforce date separation
**Changes:**
```python
# Line 121-122: Require entry_date parameter
def execute_trade(self, symbol, entry_price, shares, stop_loss_price,
                  target_1_price=None, target_2_price=None, target_3_price=None,
                  signal_date=None, entry_date=None, ...):  # ADD entry_date param
    
    # Add validation: entry_date must be after signal_date
    if signal_date and entry_date:
        if entry_date <= signal_date:
            return {'success': False, 'status': 'invalid',
                    'message': f'entry_date must be after signal_date'}
    
    # Store both dates in algo_trades
    # signal_date = when signal was detected (for auditing)
    # entry_date = when trade actually entered (for lifecycle)
```

### 2.3: Update database schema for algo_trades
```sql
-- Add entry_date if missing, or verify it exists
ALTER TABLE algo_trades 
ADD COLUMN IF NOT EXISTS entry_date DATE;

-- Ensure both dates are tracked
-- signal_date = Day 0 (when signal generated)
-- entry_date = Day 1 (when trade enters)
```

---

## PHASE 3: Fix Exit Timing (Days 3-4)

### 3.1: Update algo_exit_engine.py to check next day only
**Current problem:** Checks exit conditions on signal_date (same day as entry)  
**Fix:** Check on current market data (next day +)

**Changes:**
```python
# Line 163: When checking exits in algo_run_daily
exits = exit_engine.check_and_execute_exits(eval_date)

# This calls algo_exit_engine.py - it should:
# 1. Get all OPEN trades
# 2. For each trade, fetch TODAY'S market data
# 3. Check: Is trend_broken(today's data)?
# 4. If yes: Exit at today's close

# In algo_exit_engine.py:
def check_and_execute_exits(self, eval_date):
    """Check exits on CURRENT market data, not old signal data."""
    
    self.cur.execute("""
        SELECT trade_id, symbol, entry_date, entry_price, stop_loss_price
        FROM algo_trades
        WHERE status = 'open' AND entry_date < %s  -- Before today
    """, (eval_date,))
    
    for trade_id, symbol, entry_date, entry_price, stop_loss in trades:
        # Enforce minimum holding period
        days_held = (eval_date - entry_date).days
        if days_held < 1:  # Must hold at least 1 full day
            continue
        
        # Fetch TODAY'S market data
        today_close, today_volume, today_sma200 = self._get_market_data(symbol, eval_date)
        
        # Check: Minervini trend break (closed below 200-day MA on volume)
        if today_close < today_sma200 and today_volume > avg_volume:
            self._execute_exit(trade_id, eval_date, today_close, reason="Minervini trend break")
```

### 3.2: Add minimum holding period enforcement
```python
# In algo_trade_executor.py - prevent same-day exit
if entry_date and exit_date:
    holding_days = (exit_date - entry_date).days
    if holding_days < 1:
        raise ValueError(f"Invalid: exit_date must be at least 1 day after entry")
```

---

## PHASE 4: Clean Up Signal Data (Days 4-5)

### 4.1: Fix or Remove buy_sell_daily.entry_price
**Option A: Delete the field (clean)**
```sql
ALTER TABLE buy_sell_daily DROP COLUMN entry_price;
```

**Option B: Keep but document it's NOT for trading**
```sql
-- Rename for clarity
ALTER TABLE buy_sell_daily RENAME COLUMN entry_price TO theoretical_buy_level;

-- Add comment
COMMENT ON COLUMN buy_sell_daily.theoretical_buy_level IS 
  'Theoretical buy zone price - FOR ANALYSIS ONLY. Do not use for trade execution. Use price_daily.close instead.';
```

### 4.2: Add Validation to Signal Generation
**In loadbuyselldaily.py:**
```python
# If generating any level price, validate it
if buy_level:
    # Validate it's within daily range OR document why not
    if buy_level < low or buy_level > high:
        log.warning(f"buy_level ${buy_level} outside daily range [${low}-${high}]")
        # Decide: set to close, or set to None?
        buy_level = close_price  # Use market close instead
```

### 4.3: Add Data Quality Checks
```python
# Before storing signal in DB, validate:
def validate_signal(symbol, date, signal, close, entry_price, low, high):
    errors = []
    
    # Check entry_price is reasonable
    if entry_price:
        if entry_price < close * 0.95 or entry_price > close * 1.05:
            errors.append(f"entry_price {entry_price} more than 5% from close {close}")
        if entry_price < low or entry_price > high:
            errors.append(f"entry_price {entry_price} outside daily range [{low}-{high}]")
    
    if errors:
        log.warning(f"{symbol} {date}: {', '.join(errors)}")
        # Option: Set to None so executor uses market data on entry day
        entry_price = None
    
    return entry_price
```

---

## PHASE 5: Update Filter Pipeline (Days 5-6)

### 5.1: algo_filter_pipeline.py - Use Next-Day Market Data
**Change the evaluation logic:**
```python
def evaluate_signals(self, eval_date=None):
    # eval_date is TODAY (e.g., 2026-05-07)
    # We're evaluating signals from YESTERDAY (2026-05-06)
    
    signal_date = eval_date - timedelta(days=1)
    
    # Get yesterday's signals
    signals = self._get_signals_for_date(signal_date)
    
    # TODAY we evaluate if they qualify for entry
    # So we check TODAY's market data
    
    for symbol, signal_date, signal in signals:
        # Get TODAY'S market data
        today_data = self._get_market_data(symbol, eval_date)
        
        # Check: Is Stage 2 still valid TODAY?
        # Check: Is price still above 30-day MA TODAY?
        # Use TODAY'S data, not signal_date's data
        
        if conditions_still_valid(today_data):
            entry_price = today_data['close']  # TODAY's close
            entry_date = eval_date  # TODAY
            
            # Create trade for entry TODAY
            qualified_trades.append({
                'symbol': symbol,
                'signal_date': signal_date,  # Yesterday
                'entry_date': entry_date,  # Today
                'entry_price': entry_price,  # Today's close
                ...
            })
```

### 5.2: Enforce T3 (Stage 2) Check on Entry Day
```python
# Currently: Checks stage at signal generation (old data)
# Fix: Check stage at entry (fresh data)

# In evaluate_signal():
def evaluate_signal(self, symbol, signal_date, entry_price):
    # ... T1, T2 checks ...
    
    # T3: Check Stage 2 on ENTRY DATE (today), not signal_date
    entry_date = datetime.now().date()
    
    cur.execute("""
        SELECT weinstein_stage FROM trend_template_data
        WHERE symbol = %s AND date = %s
    """, (symbol, entry_date))  # TODAY, not signal_date
    
    result = cur.fetchone()
    if not result or result[0] != 2:
        return {'pass': False, 'reason': 'T3 Stage 2 not confirmed on entry date'}
```

---

## PHASE 6: Update Trade Execution (Days 6-7)

### 6.1: algo_run_daily.py - Correct Date Handling
```python
# Step 1: Evaluate signals (get YESTERDAY's signals, check TODAY's data)
eval_date = datetime.now().date()
qualified_trades = pipeline.evaluate_signals(eval_date)
# These already have entry_date = TODAY, signal_date = YESTERDAY

# Step 2-3: Size and execute
for trade in qualified_trades:
    signal_date = trade['signal_date']  # Yesterday
    entry_date = trade['entry_date']  # Today
    entry_price = trade['entry_price']  # Today's close
    
    # Execute with correct dates
    result = executor.execute_trade(
        symbol=trade['symbol'],
        entry_price=entry_price,
        shares=trade['shares'],
        stop_loss_price=trade['stop_loss'],
        signal_date=signal_date,  # When signal was generated
        entry_date=entry_date,  # When trade enters
    )

# Step 4: Check exits on OPEN trades only
# Use TODAY's data to check if exit conditions met
exit_engine.check_and_execute_exits(eval_date)
```

### 6.2: algo_trade_executor.py - Store Correct Dates
```python
# Line 195+: When inserting into algo_trades
cur.execute("""
    INSERT INTO algo_trades 
    (trade_id, symbol, signal_date, entry_date, entry_price, ...)
    VALUES (%s, %s, %s, %s, %s, ...)
""", (
    trade_id,
    symbol,
    signal_date,  # Day 0 - when signal detected
    entry_date,  # Day 1 - when trade enters
    entry_price,  # Day 1 close - actual market price
    ...
))
```

---

## PHASE 7: Verify and Test (Days 7-8)

### 7.1: Audit Existing 51 Trades
```sql
-- Check for broken trades
SELECT trade_id, symbol, signal_date, entry_date, exit_date,
       CASE WHEN entry_date = exit_date THEN 'BROKEN'
            WHEN entry_date = signal_date THEN 'BROKEN'
            ELSE 'OK'
       END as status
FROM algo_trades
WHERE status IN ('CLOSED', 'EXITED');
```

**Expected:** 0 broken trades after fixes  
**Action:** If any found, fix dates retrospectively

### 7.2: Verify Entry Prices
```sql
-- Check entry prices match market data
SELECT t.trade_id, t.symbol, t.entry_date, t.entry_price,
       p.close as market_close,
       ABS(t.entry_price - p.close) / p.close * 100 as diff_pct
FROM algo_trades t
LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.entry_date = p.date
WHERE status IN ('CLOSED', 'EXITED')
ORDER BY diff_pct DESC;
```

**Expected:** All differences < 1% (rounding only)

### 7.3: Verify Trade Duration
```sql
-- Check holding periods
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN (exit_date - entry_date) < 1 THEN 1 ELSE 0 END) as same_day,
  SUM(CASE WHEN (exit_date - entry_date) >= 1 THEN 1 ELSE 0 END) as multi_day,
  AVG(exit_date - entry_date) as avg_hold_days,
  MIN(exit_date - entry_date) as min_hold_days,
  MAX(exit_date - entry_date) as max_hold_days
FROM algo_trades
WHERE status IN ('CLOSED', 'EXITED');
```

**Expected:** 
- same_day = 0 (no more same-day trades)
- avg_hold_days = 5-15 (professional holding period)
- min_hold_days >= 1 (never same day)

### 7.4: Verify P&L Distribution
```sql
-- Check P&L is realistic
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN profit_loss_pct = 0 THEN 1 ELSE 0 END) as zero_pnl,
  SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as winners,
  SUM(CASE WHEN profit_loss_pct < 0 THEN 1 ELSE 0 END) as losers,
  ROUND(AVG(profit_loss_pct), 2) as avg_pnl_pct,
  SUM(profit_loss_dollars) as total_pnl
FROM algo_trades
WHERE status IN ('CLOSED', 'EXITED');
```

**Expected:**
- zero_pnl = 0 (no more 0% P&L trades)
- winners + losers = total (not all the same direction)
- avg_pnl_pct realistic for swing trading (varies by market)

---

## Implementation Timeline

| Phase | Task | Days | Estimated |
|-------|------|------|-----------|
| 1 | Fix entry price | 2 | Medium |
| 2 | Fix entry/exit timing | 2 | Medium |
| 3 | Fix exit timing | 1 | Low |
| 4 | Clean signal data | 1 | Low |
| 5 | Update filter pipeline | 2 | Medium |
| 6 | Update execution | 1 | Low |
| 7 | Test & verify | 2 | Medium |
| | **TOTAL** | **11 days** | |

---

## Success Criteria (All Must Pass)

- [ ] No trade has entry_date == exit_date
- [ ] entry_date > signal_date for all trades
- [ ] entry_price matches price_daily.close ±1%
- [ ] exit_price matches price_daily.close ±1%
- [ ] All trades have holding period >= 1 day
- [ ] 0% P&L trades = 0 (not all trades)
- [ ] P&L distribution is realistic (mix of + and -)
- [ ] Minimum 5 multi-day trades in backtest
- [ ] Exit reasons mention "trend break", not "same day"
- [ ] Filter pipeline checks entry date, not signal date

---

## Rollback Plan (If Issues)

Each phase has natural commit points:
- After Phase 1: entry_price fixed
- After Phase 2: dates separated
- After Phase 3: exit timing fixed
- etc.

If any phase breaks production:
1. Revert to start of that phase
2. Identify root cause
3. Fix in isolation
4. Re-test before continuing

