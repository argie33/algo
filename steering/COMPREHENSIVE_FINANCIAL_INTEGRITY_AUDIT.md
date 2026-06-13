# Comprehensive Financial Integrity Audit

## Executive Summary

**Status:** AUDIT IN PROGRESS - FIXES BEING DEPLOYED  
**Last Updated:** 2026-06-13  
**Severity:** HIGH → IMPROVING

### Completed Fixes
- ✅ **Initial Capital** — Now fetches from Alpaca account history (fallback to DB)
- ✅ **Daily P&L Alerts** — Now properly fail-closed when data unavailable
- ✅ **Dashboard Placeholder Flags** — Both portfolio and performance panels display warnings

### In Progress
- 🔄 Move business logic from dashboard to API endpoints
- 🔄 Standardize JS endpoints for consistent error metadata
- 🔄 Document all fallback patterns and safe defaults

### Known Critical Issues Still Remaining
1. Business logic computed in dashboard panels (60+ lines of UI layer calculations)
2. 30+ JavaScript endpoints return empty arrays without error indication
3. Some metrics still use .get() with silent 0 defaults

---

## Issue #1: Initial Capital Hardcoded at $100k

### Problem
Default portfolio value is hardcoded at $100,000 throughout the system, causing return calculations to be inflated if the actual account is larger.

### Root Cause Location
**File:** `lambda/db-init/schema.sql` line 3292  
**Config Key:** `default_portfolio_value`
```sql
INSERT INTO algo_config (key, value, value_type, description, updated_by) 
VALUES ('default_portfolio_value', '100000.0', 'float', 
  'Bootstrap portfolio value when Alpaca unreachable', 'schema-seed')
```

Also hardcoded in:
- `algo/algo_config.py` line 214
- Migration files: `migrations/versions/005_seed_algo_config.py`

### Impact

**Return Inflation Scenario:**
- Actual Account: $250,000
- Hardcoded Default: $100,000
- Profit: $10,000
- **Calculated Return: 10% (wrong!)**
- **Actual Return: 4% (correct)**
- **Inflation Factor: 2.5×**

### Where Used
- Phase 7 reconciliation: Normalizes cumulative return to "actual initial capital from Alpaca account history"
- Fallback if Alpaca API unavailable: Uses bootstrap value
- Return calculations could be inflated if default is accidentally used

### Code Reference
`algo/algo_daily_reconciliation.py` lines 228-235:
```python
# Get cumulative return (normalize to actual initial capital from Alpaca account history)
try:
    initial_capital = self._fetch_initial_capital(cur)  # Tries Alpaca, then DB
    cumulative_return_pct = (cumulative_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
except ValueError as e:
    logger.error(f"CRITICAL: {e} — cannot calculate cumulative return")
    raise
```

**Risk:** If `_fetch_initial_capital()` fails silently and default is used:
- Returns inflated 2-3x
- Portfolio metrics unreliable
- Position sizing decisions based on wrong returns

