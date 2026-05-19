# Fallback Data Fixes — Implementation Summary

**Date**: 2026-05-19  
**Status**: ✅ COMPLETE (All 6 CRITICAL fixes implemented)  
**Testing Required**: Full orchestrator --dry-run needed before production

---

## Summary of Changes

All instances of fake/fallback/placeholder data have been identified and removed. System now **FAILS LOUDLY** instead of silently using synthetic data.

### Files Modified

1. **algo/algo_filter_pipeline.py** — 2 critical stop-loss fallbacks removed
2. **algo/algo_circuit_breaker.py** — VIX fallback removed (fail-closed on missing data)
3. **algo/algo_position_monitor.py** — Stop loss fallback for stock splits removed
4. **loaders/load_technical_data_daily.py** — Added filtering for API-limit fallback data
5. **loaders/loadbuyselldaily.py** — Added filtering for zero-price/zero-volume data

---

## Fix Details

### 1. ✅ Emergency 5% Stop Fallback (CRITICAL)

**File**: `algo/algo_filter_pipeline.py` (lines 1070-1106)

**Before**:
```python
if atr_value and atr_value > 0:
    stop_loss_price = max(0.01, entry_price - (2.0 * atr_value))
else:
    stop_loss_price = entry_price * 0.95  # Emergency fallback — UNSAFE
    logger.warning(f'using 5% emergency fallback — RISK INFLATED')
```

**After**:
```python
if atr_value and atr_value > 0:
    stop_loss_price = max(0.01, entry_price - (2.0 * atr_value))
else:
    # FAIL-CLOSED: No valid stop calculation
    logger.error(f'REJECTED: Stop calculation failed and no ATR available')
    return {
        'pass': False,
        'reason': 'Stop calculation failed; no ATR available for fallback',
        'shares': 0,
    }
```

**Impact**: Signals requiring a stop price without adequate technical indicators are now REJECTED instead of trading with a loose 5% floor.

---

### 2. ✅ 8% Floor Fallback (CRITICAL)

**File**: `algo/algo_filter_pipeline.py` (lines 976-996)

**Before**:
```python
candidates = [c for c in (sma_50, swing_low, atr_stop) if c is not None and 0 < c < entry]
if not candidates:
    self._last_stop_method = 'fallback_8pct_floor'
    self._last_stop_reasoning = '8% floor — no structural levels available'
    return round(floor_stop, 2)  # Returns placeholder 8% stop
```

**After**:
```python
candidates = [c for c in (sma_50, swing_low, atr_stop) if c is not None and 0 < c < entry]
if not candidates:
    # FAIL-CLOSED: No structural stops available
    logger.error(f'No structural levels for {symbol} (insufficient technical data)')
    return None  # Signals fail T3 tier when no structural stops found

# In calling function, if stop is None:
if stop_loss_price is None:
    return {
        'pass': False,
        'reason': 'No valid stop loss available (insufficient technical indicators)',
    }
```

**Impact**: Signals that lack structural support levels (SMA-50, swing low, ATR all missing) are REJECTED. No placeholder 8% floor trading.

---

### 3. ✅ Position Monitor Stock Split Fallback (CRITICAL)

**File**: `algo/algo_position_monitor.py` (lines 602-631)

**Before**:
```python
if qty_change_pct > 20:  # Likely a split
    split_ratio = alpaca_qty / db_qty
    new_stop = db_stop / split_ratio if db_stop else entry_price * 0.95
    # Updates stop with fallback if original stop missing
```

**After**:
```python
if qty_change_pct > 20:  # Likely a split
    split_ratio = alpaca_qty / db_qty
    if not db_stop:
        # FAIL-CLOSED: Can't apply split ratio without knowing original stop
        logger.critical(f'Stock split detected but no stop price in DB — Manual review required')
        # Update quantity but leave stop untouched
        # Log CRITICAL alert for manual intervention
        continue  # Skip auto-adjustment

    new_stop = db_stop / split_ratio  # Only if original stop known
```

**Impact**: When a stock split is detected but the original stop price is missing from the database, the system logs a CRITICAL alert instead of guessing with entry_price * 0.95. Quantity is updated but stop adjustment requires manual verification.

---

### 4. ✅ VIX Circuit Breaker Fail-Closed (CRITICAL)

**File**: `algo/algo_circuit_breaker.py` (lines 358-374)

**Before**:
```python
if vix is None:
    vix = self._compute_vix_fallback(current_date)  # Computed VIX
    source = "computed"
else:
    source = "actual"

# Uses computed VIX (which falls back to neutral 20 if insufficient data)
threshold = float(self.config.get('vix_max_threshold', 35.0))
return {
    'halted': vix > threshold,
    'reason': f'VIX {vix:.1f} > {threshold:.0f} ({source})',
}
```

