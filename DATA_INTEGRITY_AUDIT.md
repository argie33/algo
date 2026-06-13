# Data Integrity Audit - Complete Findings

Goal: Find all fake fallbacks, placeholder values, mock data, and anything that could impact financial data integrity.

---

## CRITICAL ISSUES (Highest Risk)

### 1. DEFAULT PORTFOLIO VALUE ($100,000 Bootstrap)
**Severity:** HIGH  
**Files:** 
- `algo/algo_config.py:214` (DEFAULTS config)
- `algo/algo_position_sizer.py:75` (get_portfolio_value())
- `algo/algo_trade_executor.py:1060` (_get_portfolio_value())

**What:** When Alpaca API is unreachable AND no recent portfolio snapshot exists, the system falls back to a hardcoded default of $100,000.

**Current Code:**
```python
# algo_position_sizer.py:75
default_pv = float(self.config.get('default_portfolio_value', 100000.0))
logger.warning(
    f"[BOOTSTRAP] Portfolio value unavailable (Alpaca unreachable, no recent snapshot). "
    f"Using default ${default_pv:,.0f}. Positions will be sized conservatively. "
    "Phase 7 reconciliation will create a real snapshot after this run."
)
return default_pv
```

**Impact:**
- ALL position sizing is based on this value if Alpaca is down
- Risk calculations scale with this fallback portfolio value
- Does not distinguish between paper ($100k) and live accounts (can be millions)
- Acts as placeholder when real account data unavailable

**When It Happens:**
1. Alpaca API credentials missing/expired
2. Alpaca API unavailable (network/service down)
3. No portfolio snapshot in database yet (first run scenario)

---

### 2. VIX FALLBACK TO NEUTRAL VALUE (20)
**Severity:** HIGH  
**Files:**
- `algo/algo_circuit_breaker.py:446` (insufficient SPY data)
- `algo/algo_circuit_breaker.py:465` (return 20.0)
- `algo/algo_circuit_breaker.py:468` (exception handling)

**What:** When actual VIX data is unavailable, system computes "implied VIX" from SPY price volatility. If that also fails, defaults to neutral 20.

**Current Code:**
```python
def _compute_vix_fallback(self, current_date: Any, cur) -> float:
    """Compute implied volatility from SPY price changes when VIX missing.
    Uses 20-day rolling standard deviation of SPY returns as approximation
    (correlation with VIX: ~0.80-0.85). Falls back to 20 (neutral) if insufficient data.
    """
    try:
        # ... compute implied_vix from SPY ...
        if len(prices) < 5:
            logger.warning(f"VIX fallback: insufficient SPY data ({len(prices)} days), using neutral 20")
            return 20.0  # <-- PLACEHOLDER VALUE
        # ...
    except Exception as e:
        logger.warning(f"VIX fallback computation failed: {e}, using neutral 20")
        return 20.0  # <-- PLACEHOLDER VALUE
```

**Impact:**
- Circuit breaker CB5 uses this to check volatility spike risk
- Neutral 20 masks actual market risk when VIX missing
- VIX spike detector (>35) won't fire if using fallback 20
- Code explicitly says "Never use neutral default (20)" (line 407) but then returns 20 anyway

**When It Happens:**
1. VIX market data missing from database
2. SPY price data insufficient (<5 days) for volatility computation
3. Exception during fallback computation (network/DB error)

---

### 3. ESTIMATED EXIT PRICES (Phase 4 → Phase 7 Reconciliation)
**Severity:** MEDIUM-HIGH  
**Files:**
- `algo/algo_daily_reconciliation.py:331` (reconcile_exit_fills docstring)
- `algo/algo_trade_executor.py` (Phase 4 exit placement)
- `algo/algo_daily_reconciliation.py:329-332` (explanation)

**What:** Phase 4 places market exit orders BEFORE market open using "last known market price". These estimated prices are reconciled against actual Alpaca fill prices AFTER market opens in Phase 7.

**Current Code Comment:**
```python
"""
Phase 4 marks trades 'closed' immediately using the last known market price
when placing market exit orders before market open. This reconciles those
estimated prices with actual Alpaca fill prices after market opens.
"""
```