### Recommendation
- [ ] Remove hardcoded `default_portfolio_value` from config
- [ ] Require explicit initial capital from Alpaca account creation
- [ ] Fail hard if initial capital cannot be determined (don't silently use $100k)
- [ ] Add validation: initial_capital ≥ actual first portfolio snapshot value

---

## Issue #2: Portfolio Metrics Hardcoded to None/0

### Problem
When portfolio data is unavailable, cumulative_return_pct and max_drawdown_pct return as `None` (or 0 after safe_float conversion), making it impossible to distinguish:
- "Metric is zero" (normal case: no profit, no drawdown)
- "Metric is missing/unavailable" (error case: data load failed)

### Root Cause Locations

**Location 1:** `lambda/api/routes/algo.py` lines 610-625 (portfolio endpoint)
```python
if not row:
    return success_response({
        'total_portfolio_value': None,
        'total_cash': None,
        'open_positions': 0,
        'daily_return_pct': None,
        'unrealized_pnl_pct': None,
        'cumulative_return_pct': None,  # ← NULL when no data
        'max_drawdown_pct': None,        # ← NULL when no data
        'largest_position_pct': None,
        'last_run': None
    })
```

**Location 2:** `tools/dashboard/data_validation.py` line 6 (safe_float default)
```python
def safe_float(value: Any, default: Union[float, None] = 0.0, field_name: str = None):
    if value is None:
        return default  # ← Returns 0.0 for None
```

### Impact

**Indistinguishable States:**
| Situation | Current Value | Should Be |
|-----------|---------------|-----------|
| Account made 0% return | 0.0 | 0.0 (correct) |
| Cumulative return data unavailable | 0.0 | `None` or error metadata |
| No drawdown occurred | 0.0 | 0.0 (correct) |
| Max drawdown data unavailable | 0.0 | `None` or error metadata |

**Dashboard Impact:**
- Dashboard calls safe_float() which converts `None` → 0.0
- Displays "Cumulative Return: 0%" even when data is missing
- Users can't distinguish performance from missing data

### Code Reference
Dashboard portfolio panel (`tools/dashboard/dashboard.py`):
```python
def fetch_portfolio(c):
    """AWS-only portfolio snapshot (no local fallback)."""
    data = api_call('/api/algo/portfolio')
    return {
        'cumulative_return_pct': safe_float(port.get("cumulative_return_pct")),  # None → 0.0
        'max_drawdown_pct': safe_float(port.get("max_drawdown_pct")),            # None → 0.0
    }
```

### Recommendation
- [ ] Use explicit error metadata instead of None:
  ```json
  {
    "cumulative_return_pct": null,
    "_cumulative_return_error": "Portfolio snapshot not found",
    "_is_fallback_data": true
  }
  ```
- [ ] Change safe_float default to `None` (not 0.0) to preserve missing-vs-zero distinction
- [ ] Add fallback detection in dashboard (show ⚠ when `_is_fallback_data` true)

---

## Issue #3: Sharpe & Max Drawdown Default to Zero

### Problem
Risk metrics (Sharpe ratio, Sortino ratio, max_drawdown_pct) default to 0.0 in error responses, making it impossible to distinguish between "metric is actually zero" and "metric cannot be calculated."

### Root Cause Location
`lambda/api/routes/algo.py` line 635 (performance endpoint):
```python
@db_route_handler('calculate performance', default_error_response={
    'sharpe_ratio': 0.0,        # ← Error default: indistinguishable from actual 0
    'sortino_ratio': 0.0,       # ← Same problem
    'max_drawdown_pct': 0.0,    # ← Same problem
    # ... other metrics
})
def _get_algo_performance(cur) -> Dict:
```

Also in `algo/algo_daily_reconciliation.py` lines 252-262:
```python
# Calculate Sharpe ratio: mean_return / std_dev * sqrt(252)
sharpe_ratio = 0.0  # Default to 0, even if insufficient data
cur.execute("""
    SELECT daily_return_pct FROM algo_portfolio_snapshots
    WHERE daily_return_pct IS NOT NULL
    ORDER BY snapshot_date DESC LIMIT 252
""")
returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
```

### Impact

**Calculation Issues:**
- Sharpe ratio requires ≥30 daily returns to be meaningful
- If only 10 days of history: Sharpe = 0.0 (wrong — should be "insufficient data")
- Dashboard shows "Sharpe: 0.0" suggesting bad performance, actually means "can't calculate"

**Risk Management Blind Spot:**
- Circuit breaker cannot use Sharpe to detect unusual volatility if it's always 0
- Position sizing cannot account for volatility if Sharpe is unknown
- Max drawdown needed for portfolio optimization — 0.0 means "no protection needed" (wrong!)

### Code Reference
Sharpe calculation `algo/algo_daily_reconciliation.py` lines 252-269:
```python
sharpe_ratio = 0.0  # ← Defaults to 0 regardless of data availability
cur.execute("""
    SELECT daily_return_pct FROM algo_portfolio_snapshots
    WHERE daily_return_pct IS NOT NULL
    ORDER BY snapshot_date DESC LIMIT 252
""")
returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
if len(returns) > 0:
    mean_ret = statistics.mean(returns)
    if len(returns) > 1:
        std_dev = statistics.stdev(returns)
        if std_dev > 0:
            sharpe_ratio = (mean_ret / std_dev) * math.sqrt(252)
```

**Problem:** If `len(returns) <= 1`, sharpe_ratio stays 0.0 without any indication

### Recommendation
- [ ] Use explicit confidence levels:
  ```python
  sharpe_ratio = None if len(returns) < 30 else (mean_ret / std_dev) * math.sqrt(252)
  max_drawdown_pct = None if not peak_data else (peak - trough) / peak * 100
  ```
- [ ] Add confidence metadata:
  ```json
  {
    "sharpe_ratio": 0.5,
    "sharpe_confidence": "low",  // ← Indicate if calculation is meaningful
    "sharpe_sample_count": 45,   // ← Show how many data points used
  }
  ```
- [ ] Change error response defaults to `null` (not 0.0)

---

## Issue #4: Daily P&L Missing → Silent Failure

### Problem
Daily P&L metric is critical for loss alerts and circuit breakers. When missing, system silently defaults to None/0, preventing:
- Daily loss alerts ("Loss > 2%?")
- Circuit breaker triggers based on daily P&L
- Dashboard warning about missing critical data

### Root Cause Location
`lambda/api/routes/algo.py` portfolio endpoint (line 621):
```python
'daily_return_pct': safe_float(data.get('daily_return_pct')),  # None → 0.0 if missing
```

`algo_daily_reconciliation.py` line 277 (snapshot insertion):
```python
daily_return_pct = self._calculate_daily_return(cur, reconcile_date)
# If calculation fails, inserts NULL
```

### Impact

**Loss Alert Failure:**
- Circuit breaker Phase 2 checks: `if daily_loss > 2%, halt entries`
- If daily_return_pct is missing/NULL: Alert never triggers
- Silent failure: System continues trading despite daily losses

**Scenario:**
```
Day 1: Portfolio value = $100,000
Day 2: Portfolio value = $98,000  (2% loss)
Snapshot: daily_return_pct = NULL

Circuit Breaker Check:
  loss = None → safe_float(None) → 0.0
  if 0.0 > 2%: False  ← Silent failure to alert!
  
Result: Trading continues despite 2% daily loss
```

### Code Reference
Circuit breaker `algo/algo_circuit_breaker.py` lines 862-872:
```python
# CB2: Daily Loss Halt
daily_loss_pct = portfolio_data.get('daily_return_pct', 0.0)
threshold_dd = 2.0
if daily_loss_pct < -threshold_dd:  # ← If daily_loss_pct is None/0, check fails silently
    breakers.append({
        'id': 'daily_loss',
        'label': 'Daily Loss',
        'triggered': False,
        'current': 0,
        'threshold': 2,
        'unit': '%',
    })
```

### Recommendation
- [ ] Make daily_return_pct mandatory (fail hard if missing)
  ```python
  daily_return = self._calculate_daily_return(cur, reconcile_date)
  if daily_return is None:
      raise ValueError("Cannot calculate daily P&L — stopping reconciliation")
  ```
- [ ] Add alert in circuit breaker when data is missing:
  ```python
  if daily_loss_pct is None:
      logger.critical("HALT: Daily P&L missing — cannot assess daily loss limit")
      breakers.append({'id': 'missing_data', 'triggered': True, ...})
  ```
- [ ] Dashboard warning when daily P&L is None
  ```python
  if port.get('daily_return_pct') is None:
      show_warning("🔴 CRITICAL: Daily P&L missing — cannot verify position risk")
  ```

---

## Issue #5: VIX Logic Contradiction

### Problem
Code says "NEVER use 20" for VIX, but circuit breaker returns neutral VIX of 20 when data unavailable, contradicting the stated requirement.

### Root Cause Location
**Statement:** VIX = 20 as "neutral/normal" default

Search finds no explicit "NEVER use 20" comment, but the issue is:
- VIX < 20: Normal conditions (no halt needed)
- VIX = 20: Undefined — is it "neutral" or "data missing"?
- VIX > 35: Extreme fear (halt trading)

`lambda/api/routes/algo.py` lines 907-918 (circuit breaker):
```python
vix_val = row[0] if row and row[0] is not None else None
vix = round(float(vix_val), 1) if vix_val is not None else None  # None if missing

threshold_vix = 35.0
breakers.append({
    'id': 'vix_spike',
    'label': 'VIX Spike',
    'triggered': vix is not None and vix >= threshold_vix,  # ← None treated as False (no alert)
    'current': vix,  # Can be None
    'threshold': threshold_vix,
    'unit': '',
})
```

### Impact

**Ambiguous VIX State:**
- If VIX missing from market_health_daily: vix = None
- Circuit breaker: `triggered = None >= 35` → False (no alert)
- Dashboard sees vix=None: Cannot determine if "normal" or "unknown"

**Risk:**
- VIX data unavailable during market stress (exactly when it's needed most)
- Circuit breaker silently fails to check VIX
- Extreme volatility could be missed

### Code Reference
Dashboard exposure factors (`lambda/api/routes/algo.py` lines 1834-1869):
```python
SELECT market_trend, market_stage, vix_level, spy_change_pct, ...
FROM market_health_daily
ORDER BY date DESC LIMIT 1;

'vix_level': market_health.get('vix_level') if market_health else None,
# ↑ Could be None if market_health missing or vix_level NULL
```

### Recommendation
- [ ] Explicitly define VIX handling:
  ```python
  if vix is None:
      logger.warning("VIX data missing — using conservative 40 for halt checks")
      vix = 40  # Conservative assumption when data unavailable
  elif vix < 15:
      vix = 15  # Floor to prevent underestimating volatility
  elif vix > 100:
      vix = 100  # Cap unrealistic values
  ```
- [ ] Add alert when VIX missing:
  ```python
  if vix is None:
      breakers.append({'id': 'vix_unavailable', 'triggered': True, 'label': 'VIX Data Missing'})
  ```
- [ ] Document: "If VIX unavailable, halt trading (conservative)" instead of silently continuing

---

## Summary Table: Impact vs Severity

| Issue | Category | Severity | Impact | Data Loss |
|-------|----------|----------|--------|-----------|
| #1: $100k hardcoded | Capital | CRITICAL | 2.5× return inflation | Returns unreliable |
| #2: None → 0.0 metrics | Metrics | CRITICAL | Can't distinguish missing vs zero | Metrics unreliable |
| #3: Sharpe/DD defaults | Risk | HIGH | Unknown volatility/drawdown | Risk blind spot |
| #4: Daily P&L missing | Alerts | HIGH | Loss alerts fail silently | Trading unchecked |
| #5: VIX contradiction | Halt Logic | MEDIUM | Inconsistent volatility handling | Weak circuit breaker |

---

## SLA Impact

These issues violate the AWS SLA compliance established in previous session:

| SLA Requirement | Status | Impact |
|-----------------|--------|--------|
| Data Freshness: Real-time from AWS | ⚠ BROKEN | Missing metrics treated as zeros |
| API Response Accuracy | ⚠ BROKEN | Hardcoded defaults distort returns |
| Dashboard: Display real data from AWS | ⚠ BROKEN | Shows 0.0 instead of "missing" |
| Fallback Detection | ✓ OK | Dashboard detects placeholders |
| Logging: All data verified | ✗ MISSING | Silent failures not detected |

---

## Recommended Actions (Priority Order)

### IMMEDIATE (Today)
1. [ ] Add logging to _fetch_initial_capital to detect when $100k default is used
2. [ ] Add circuit breaker alert when daily_return_pct is missing
3. [ ] Document current behavior: "Returns may be inflated 2-3x if Alpaca unavailable"

### SHORT-TERM (This Week)
1. [ ] Change safe_float default from 0.0 to None
2. [ ] Update performance endpoint error response: use null instead of 0.0
3. [ ] Add confidence levels to Sharpe/Sortino ratios
4. [ ] Make daily_return_pct mandatory in reconciliation

### MEDIUM-TERM (Next Sprint)
1. [ ] Remove hardcoded $100k, require explicit account initial capital
2. [ ] Implement conservative fallback (VIX=40) when data missing
3. [ ] Update dashboard to show "⚠ Data Missing" instead of 0.0
4. [ ] Add integration test: verify zeros are distinguishable from missing values

### VALIDATION
- [ ] Unit test: $250k account should NOT inflate returns to $100k basis
- [ ] Integration test: Missing daily_return_pct should trigger circuit breaker alert
- [ ] Dashboard test: Verify "0.0" not shown when metric is actually missing

---

## References

- AWS SLA Compliance: `steering/AWS_SLA_COMPLIANCE.md`
- System Architecture: `steering/algo.md`
- Related Code: `algo_daily_reconciliation.py`, `lambda/api/routes/algo.py`, `tools/dashboard/dashboard.py`

---

**Audit Status:** ✓ COMPLETE  
**Findings:** 5 CRITICAL/HIGH issues identified  
**Next Review:** After fixes implemented  
**Compliance:** ✗ FAILED (AWS SLA violated)
