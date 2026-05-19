# Comprehensive Fallback Data Audit

**Goal**: Identify ALL instances of fake/fallback/mock/placeholder data that could corrupt trading decisions. In finance, silent corruption is worse than no data — we fail loudly.

**Status**: 🔴 CRITICAL FINDINGS IDENTIFIED

---

## Executive Summary

The system has several **CRITICAL** fallback mechanisms that use synthetic/computed/default data instead of real data:

1. **Stop-loss price fallbacks** — Emergency 5% & 8% floors when structural levels missing
2. **VIX fallbacks** — Neutral VIX=20 when missing; computed from SPY volatility
3. **API limit corruption** — Identical OHLC values passed through as real data
4. **Zero/empty data** — Zero volume, zero prices, NULL values silently processed

These fallbacks can cause:
- **Risk inflation**: Reduced stop losses → larger position losses
- **Wrong circuit breakers**: Neutral VIX during actual volatility spikes
- **Bad fill prices**: API-limit fallback OHLC masking real moves
- **Silent data degradation**: No warning when data becomes unreliable

---

## CRITICAL FINDINGS

### 1. Stop-Loss Price Fallbacks (T4 Risk Filter)
**File**: `algo/algo_filter_pipeline.py` (lines 1071-1091)  
**Risk Level**: 🔴 CRITICAL

When proper stop calculation fails, system uses cascading fallbacks:

```python
# Lines 1071-1091
if not stop_loss_price or stop_loss_price >= entry_price:
    # Try 2x ATR fallback if ATR available
    if atr_value and atr_value > 0:
        stop_loss_price = max(0.01, entry_price - (2.0 * atr_value))
        logger.warning(f'[T5] using 2x ATR fallback: {stop_loss_price:.2f}')
    else:
        # EMERGENCY: 5% floor when ATR missing
        stop_loss_price = entry_price * 0.95
        logger.warning(f'[T5] using 5% emergency fallback — RISK INFLATED')
```

**Problem**: 
- 5% floor is TOO LOOSE for real trading — could allow 5% loss per position
- ATR might be stale/missing if technical_data_daily is stale
- No check that ATR is from TODAY's data — could be 7 days old

**Example impact**: 
- Entry: $100, Stop: $95 (5% floor)
- Real structural stop should be: $92 (SMA-20)
- = 3% more loss exposure per trade

### 2. Stop-Loss Floor (8% Fallback)
**File**: `algo/algo_filter_pipeline.py` (lines 978-987)  
**Risk Level**: 🔴 CRITICAL

When no structural levels found (SMA-50, swing low, ATR):

```python
# Lines 978-987
floor_stop = entry * (1.0 - max_stop_pct)  # max_stop_pct defaults to 0.08 (8%)
candidates = [c for c in (sma_50, swing_low, atr_stop) if c is not None and 0 < c < entry]
if not candidates:
    self._last_stop_method = 'fallback_8pct_floor'
    return round(floor_stop, 2)  # Return 8% loss floor
```

**Problem**:
- 8% is a placeholder emergency value, not based on actual market structure
- If SMA-50, swing low, AND ATR all missing = data quality issue (should REJECT not fall back)
- Cascades: tier can hit T4 with 8% floor, then T5 re-calculates with 5% floor = conflicting stops

**Impact**: Position can trade with no real structural stop.

### 3. Position Monitor Stop Fallback
**File**: `algo/algo_position_monitor.py` (line 607)  
**Risk Level**: 🔴 CRITICAL

```python
# Line 607 — split-adjusted stop calculation
new_stop = db_stop / split_ratio if db_stop else entry_price * 0.95
```

**Problem**:
- Uses entry_price as fallback for split-adjusted stops
- Marked as CRITICAL in comments but STILL HAS FALLBACK

**Recent fix** (commit f1a5f6b98): Removed entry_price fallback for current_price, but NOT for stop calculation.

---

## HIGH RISK FINDINGS