**Impact:**
- Exit prices in algo_trades table may be estimated, not actual fills
- Profit/loss calculations based on estimated price until Phase 7 runs
- If Phase 7 doesn't run or fails, estimated prices become permanent

---

## SERIOUS ISSUES (Medium-High Risk)

### 4. REAL-TIME PRICE FALLBACKS
**Severity:** MEDIUM-HIGH  
**Files:**
- `algo/algo_realtime_prices.py:64-118` (get_latest_prices())
- `algo/algo_realtime_prices.py:214-241` (_get_fallback_prices())
- `algo/algo_position_monitor.py` (tracks `price_is_fallback` metadata)

**What:** Real-time pricing attempts in order:
1. Alpaca Data API (real-time)
2. IEX Cloud (mid-market, ~100ms latency)
3. YFinance (delayed ~15 min)
4. Database daily prices (delayed 24h+ if outside market hours)

**Current Code:**
```python
def _get_fallback_prices(self, symbols: List[str]) -> Dict[str, float]:
    """Fallback: use cached or daily prices from database."""
    try:
        prices = {}
        with DatabaseContext('read') as cur:
            current_date = _date.today()
            for symbol in symbols:
                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT 1
                """, (symbol, current_date))
                row = cur.fetchone()
                if row and row[0]:
                    prices[symbol] = float(row[0])
        return prices
    except Exception as e:
        logger.error(f"Failed to fetch fallback prices from database: {e}")
        return {}  # <-- EMPTY DICT
```

**Impact:**
- Position sizing uses fallback prices when real-time unavailable
- 24h+ stale prices used for intraday sizing (gaps missed)
- Empty dict returned if database fails (no price at all)
- F-01 (intraday position sizing) depends on fresh prices

---

### 5. VIX APPROXIMATION (Implied VIX from SPY)
**Severity:** MEDIUM  
**Files:**
- `algo/algo_circuit_breaker.py:425-468` (_compute_vix_fallback())

**What:** When actual VIX unavailable, system computes implied volatility from 20-day SPY price standard deviation.

**Formula:**
```python
implied_vix = std_dev(SPY_returns) * sqrt(252) * 100
# Clamps to [5.0, 80.0]
```

**Issues:**
- Correlation with real VIX: ~0.80-0.85 (not perfect)
- SPY volatility ≠ market volatility (SPY is large-cap, misses small-cap stress)
- Approximation, not actual market volatility indicator
- Can significantly over/under-estimate risk

---

## MEDIUM SEVERITY ISSUES

### 6. EMPTY DICT/NONE RETURNS ON DATA FETCH FAILURES
**Severity:** MEDIUM  
**Files (examples):**
- `algo/algo_daily_report.py:69, 95, 110` (multiple return {})
- `algo/algo_exit_engine.py:205, 385, 401` (multiple return None)
- `algo/algo_position_monitor.py:46` (return None on DB failure)

**What:** Functions return empty dict `{}` or `None` when data fetch fails, allowing calling code to proceed without prices/values.

**Example:**
```python
def _with_cursor(self, operation, mode='read'):
    """Execute operation with cursor via DatabaseContext."""
    try:
        with DatabaseContext(mode) as cur:
            return operation(cur)
    except Exception as e:
        logger.debug(f"Database operation failed: {e}")
        return None  # <-- RETURNS NONE
```

**Impact:**
- Calling code must handle None/empty dict or crash
- Risk calculations with missing data inputs
- Silent failures if error handling incomplete

---

### 7. PORTFOLIO SNAPSHOT AGE TOLERANCE
**Severity:** MEDIUM  
**Files:**
- `algo/algo_position_sizer.py:63-68` (allow 2-day old snapshot)

**What:** Portfolio snapshot used for position sizing if ≤ 2 days old. After 2 days, falls back to default.

**Current Code:**
```python
if age_days <= 2:
    return snapshot_value
logger.warning(
    f"Portfolio snapshot is {age_days} days old — falling back to default. "
    "Ensure Phase 7 runs to refresh the snapshot."
)
```

