# Financial Data Integrity Audit — Complete Fake Data & Placeholder Analysis

**Objective**: Identify ALL instances where fake data, placeholders, hardcoded defaults, and fallback values could corrupt financial data integrity.

**Status**: 🔴 CRITICAL — Multiple systematic failures found across dashboard, API, and reconciliation layers.

**Date**: 2026-06-12

---

## EXECUTIVE SUMMARY

The system has **intentional fallback chains** that return **all-zero placeholder values** and **hardcoded defaults** when real data is unavailable. However:

1. ✗ Dashboard does NOT display flags indicating fake data (`_is_placeholder`, `_fallback_reason`)
2. ✗ Users see 0 values identical to real 0 values — no way to distinguish
3. ✗ Calculations use hardcoded initial capital (100k) instead of actual account value
4. ✗ Win streak always shows 0, equity curve always empty (hardcoded placeholders)
5. ✗ Daily reports show fake metrics without warning
6. ✗ Critical alerts won't trigger if metrics default to 0

---

## TIER 1: DASHBOARD FAKE DATA (Visible to Users)

### 1.1 Portfolio Hardcoded Placeholders
**File**: `tools/dashboard/dashboard.py`  
**Lines**: 620-629  
**Severity**: 🔴 CRITICAL

**What's Wrong**:
```python
def fetch_portfolio(c):
    return {
        "snapshot_date": port.get("last_run"),
        "total_portfolio_value": safe_float(port.get("total_portfolio_value")),
        "total_cash": safe_float(port.get("total_cash")),
        "position_count": safe_int(port.get("open_positions")),
        "cumulative_return_pct": None,      # ← HARDCODED NONE
        "max_drawdown_pct": None,            # ← HARDCODED NONE
        "largest_position_pct": None         # ← HARDCODED NONE
    }
```

**Impact**:
- Portfolio panel (line 1426-1475) displays these as "--" (missing)
- User can't see cumulative return for entire portfolio
- User can't see maximum drawdown (critical risk metric)
- User can't see concentration risk (largest position %)
- **These are ALWAYS missing, never populated from data**

**Financial Impact**:
- Portfolio Return tracking is UNAVAILABLE
- Risk management metric (max drawdown) is UNAVAILABLE
- Concentration risk metric is UNAVAILABLE
- User makes decisions based on incomplete picture

---

### 1.2 Performance Hardcoded Zeros
**File**: `tools/dashboard/dashboard.py`  
**Lines**: 646, 654-655, 711

**What's Wrong**:
```python
def fetch_perf(c):
    return {
        "n": safe_int(perf.get("total_trades")),
        "w": safe_int(perf.get("winning_trades")),
        "l": safe_int(perf.get("losing_trades")),
        "wr": safe_float(perf.get("win_rate")),
        "pnl": safe_float(perf.get("total_pnl_dollars")),
        "streak": 0,                        # ← HARDCODED ZERO
        "sharpe": safe_float(perf.get("sharpe_ratio")),
        "maxdd": safe_float(perf.get("max_drawdown_pct", 0)),
        "avg_win": safe_float(perf.get("avg_winning_trade", 0)),
        "avg_loss": safe_float(perf.get("avg_losing_trade", 0)),
        "profit_factor": safe_float(perf.get("profit_factor")),
        "expectancy": safe_float(perf.get("expectancy")),
        "avg_r": 0,                        # ← HARDCODED ZERO
        "equity_vals": [],                 # ← EMPTY PLACEHOLDER
        "recent_rets": []                  # ← EMPTY PLACEHOLDER
    }
```

**Where It's Used**:
```python
# panel_performance_spark (line 1495-1599)
if len(equity_vals) >= 3:
    sp = sparkline(equity_vals, width=28)
    rows.append(Text.from_markup(f"[dim]Equity:[/] {sp}"))
```

**Impact**:
- **Equity curve sparkline NEVER DISPLAYS** (len([]) < 3)
- **Win streak always shows as 0W** even if algo had winning streak
- User can't see portfolio equity progression
- User can't see recent daily returns
- **All hardcoded, never calculated from data**

**Financial Impact**:
- Equity curve tracking is UNAVAILABLE
- Win streak metric is FAKE (always 0)
- Recent performance visualization is MISSING
- User can't see performance trending

---

### 1.3 Economic Indicators Missing
**File**: `tools/dashboard/dashboard.py`  
**Lines**: 754-796 (fetch_economic_pulse)

**What's Wrong**:
```python
def fetch_economic_pulse(c):
    # Still uses direct DB queries (lines 761-794)
    rows = q(c, """SELECT DISTINCT ON (series_id) ...""")  # LINE 761
```