### 4. VIX Fallbacks (Circuit Breaker)
**File**: `algo/algo_circuit_breaker.py` (lines 361-418)  
**Risk Level**: 🟠 HIGH

Two layers of VIX fallbacks:

**Layer 1**: Missing VIX data → Compute from SPY volatility
```python
# Line 362-364
if vix is None:
    vix = self._compute_vix_fallback(current_date)
    source = "computed"
```

**Layer 2**: Insufficient SPY data → Use neutral VIX=20
```python
# Line 397
if len(prices) < 5:
    logger.warning(f"VIX fallback: insufficient SPY data ({len(prices)} days), using neutral 20")
    return 20.0
```

**Problem**:
- Neutral VIX=20 used when volatility might be 40+ (real-money trading)
- Computed VIX from SPY has 0.80-0.85 correlation (not perfect)
- If VIX missing = VIX table stale? But circuit breaker still runs with fake VIX

**Impact**: 
- Circuit breaker disabled during actual market stress (VIX spike)
- Allows entry execution when market halted/stressed

---

### 5. API-Limit Corruption (Identical OHLC)
**File**: `algo/algo_data_patrol.py` (lines 288-302)  
**Risk Level**: 🟠 HIGH

Pattern detected: `open = high = low = close` indicates API limit hit or no trading:

```python
# Lines 288-302
# Identical OHLC = high==low==open==close (often API-limit fallback)
self.cur.execute("""
    SELECT COUNT(*) FROM price_daily
    WHERE date = (SELECT MAX(date) FROM price_daily)
      AND open = high AND high = low AND low = close
      AND volume > 0
""")
ident_count = int(self.cur.fetchone()[0] or 0)
if ident_count > 30:
    self.log('identical_ohlc', WARN, 'price_daily',
             f'{ident_count} symbols with identical OHLC (suspicious)',
             {'count': ident_count})
```

**Problem**:
- Data Patrol WARNS but doesn't REJECT
- Identical OHLC signals are still used in T3 (swing score) and T4 calculations
- No filtering to exclude these rows from technical indicator calculations

**Impact**:
- Stale/fallback price data used to compute RSI, SMA, ATR
- False signals when data source fails

---

### 6. Zero-Volume & Zero-Price Data
**File**: `algo/algo_data_patrol.py` (lines 249-286)  
**Risk Level**: 🟠 HIGH

Data patrol detects but doesn't reject:

```python
# Lines 249-254
self.cur.execute("""
    SELECT DISTINCT symbol FROM price_daily
    WHERE date = (SELECT MAX(date) FROM price_daily)
      AND (volume = 0 OR open = 0 OR close = 0)
    ORDER BY symbol
""")
```

**Problem**:
- Zero-volume rows are common for halted/delisted stocks
- Zero-price rows are data errors (should be NULL)
- Filter pipeline doesn't exclude these from entry/exit calculations
- Signal is generated → filter checks volume? Need to verify

---

## MEDIUM RISK FINDINGS

### 7. Coverage Thresholds
**File**: `algo/algo_data_patrol.py` (lines 109-111)  
**Risk Level**: 🟡 MEDIUM

```python
# Lines 109-111
'coverage_thresholds': {
    'min_universe_pct': 75,  # Allow 75% instead of 95% - yfinance has limits
    'min_coverage_ratio': 0.75,
}
```

**Problem**:
- 75% universe coverage means up to 25% of stocks missing data
- If major cap stocks missing (e.g., AAPL, MSFT) → sector exposure skewed
- No per-sector minimum coverage check

---

### 8. Market Health 5-Day Fallback
**File**: `algo/algo_filter_pipeline.py` (line 566)  
**Risk Level**: 🟡 MEDIUM

Market health check falls back 5 days if current date data missing:

```python
# Line 566
def _tier2_market_health(self, signal_date) -> Dict[str, Any]:
    """Market health for the signal's date, with 5-day fallback."""
```

**Problem**:
- If market_health_daily is stale, uses old health status
- No indicator that health is stale/fallback