**Impact:**
- 2-day stale portfolio value used for sizing
- Doesn't account for market moves (10%+ gaps possible)
- If Phase 7 doesn't run for days, falls back to default

---

### 8. MARKET DATA FRESHNESS CHECKS (Hardcoded Staleness)
**Severity:** MEDIUM  
**Files:**
- `algo/algo_circuit_breaker.py:490-495` (market_stage data staleness)

**What:** Various circuit breaker checks use hardcoded staleness thresholds (1-3 days).

**Current Code Comment:**
```python
# Hardcoded calendar-day thresholds cause false halts after 3-day holiday weekends when
# the market_health_daily record is from Friday but current_date is Tuesday (4 days gap).
```

**Impact:**
- False circuit breaker halts after market holidays
- Staleness check doesn't account for trading calendar
- Fixed partially but still risky

---

## LOW-MEDIUM SEVERITY ISSUES

### 9. MISSING DATA → EMPTY/DEFAULT RETURNS
**Severity:** LOW-MEDIUM  
**Files:**
- `algo/signals/signal_trend.py:31, 38` (return score 0 on insufficient history)
- `algo/algo_advanced_filters.py:471` (return 0.0 on missing data)

**What:** Signal scoring returns 0 when data insufficient, which can mean "no signal" or "passed all checks" depending on context.

---

### 10. SAFE CONVERSION DEFAULTS
**Severity:** LOW-MEDIUM  
**Files:**
- `algo/algo_performance.py:28-35` (safe_float() with default=0.0)
- `algo/algo_circuit_breaker.py:38-50` (_safe_float() with default=0.0)

**What:** Float conversion functions return 0.0 as default when conversion fails.

**Issue:** Using 0.0 for missing portfolio value vs missing P&L return is context-dependent.

---

## SUMMARY TABLE

| Issue | Severity | Category | Files | Impact | When |
|-------|----------|----------|-------|--------|------|
| Default Portfolio $100k | HIGH | Fallback | position_sizer.py, trade_executor.py | Wrong position sizing if Alpaca down | Alpaca unreachable + no snapshot |
| VIX Fallback to 20 | HIGH | Placeholder | circuit_breaker.py | Masks volatility risk | VIX data missing |
| Estimated Exit Prices | MEDIUM-HIGH | Estimated | daily_reconciliation.py | Temporary until Phase 7 | Phase 4 exits before market open |
| Price Fallbacks (24h) | MEDIUM-HIGH | Fallback | realtime_prices.py | Stale prices in intraday sizing | Real-time sources fail |
| Implied VIX (SPY approx) | MEDIUM | Approximation | circuit_breaker.py | 0.80-0.85 correlation | VIX unavailable |
| Empty Dict Returns | MEDIUM | Silent Failure | multiple | Missing data continues | DB/API failures |
| Snapshot Age Tolerance | MEDIUM | Staleness | position_sizer.py | 2-day old portfolio value | No Phase 7 runs |
| Holiday Staleness Checks | MEDIUM | Hardcoded | circuit_breaker.py | False halts after holidays | Market holidays |
| Missing Data → Score 0 | LOW-MEDIUM | Ambiguous | signals/* | Unclear if passed/failed | Insufficient data |
| Safe Defaults (0.0) | LOW-MEDIUM | Type Conversion | performance.py | Context-dependent | Data conversion failure |

---

## RECOMMENDATIONS FOR DISCUSSION

1. **Immediate**: Audit all uses of `default_portfolio_value` — should this fallback exist at all?
2. **Immediate**: Review VIX fallback logic — explicit code says "Never use neutral 20" but does anyway
3. **Important**: Clarify Phase 7 reconciliation timing — estimated prices must be reconciled same day
4. **Important**: Add circuit breaker for portfolio value fetches — should halt if no valid value available
5. **Important**: Document when fallback prices are used and mark positions accordingly
6. **Review**: All empty dict/None returns in critical paths — should they fail closed instead?
7. **Review**: Portfolio snapshot age (2 days) — too old for live trading?