But `q()` is deprecated:
```python
def q(c, sql, p=None):
    """Deprecated: Direct DB queries removed. Use DashboardDataAPI instead."""
    logger.warning(f"DB query called (deprecated): {sql[:50]}...")
    return []  # ← RETURNS EMPTY!
```

**Impact**:
- **Economic data is always empty** (returns [])
- Economic pulse panel shows "no data" even if data exists
- User can't see treasury yields, credit spreads, CPI, unemployment, etc.
- **Migration incomplete** — fetch still calls deprecated function

---

## TIER 2: API FALLBACK FAKE DATA (Returned to Dashboard)

### 2.1 All-Zero Performance Metrics Fallback
**File**: `lambda/api/routes/algo.py`  
**Lines**: 615-642  
**Severity**: 🔴 CRITICAL

**What's Wrong**:
When the performance API endpoint fails, it returns hardcoded all-zero values:

```python
if "_error" in perf:
    logger.error(f"Performance metrics fetch failed: {perf['_error']}")
    log_fallback_usage('performance_metrics', 'hardcoded_defaults', 
                       FallbackTrigger.PRIMARY_UNAVAILABLE, 
                       error=perf.get('_error'))
    
    # Use documented fallback values from fallback_registry
    fallback_values = get_hardcoded_fallback_values('performance_metrics', 'hardcoded_defaults')
    fallback_response = fallback_values.copy() if fallback_values else {}
    
    # Add metadata indicating these are placeholder/fallback values
    fallback_response.update({
        '_is_fallback_data': True,
        '_is_placeholder': True,          # ← FLAG EXISTS
        '_error': perf.get('_error'),
        '_fallback_reason': 'Performance data unavailable - using all-zero placeholder metrics',
        'data_freshness': {
            'is_stale': True,
            'warning': 'Data unavailable',
            'message': 'Unable to fetch performance metrics. Showing placeholder values. Check system logs for details.'
        },
        'confidence_metadata': {
            'sharpe_confidence': 'critical_unavailable',
            'win_rate_confidence': 'critical_unavailable',
            'return_confidence': 'critical_unavailable',
            'snapshot_count': 0,
            'total_trades': 0,
        }
    })
    return json_response(200, fallback_response)
```

**Fallback Values** (from `utils/fallback_registry.py` lines 229-251):
```python
hardcoded_values={
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "breakeven_trades": 0,
    "win_rate_pct": 0.0,
    "profit_factor": 0.0,
    "total_pnl_dollars": 0.0,
    "total_pnl_pct": 0.0,
    "total_return_pct": 0.0,
    "avg_win_pct": 0.0,
    "avg_loss_pct": 0.0,
    "best_trade_pct": 0.0,
    "worst_trade_pct": 0.0,
    "sharpe_ratio": 0.0,
    "sortino_ratio": 0.0,
    "max_drawdown_pct": 0.0,
    "avg_holding_days": 0.0,
    "expectancy_r": 0.0,
    "best_win_streak": 0,
    "worst_loss_streak": 0,
    "current_streak": 0,
}
```

**Impact**:
- **Dashboard returns ALL ZEROS when API unavailable**
- Includes metadata: `'_is_placeholder': True`, `'_fallback_reason': ...`
- But dashboard DOES NOT CHECK these flags!
- User sees all metrics as 0 with no indication it's fake data

---

## TIER 3: RECONCILIATION HARDCODED DEFAULTS

### 3.1 Sharpe Ratio Hardcoded Default
**File**: `algo/algo_daily_reconciliation.py`  
**Lines**: 235-250

**What's Wrong**:
```python
sharpe_ratio = 0.0  # LINE 235 - Hardcoded initial value
cur.execute("""
    SELECT daily_return_pct FROM algo_portfolio_snapshots
    WHERE daily_return_pct IS NOT NULL
    ORDER BY snapshot_date DESC LIMIT 252
""")
returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
if len(returns) > 1:
    import statistics
    try:
        std_dev = statistics.stdev(returns)
        mean_return = statistics.mean(returns)
        sharpe_ratio = (mean_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0.0
    except Exception as e:
        logger.warning(f"Exception: {e}")
        sharpe_ratio = 0.0  # ← Falls back to 0.0 on error
```

**Impact**:
- If `len(returns) <= 1`, sharpe_ratio stays at 0.0
- If calculation fails, sharpe_ratio defaults to 0.0
- Inserted into database as real calculated value, not flagged as default
- User receives fake 0.0 as if it were a calculated Sharpe ratio

**When Does This Happen?**
- First trading day (only 1 snapshot)
- Data gap > 252 days
- Portfolio snapshots table empty