---

## ALREADY FIXED ✅

From commit `f1a5f6b98`:

1. ✅ **Entry price as fallback for current_price** (algo_position_monitor.py)
   - Was: `cur_price = db_price or entry_price`  
   - Now: `REJECT if no real current price`

2. ✅ **CloudWatch metric 999 fallback** (lambda/data-freshness-monitor)
   - Was: `age_days = 999 if NULL`
   - Now: `age_days = 0 with warning`

3. ✅ **Trade executor fallback** (algo_trade_executor.py)
   - Was: `executed_price = entry_price for pending orders`
   - Now: `executed_price = None until actually filled`

---

## Risk Matrix

| Issue | File | Severity | Impact | Fix |
|-------|------|----------|--------|-----|
| **5% stop fallback** | algo_filter_pipeline.py:1090 | CRITICAL | Risk inflation | Fail-closed if missing |
| **8% floor fallback** | algo_filter_pipeline.py:982 | CRITICAL | No structural stop | Reject signal if insufficient data |
| **Position monitor stop** | algo_position_monitor.py:607 | CRITICAL | Fallback stop | Use split_ratio or reject |
| **VIX neutral=20** | algo_circuit_breaker.py:397 | HIGH | Disabled circuit breaker | Fail-closed if no VIX |
| **API-limit OHLC** | price_daily table | HIGH | Stale data in signals | Filter identical OHLC |
| **Zero price/volume** | price_daily table | HIGH | Halt data passed through | Exclude from technical calculations |
| **75% coverage** | algo_data_patrol.py:110 | MEDIUM | Sector skew | Add per-sector minimums |
| **Market health fallback** | algo_filter_pipeline.py:566 | MEDIUM | Old health status | Log when fallback used |

---

## Recommendations

### Tier 1 (Fix Immediately)
1. **Remove 5% stop emergency fallback** → Fail-closed (reject signal) if ATR missing
2. **Remove 8% floor fallback** → Require minimum 2 structural levels or reject
3. **Fix position monitor stop** → Document split-adjusted stop calculation or reject

### Tier 2 (Fix This Sprint)
4. **VIX circuit breaker** → Fail-closed if no VIX (don't use neutral=20)
5. **Filter identical OHLC** → Exclude from technical calculations
6. **Reject zero-price rows** → Treat as data error, not valid price

### Tier 3 (Monitor/Harden)
7. **Coverage alerts** → Monitor per-sector coverage, alert if <80%
8. **Market health logging** → Log when using fallback health status
9. **Data freshness** → Add data_as_of timestamp checks

---

## Testing Required

After fixes:
- [ ] Run full orchestrator with --dry-run to find signal rejections
- [ ] Verify no signals execute with emergency fallback stops
- [ ] Check circuit breaker properly halts on VIX gaps
- [ ] Audit position monitor stops for all open positions
- [ ] Data patrol runs green on all critical checks

---

## Database Queries to Validate

```sql
-- Find prices with identical OHLC (API-limit corruption)
SELECT COUNT(*) FROM price_daily 
WHERE date = (SELECT MAX(date) FROM price_daily)
  AND open = high AND high = low AND low = close;

-- Find zero-price or zero-volume data
SELECT COUNT(*) FROM price_daily 
WHERE date = (SELECT MAX(date) FROM price_daily)
  AND (close = 0 OR volume = 0);

-- Find missing technical indicators (causes fallback stops)
SELECT COUNT(*) FROM technical_data_daily 
WHERE date = (SELECT MAX(date) FROM technical_data_daily)
  AND (atr IS NULL OR sma_50 IS NULL OR rsi IS NULL);

-- Check buy_sell_daily signals — count with fallback methods
SELECT COUNT(*) FROM buy_sell_daily 
WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
  AND method LIKE '%fallback%';
```

---

## Sign-Off

- **Audit Date**: 2026-05-19
- **Auditor**: Data Integrity Team
- **Next Review**: After Tier 1 fixes implemented
