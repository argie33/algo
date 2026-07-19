# Edge Case Bug Report - Session 274+

## Summary
Found and fixed critical edge case bugs in the algo trading system when testing extreme market conditions and data anomalies.

---

## BUGS FOUND & FIXED

### 1. ✅ FIXED: Negative Stop Loss in Extreme Volatility (Phase 8)

**File:** `algo/orchestrator/phase8_entry_execution.py:898-901`

**Bug Description:**
When ATR (volatility measure) is extremely large relative to price, the stop loss calculation produces negative values:
```python
stop_loss = min(
    sma_50 - atr,      # e.g., $50 - $150 = -$100 (NEGATIVE!)
    entry_price - 2.0 * atr  # e.g., $100 - $300 = -$200 (NEGATIVE!)
)
```

**Impact:**
- Impossible to execute trades at negative prices
- Would crash position sizer expecting positive stop prices
- Silent data corruption if position tracker doesn't validate
- Risk calculation becomes unrealistic (150% risk instead of ~10%)

**Scenario:**
- Entry: $100
- ATR: $150 (150% volatility!)
- SMA_50: $50
- Result: Stop = $-200 (invalid)

**Fix Applied:**
Added validation to reject trades when:
1. Entry price <= 0 (corrupted price data)
2. ATR < 0 (impossible, indicates data error)
3. SMA_50 <= 0 (corrupted moving average)
4. Calculated stop_loss <= 0 (extreme volatility, cannot place safe stop)

**Status:** ✅ FIXED in commit c... (validation added lines 892-941)

---

## POTENTIAL BUGS (Investigated, Found Guarded)

### 2. ✅ GUARDED: Risk Percentage Division by Zero (Phase 8, Line 903)

**File:** `algo/orchestrator/phase8_entry_execution.py:943`

**Code:**
```python
risk_pct = (entry_price - stop_loss) / entry_price * 100
```

**Concern:** Division by zero if entry_price == 0

**Status:** ✅ GUARDED - Entry price validated on line 893-899

---

### 3. ✅ GUARDED: P&L Percentage Calculation (Phase 9, Line 645)

**File:** `algo/orchestrator/phase9_reconciliation.py:645`

**Code:**
```python
pnl_pct = (exit_price - entry_price) / entry_price * 100
```

**Concern:** Division by zero if entry_price == 0

**Status:** ✅ GUARDED - Entry price validated on lines 641-643

---

### 4. ✅ GUARDED: Position Sizer Risk Calculation (Phase 6)

**File:** `algo/trading/position_sizer.py:705-712`

**Code:**
```python
risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
if risk_per_share <= 0:
    raise ValueError(...)  # Fail-fast
shares = int((risk_dollars / risk_per_share).quantize(...))
```

**Status:** ✅ GUARDED - Division guarded with validation

---

### 5. ✅ GUARDED: Ladder Percentage (Phase 3, Line 117)

**File:** `algo/orchestrator/phase3_position_monitor.py:117`

**Code:**
```python
ladder_pct_stop = (current_to_stop_dist / entry_to_stop_range) * 100
```

**Concern:** Division by zero if entry_to_stop_range == 0

**Status:** ✅ GUARDED - Check on line 116: `if entry_to_stop_range > 0:`

---

### 6. ✅ GUARDED: ATR Volatility Calculation (Phase 7, Line 97)

**File:** `algo/orchestrator/phase7_signal_generation.py:97`

**Code:**
```python
atr_pct = (atr_14 / close) * 100
```

**Concern:** Division by zero if close == 0

**Status:** ✅ GUARDED - Validation on line 93-96: `if close is None or close <= 0: raise ValueError(...)`

---

### 7. ✅ GUARDED: Exit Price Validation

**File:** `algo/trading/executor_exit_handler.py:616-626`

**Concerns Checked:**
- Exit price <= 0 (validated line 616)
- Entry price <= 0 (validated line 622)  
- Risk per share <= 0 (validated line 630)

**Status:** ✅ ALL GUARDED

---

## TESTING OBSERVATIONS

### Edge Cases Tested:
1. ✅ Empty signal lists - handled correctly
2. ✅ Null technical data - caught and logged
3. ✅ Zero portfolio value - triggers error as expected
4. ✅ Negative prices - all caught and rejected
5. ✅ Extreme volatility (ATR > price) - now rejected safely
6. ✅ Tight stops (1% risk) - rejected per policy
7. ✅ Floating point precision - Decimal handles correctly

### Configuration Issues Discovered:
- ⚠️ Config keys required at runtime: `max_concentration_pct`, `max_position_size_pct` not in initialization

---

## RECOMMENDATIONS

### 1. Config Validation Enhancement
Add all required config keys to PositionSizer.__init__ instead of discovering at runtime:
```python
required_config_keys = [
    # ... existing keys ...
    "max_position_size_pct",
    "max_concentration_pct",
    # ... others discovered at runtime ...
]
```

### 2. Stop Loss Floor Check
Consider adding a minimum stop distance check (e.g., stop >= entry * 0.95) to catch unrealistic scenarios early.

### 3. Data Integrity Audits
Regular checks for:
- Negative prices in price_daily table
- Negative ATR values (should never happen)
- SMA_50 values outside reasonable range

### 4. Circuit Breaker Monitoring
Log when Phase 8 rejects trades due to extreme volatility (stop_loss <= 0) - could indicate market stress.

---

## FILES MODIFIED

- ✅ `algo/orchestrator/phase8_entry_execution.py` - Added stop loss validation

## FILES TO REVIEW

- `algo/trading/position_sizer.py` - Config initialization  
- `algo/orchestrator/phase7_signal_generation.py` - Risk scoring
- `algo/orchestrator/phase3_position_monitor.py` - Position tracking

---

## CONCLUSION

**EDGE CASE TESTING RESULT: ✅ PRODUCTION-READY (with fix applied)**

The main critical bug (negative stop loss) has been fixed. All other division-by-zero risks are properly guarded with explicit validation. System handles edge cases safely with fail-fast principles.

**Next Steps:**
1. Enhance config validation to fail-fast on missing keys
2. Add data integrity audit for price and technical indicator ranges
3. Monitor logs for pattern of "stop_loss_negative" rejections (market stress indicator)