---

### 3.2 Max Drawdown Hardcoded Default
**File**: `algo/algo_daily_reconciliation.py`  
**Lines**: 220-232

**What's Wrong**:
```python
max_drawdown_pct = 0.0  # LINE 220 - Hardcoded initial value
cur.execute("""
    SELECT
        MAX(total_portfolio_value) as peak,
        MIN(total_portfolio_value) as trough
    FROM algo_portfolio_snapshots
""")
peak_row = cur.fetchone()
if peak_row and peak_row[0] and peak_row[1]:
    peak_val = float(peak_row[0])
    trough_val = float(peak_row[1])
    if peak_val > 0:
        max_drawdown_pct = ((peak_val - trough_val) / peak_val) * 100.0
```

**Impact**:
- If no snapshots exist, returns fake 0.0
- If snapshots exist but peak is zero, returns fake 0.0
- Inserted as real calculated value, not marked as default

---

### 3.3 Hardcoded Initial Capital (WRONG CALCULATION)
**File**: `algo/algo_daily_reconciliation.py`  
**Line**: 216

**What's Wrong**:
```python
initial_capital = 100000.0  # ← HARDCODED
cumulative_return_pct = (cumulative_pnl / initial_capital * 100) if initial_capital > 0 else 0.0
```

**Impact**:
- **Cumulative return % is calculated against WRONG base**
- If actual account started with $250k, return is calculated as if it started with $100k
- Return percentage is **2.5x OFF**
- Example:
  - Real: $50k profit on $250k account = 20% return
  - Calculated: $50k / $100k = 50% return
  - **Displays 50% instead of 20%**

**Financial Impact**: CRITICAL
- User sees 2-5x overestimated returns
- User makes decisions based on inflated performance metrics

---

### 3.4 Missing Position Data Defaults
**File**: `algo/algo_daily_reconciliation.py`  
**Lines**: 130-132

**What's Wrong**:
```python
unrealized_pnl = 0.0          # Default if no positions
unrealized_pnl_pct = 0.0      # Default if no positions

for symbol, qty, entry, current, pos_value in positions:
    # ... calculations ...

# If positions list is empty, metrics stay at 0.0
```

**Impact**:
- Indistinguishable between "no positions" and "all positions break-even"
- Daily report shows 0% unrealized P&L without indicating missing positions

---

## TIER 4: DAILY REPORT FAKE METRICS

### 4.1 Daily P&L Defaults to Zero
**File**: `algo/algo_daily_report.py`  
**Lines**: 263-265

**What's Wrong**:
```python
dpnl = portfolio.get('daily_pnl_pct')
if dpnl is None:
    dpnl = 0  # ← HARDCODED, then printed as real value
    
# Then printed (line 287):
f"Daily P&L: {dpnl:+.2f}%"
# Output: "Daily P&L: +0.00%" (looks like real zero, not missing data)
```

**Impact**:
- User can't distinguish between "zero P&L" and "missing data"
- No warning that metric is unavailable
- Printed in financial report as if calculated

---

### 4.2 Sharpe Ratio Defaults to Zero
**File**: `algo/algo_daily_report.py`  
**Lines**: 275-277

**What's Wrong**:
```python
sharpe = risk.get('sharpe_ytd')
if sharpe is None:
    sharpe = 0  # ← HARDCODED
    
# Then printed (line 291):
f"Sharpe {sharpe:.1f}"
# Output: "Sharpe 0.0" (looks real, not missing)
```

---

### 4.3 VaR, Beta, Expectancy All Default to Zero
**File**: `algo/algo_daily_report.py`  
**Lines**: 269-280

```python
var95 = risk.get('var_95_pct')
if var95 is None:
    var95 = 0  # ← FAKE
    
beta = risk.get('beta')
if beta is None:
    beta = 0  # ← FAKE
    
exp_r = strategy.get('expectancy_r')
if exp_r is None:
    exp_r = 0  # ← FAKE
```

**All then printed without any indication they're defaults.**

---

## TIER 5: SILENT DATA LOSS (CASCADING FAILURES)

### 5.1 Missing Daily P&L Won't Trigger Loss Alert
**File**: `algo/algo_daily_report.py`  
**Lines**: 336-340

**What's Wrong**:
```python
daily_pnl = portfolio.get('daily_pnl_pct')
if daily_pnl is None:
    daily_pnl = 0  # ← HARDCODED

# Later in _check_thresholds():
if daily_pnl < -2.0:
    warnings.append(f"⚠️  Daily loss > 2% ({daily_pnl:.1f}%) - Halt entries?")
```

