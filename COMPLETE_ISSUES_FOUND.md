# Complete Issues Found - Comprehensive List
**Date:** 2026-05-07  
**Status:** All issues documented before fixes begin

---

## THE COMPLETE FLOW OF PROBLEMS

### Issue #1: Entry Price Calculated Wrong (Root Cause)
**Location:** `loadbuyselldaily.py:269`  
**Code says:** `entry_price = close_price`  
**Reality:** Database has `entry_price != close_price` in 83% of signals (353,014/424,703)  
**What actually happens:** 
- `entry_price` = `buylevel` (100% match in database)
- `buylevel` != `close` in 81% of cases
- Some `entry_price` values are OUTSIDE daily [low, high] range (5.7% of signals)

**Why this breaks trading:**
- Trades are created with artificial "buy zone" prices, not market prices
- Entry prices don't match what actually happened in the market
- Example: Signal on 2026-05-05 close=$123.75, entry_price=$120.00 (buylevel)

**Files affected:**
- loadbuyselldaily.py - claims to set entry_price = close
- buy_sell_daily table - stores wrong entry_price values
- algo_filter_pipeline.py:83 - pulls this wrong entry_price
- algo_run_daily.py:93 - uses wrong entry_price
- algo_trade_executor.py:142 - executes with wrong entry_price

---

### Issue #2: Same-Day Entry/Exit (100% of trades)
**Location:** `algo_run_daily.py:139` and `algo_exit_engine.py`  
**Pattern:** ALL 39 closed trades have `signal_date == exit_date`  
**Why this breaks:**
- Trade enters: 2026-05-05 @ market close
- Trade exits: 2026-05-05 @ same market close (same day, same price)
- Result: 0.00% P&L guaranteed

**Root cause:** Exit logic runs on `signal_date` instead of next trading day

**Files involved:**
- algo_run_daily.py - calls execute_trade with signal_date=eval_date (line 139)
- algo_exit_engine.py - checks exit conditions on signal_date instead of next day
- algo_orchestrator.py - orchestrates all phases on same day

---

### Issue #3: Exit Detection on Wrong Day
**Location:** `algo_exit_engine.py`  
**Problem:** "Minervini trend break" rule checks signal_date's data  
**Should:** Check next trading day's data

**Current logic (WRONG):**
```
if has_trend_break(data_on_signal_date):
    exit_today()  # Executes immediately!
```

**Should be:**
```
next_day = signal_date + 1 trading day
if has_trend_break(data_on_next_day):
    exit_on_next_day()
```

**Impact:** Rule triggers on day of entry because signal day often IS the oversold bounce

---

### Issue #4: No Next-Day Data Check
**Location:** Signal generation and trade execution  
**Problem:** System doesn't enforce waiting for market open on next trading day  
**Current:** Generate signal Day 1 → Create trade Day 1 → Exit Day 1  
**Should:** Generate signal Day 1 → Check data Day 2 → Create trade if conditions met → Monitor for exit Day 3+

---

### Issue #5: Entry Price Outside Daily Range
**Location:** `buy_sell_daily` table  
**Data:** 24,309 BUY signals (5.7%) have entry_price outside [low, high]
**Example:** 
- Daily range: [$25.21 - $26.54]
- entry_price: $25.01 (below low!) or $27.00 (above high!)

**This is impossible** in real trading - you can't enter outside the day's traded range

---

### Issue #6: Null Entry Prices in Signals
**Location:** `buy_sell_daily`  
**Data:** 240 BUY signals (0.06%) have NULL entry_price  
**Impact:** These signals can't be traded (no entry price to use)  
**Should:** Either calculate or skip with reason

---

### Issue #7: Signal Data Quality
**Location:** Various  
**Found:**
- 46 signals with NaN RSI (expected for early data - minor issue)
- 237 signals on zero-volume days (shouldn't trade)
- No validation that entry_price is realistic ($0.01-$100,000)

---

### Issue #8: Orchestration Timing
**Location:** `algo_run_daily.py`  
**Problem:** All phases (signal → entry → exit) happen in same daily run  
**Should:** 
- Day 1: Signal generation (RSI < 30 detected)
- Day 2: Entry execution (use Day 2 market data)
- Day 3+: Exit checking (monitor for trend break)

---

### Issue #9: No Distinction Between Theory and Reality
**Location:** Throughout system  
**Problem:** Mixes:
- Theoretical levels (buylevel = buy zone)
- Actual market prices (close)
- Trade execution prices (should use market data)

**System conflates all three**, causing entry_price to be theoretical instead of real

---

### Issue #10: Missing Validation Layers
**Location:** All components  
**Missing:**
1. Entry price must be within [low, high] of signal day
2. Entry price must match close price (or declared as different)
3. Exit must be on next trading day minimum (not same day)
4. All prices must be > $0 and realistic
5. Trades must have positive holding period before exit

---

## Summary Table

| Issue | Severity | Location | Impact | Fix Scope |
|-------|----------|----------|--------|-----------|
| entry_price ≠ close | CRITICAL | loadbuyselldaily, buy_sell_daily, filter_pipeline | 353k signals wrong | Data + Code |
| Same-day exit | CRITICAL | algo_run_daily, algo_exit_engine | 0% P&L on all trades | Code |
| Exit checks wrong day | CRITICAL | algo_exit_engine | Immediate exits | Code |
| entry_price outside range | CRITICAL | buy_sell_daily | 24k invalid signals | Data + Validation |
| No next-day wait | CRITICAL | Orchestration | No multi-day trades | Code |
| NULL entry prices | MAJOR | buy_sell_daily | 240 untradeable signals | Data |
| Zero volume signals | MAJOR | buy_sell_daily | 237 invalid signals | Validation |
| Theory vs Reality | CRITICAL | All components | Conceptual confusion | Redesign |

---

## What Needs to Be Fixed

### Immediate (Blocking Trades):
1. Fix entry_price calculation/retrieval
2. Implement next-day exit detection
3. Prevent same-day entry/exit

### Short-term (Data Quality):
1. Validate entry_price is in [low, high]
2. Handle NULL entry prices
3. Reject zero-volume signals

### Medium-term (Architecture):
1. Separate theoretical analysis from execution
2. Implement proper multi-day trade lifecycle
3. Add comprehensive validation

### Long-term (Redesign):
1. Rethink signal→entry→exit timing
2. Use market data for all execution (not theoretical levels)
3. Enforce business rules at data layer