**After**:
```python
if vix is None:
    # FAIL-CLOSED: No real VIX data. Halt trading.
    logger.critical(f'VIX missing — cannot reliably assess market volatility. Halting trading.')
    return {
        'halted': True,
        'reason': 'VIX data missing; unable to assess market volatility — FAIL-CLOSED',
        'value': None,
    }

# Only use actual VIX values from database
threshold = float(self.config.get('vix_max_threshold', 35.0))
return {
    'halted': vix > threshold,
    'reason': f'VIX {vix:.1f} > {threshold:.0f}' if vix > threshold else f'VIX {vix:.1f}',
}
```

**Impact**: Circuit breaker no longer uses neutral VIX=20 as fallback. If VIX data is missing/stale, trading is halted. This prevents entry signals during actual volatility spikes when VIX data source fails.

---

### 5. ✅ Identical OHLC Filtering (API-Limit Fallback)

**File**: `loaders/load_technical_data_daily.py` (lines 87-94)

**Added**:
```python
# Filter out identical OHLC rows (API-limit fallback/stale data)
initial_len = len(df)
df = df[~((df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"]))]
if len(df) < initial_len:
    filtered_count = initial_len - len(df)
    logger.debug(f"Filtered out {filtered_count} rows with identical OHLC (API-limit fallback data)")
```

**File**: `loaders/loadbuyselldaily.py` (lines 211-218)

**Added**: Same filtering logic to exclude identical OHLC rows from signal generation.

**Impact**: Rows where open=high=low=close (which indicate API rate-limit fallback or no trading) are excluded from:
- Technical indicator calculations (RSI, MACD, SMA, ATR, Bollinger Bands)
- Buy/sell signal generation

This prevents false signals based on stale data.

---

### 6. ✅ Zero-Price and Zero-Volume Validation

**File**: `loaders/load_technical_data_daily.py` (lines 58-86)

**Added**:
```python
# Validate: reject zero-price or zero-volume rows
if close is None or close <= 0:
    # Zero/negative close price = data error
    continue
if volume is not None and volume == 0:
    # Zero volume = halted/no trading
    continue
```

**File**: `loaders/loadbuyselldaily.py` (lines 136-169)

**Added**: Same zero-price/zero-volume validation.

**Impact**: Rows with:
- `close <= 0` (data errors, impossible prices)
- `volume = 0` (halted stocks, no trading)

Are excluded from technical calculations and signal generation.

---

## Data Quality Improvements

### Before (Vulnerable to)
- ❌ Silent corruption: Fallback data used without warning
- ❌ Risk inflation: Loose stop prices when structural levels missing
- ❌ Market stress blindness: Circuit breaker disabled when VIX missing
- ❌ False signals: API-limit fallback data passed through as real
- ❌ Stock split errors: Stops guessed as entry_price * 0.95

### After (Hardened)
- ✅ Fail-loud: Signals rejected if stop calculation impossible
- ✅ Risk tight: Only structural stops accepted, no placeholders
- ✅ Circuit breaker active: Halts on VIX data gaps (can't mask volatility)
- ✅ Clean signals: API-limit fallback filtered out before indicator calc
- ✅ Stock splits safe: Manual intervention required if original stop missing
- ✅ Zero data rejected: No trading on halted stocks or zero-price data

---

## Testing Checklist

Before returning to production, run:

```bash
# Full orchestrator validation (no actual trades)
python3 algo/algo_orchestrator.py --dry-run

# Data patrol — verify all checks pass
python3 algo/algo_data_patrol.py --quick

# Filter pipeline tests
python3 -m pytest tests/unit/test_filter_pipeline.py -v

# Circuit breaker tests (verify fail-closed on missing VIX)
python3 -m pytest tests/unit/test_circuit_breaker.py -v

# Position monitor tests (verify stock split logic)
python3 -m pytest tests/integration/test_orchestrator_flow.py -v
```

**Expected Results**:
- ✅ Orchestrator should report signal count (may be lower due to rejections)
- ✅ Data patrol critical checks all pass
- ✅ No signals execute with "fallback" stops
- ✅ VIX missing should halt circuit breaker
- ✅ Stock splits without original stop logged as CRITICAL

---

## Fallback Mechanisms Still in Place (Intentionally)

These are NOT removed because they provide safe fallbacks:

1. **Data Patrol Logging**: Detects but logs (doesn't use synthetic data)
2. **Signal Age Gate**: Rejects old signals (fail-safe)
3. **Market Health Staleness**: Waits 5 days for fresh data (defensive)
4. **Connection Pooling Fallback**: Logs and reconnects (infrastructure resilience)

---

## Documentation

- **Audit**: `FALLBACK_DATA_AUDIT.md` — Complete inventory of all fallbacks found
- **This File**: `FALLBACK_DATA_FIXES.md` — Implementation details

---

## Sign-Off

- **Implementation Date**: 2026-05-19
- **All 6 CRITICAL fixes**: ✅ COMPLETE
- **Testing Required**: ✅ See checklist above
- **Status**: Ready for dry-run validation

**Next Step**: Run `python3 algo/algo_orchestrator.py --dry-run` and verify no signals execute with fallback/fake data.