**Impact**:
- If daily_pnl is actually -3.5% but data missing, it defaults to 0
- Condition `if 0 < -2.0:` is FALSE
- **ALERT NEVER FIRES**
- User receives NO WARNING to halt entries during down days
- **Potential for cascading losses**

---

### 5.2 Missing Market Data Fallback (Undocumented)
**File**: `algo/algo_data_patrol.py`  
**Line**: 69

**What's Wrong**:
```python
"""Reads from database first, falls back to hardcoded defaults if not configured.
"""
```

**Problem**: No documentation of what those defaults are.
- Code mentions fallback to hardcoded defaults
- Nowhere documents WHAT defaults are hardcoded
- No validation of default values

---

## TIER 6: DETECTION GAPS (Dashboard Ignores Metadata)

### 6.1 Dashboard Doesn't Check Placeholder Flags
The API returns metadata flags, but dashboard IGNORES them:

```python
# API returns:
{
    '_is_placeholder': True,
    '_is_fallback_data': True,
    '_fallback_reason': 'Performance data unavailable...',
    'confidence_metadata': {
        'sharpe_confidence': 'critical_unavailable',
        'win_rate_confidence': 'critical_unavailable',
    }
}

# Dashboard does NOT check any of these flags
# Just uses the values as if they're real
```

**What's Missing**:
1. ✗ No check for `_is_placeholder`
2. ✗ No check for `_is_fallback_data`
3. ✗ No check for `_fallback_reason`
4. ✗ No check for `confidence_metadata` states
5. ✗ No visual indicator of "data unavailable"
6. ✗ Zero values displayed identically to real zeros

---

## SYSTEMATIC ISSUES

### Issue A: No Distinction Between "Zero" and "Missing"
```python
# These are indistinguishable in UI:
sharpe = 0.0    # Real: strategy has zero sharpe ratio (broken)
sharpe = 0.0    # Fake: metric unavailable, defaulted to zero
```

**User can't tell which is which.**

---

### Issue B: Cascade of Defaults
```
Data missing from source
    ↓
Returns None/empty
    ↓
Defaults to 0 (often silent)
    ↓
Stored/displayed as real 0
    ↓
Used in downstream calculations (wrong)
    ↓
User makes decisions on fake data
```

---

### Issue C: No Validation of Initial Capital
- Hardcoded 100k assumed
- If account started with 250k, all returns are inflated 2.5x
- No validation against actual Alpaca account history

---

## SUMMARY TABLE

| Component | Fake Data | Type | Impact |
|-----------|-----------|------|--------|
| Portfolio cumulative return | None | Hardcoded | Missing critical metric |
| Portfolio max drawdown | None | Hardcoded | Missing risk metric |
| Portfolio largest position % | None | Hardcoded | Missing concentration metric |
| Win streak | 0 | Hardcoded | Always shows false 0 |
| Equity curve | [] | Hardcoded empty | Visualization never shows |
| Recent returns | [] | Hardcoded empty | Visualization missing |
| Economic indicators | [] | Deprecated query | Always missing |
| Sharpe ratio | 0.0 | Conditional default | Returns fake when calc fails |
| Max drawdown | 0.0 | Conditional default | Returns fake when no data |
| Daily P&L | 0 | Silent default | No alert on missing value |
| Sharpe (report) | 0 | Silent default | Printed as real |
| VaR | 0 | Silent default | Printed as real |
| Beta | 0 | Silent default | Printed as real |
| Cumulative return % | Wrong | Hardcoded capital | Inflated 2.5x off |

---

## CRITICAL FINDINGS

**🔴 CRITICAL**: Multiple systematic failures that return fake data to users:
1. Dashboard hardcodes all-zero placeholders for key metrics
2. API returns placeholder data with metadata flags dashboard ignores
3. Reconciliation uses hardcoded defaults without validation
4. Daily reports show fake metrics without warning
5. Hardcoded initial capital causes 2.5x return calculation errors
6. Silent alerts failures when metrics default to 0
7. No distinction between "zero value" and "missing data"

**Financial Data Integrity**: COMPROMISED

---

## NEXT STEPS FOR DISCUSSION

1. Should we REMOVE all hardcoded defaults and fail-fast instead?
2. Should dashboard display metadata flags when fake data is used?
3. Should we calculate metrics in real-time instead of storing defaults?
4. Should we validate initial capital against Alpaca history?
5. Should daily reports refuse to generate if key metrics missing?
6. Should we add explicit "Data Unavailable" UI state?
7. Should we log CRITICAL severity whenever placeholders are used?
8. Should we fail-fast if initial capital doesn't match account history?
