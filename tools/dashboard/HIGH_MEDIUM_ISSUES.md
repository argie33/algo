# High & Medium Severity Issues — Focused List

**Date:** 2026-06-11  
**Scope:** Tier 2 (HIGH) + Tier 3 (MEDIUM) issues only  
**Count:** 37 total issues  
**Time to Fix:** 5-7 hours  
**Priority:** After TIER 1 critical fixes are complete

---

## TIER 2: HIGH SEVERITY (17 issues)

### Issue H1: Port Hardcoded to 5432

**Location:** Line 242  
**Severity:** 🟠 HIGH  
**Problem:** Database port hardcoded to 5432, not configurable  
**Impact:** Fails silently if DB on different port (5433, 5434, etc.)  
**Current Code:**
```python
# If port missing, defaults to 5432
port = int(os.environ.get("DB_PORT", 5432))
```
**Fix Required:**
- Read port from environment variable
- Validate port is valid number (1-65535)
- Fail fast if port missing

**Status:** ❌ NOT FIXED

---

### Issue H2: No Test Connection Validation

**Location:** Lines 246-317 (in credential validation function)  
**Severity:** 🟠 HIGH  
**Problem:** Credentials validated for format only, not actual connectivity  
**Impact:** Operator gets "credentials loaded" but actual DB connection fails  
**Current Code:**
```python
# Only checks if env vars exist
if all([env_creds["host"], env_creds["user"], env_creds["password"]]):
    return env_creds
# Never tests if connection actually works
```
**Fix Required:**
- Add `test_connection()` call after credentials loaded
- Try dummy query: `SELECT 1`
- Fail with specific error if connection fails

**Status:** ❌ NOT FIXED

---

### Issue H3: VIX Comparison Uses 0 for None (Location 1)

**Location:** Line 3151  
**Severity:** 🟠 HIGH  
**Problem:** `(mkt.get("vix") or 0) >= 30` shows GREEN when vix=None  
**Impact:** Operator thinks market is calm when VIX data is actually missing  
**Current Code:**
```python
vc = R if (mkt.get("vix") or 0) >= 30 else (Y if (mkt.get("vix") or 0) >= 20 else G)
# If vix = None: becomes (None or 0) >= 30 → 0 >= 30 → False → G (GREEN)
# Should be Y (YELLOW) for unknown
```
**Fix Required:**
```python
vix = mkt.get("vix")
if vix is None:
    vc = Y  # Yellow for unknown
else:
    vc = R if vix >= 30 else (Y if vix >= 20 else G)
```

**Status:** ❌ NOT FIXED

---

### Issue H4: VIX Comparison Uses 0 for None (Location 2)

**Location:** Line 3158  
**Severity:** 🟠 HIGH  
**Problem:** Same as H3, different location  
**Impact:** Duplicate VIX color logic bug in separate panel  
**Current Code:** Same pattern as H3  
**Fix Required:** Same fix as H3

**Status:** ❌ NOT FIXED

---

### Issue H5: Market Breadth Calculation Hides Missing Data

**Location:** Line 3173  
**Severity:** 🟠 HIGH  
**Problem:** `nhnl = (nh or 0) - (nl or 0)` shows 0 when both are None  
**Impact:** Missing breadth data displays as neutral (0), not flagged as missing  
**Current Code:**
```python
nhnl = (nh or 0) - (nl or 0) if nh is not None and nl is not None else None
# Problem: If both are None, this returns None (correct)
# But used in: hbar(cur or 0, thr, w=4) which converts None to 0
```
**Fix Required:**
```python
nh = mkt.get("nh")
nl = mkt.get("nl")
if nh is not None and nl is not None:
    nhnl = nh - nl
    display = f"{nhnl:.0f}"
else:
    display = "--"  # Show missing, not 0
```

**Status:** ❌ NOT FIXED

---

### Issue H6: Schema Validation Missing Column Types

**Location:** Lines 358-492  
**Severity:** 🟠 HIGH  
**Problem:** `validate_schema()` checks if columns exist, not if types are correct  
**Impact:** If price column is TEXT instead of NUMERIC, float() throws ValueError  
**Current Code:**
```python
# Checks existence:
if col_name not in columns:
    error(f"Column {col_name} missing")

# But doesn't check type:
# If col is TEXT type, float(price) fails later
```
**Fix Required:**
- Check not just existence but type correctness
- Validate: numeric columns are int/float, temporal are timestamp, etc.
- Return error dict if type mismatch found

**Status:** ❌ NOT FIXED

---

### Issue H7: Sector Ranking Missing Data Validation

**Location:** Lines 2683-2684  
**Severity:** 🟠 HIGH  
**Problem:** Sector ranking entries skipped if incomplete, but count not returned  
**Impact:** Operator doesn't know how many entries were filtered  
**Current Code:**
```python
# Skips incomplete entries
if not entry.get("sector") or not entry.get("rank"):
    continue  # Silently skipped

# No indication of how many were filtered
```
**Fix Required:**
- Track count of skipped entries
- Return `"filtered_count": 5` in result
- Log warning: "Sector ranking: filtered 5 incomplete entries"

**Status:** ❌ NOT FIXED

---

### Issue H8: Trade Status Not Validated Against Enum

**Location:** panel_recent_trades()  
**Severity:** 🟠 HIGH  
**Problem:** Display trade status without validating it's in valid set  
**Impact:** Invalid status values display without warning (data corruption signal)  
**Current Code:**
```python
status = trade.get("status")  # Could be anything
display = f"[green]{status}[/]"  # Shows invalid values
```
**Fix Required:**
```python
VALID_STATUSES = {"open", "closed", "exited", "cancelled"}
status = trade.get("status")
if status not in VALID_STATUSES:
    logger.warning(f"Invalid trade status: {status}")
    status = "INVALID"
display = f"[yellow]{status}[/]"
```

**Status:** ❌ NOT FIXED

---

### Issue H9: Position Entry Price Validation Incomplete

**Location:** Line 1571  
**Severity:** 🟠 HIGH  
**Problem:** Entry price checked for NULL but not for negative values  
**Impact:** Negative entry price causes wrong P&L calculation  
**Current Code:**
```python
WHEN ot.entry_price IS NULL OR ot.entry_price <= 0 THEN NULL
# ✅ This check exists and is correct
```

**Status:** ✅ VERIFIED FIXED

---

### Issue H10: Signal Quality Score Missing Validation

**Location:** Lines 1698-1703  
**Severity:** 🟠 HIGH  
**Problem:** Filters invalid signals but doesn't return count to caller  
**Impact:** Operator doesn't know how many signals were filtered out  
**Current Code:**
```python
# Filters out bad signals
valid_signals = [s for s in signals if s.get("signal_quality_score") and s.get("entry_quality_score")]

# Logs count:
if len(valid_signals) != len(signals):
    logger.warning(f"Filtered {len(signals) - len(valid_signals)} signals")

# But doesn't return count to caller!
return {"signals": valid_signals}  # Missing: "filtered_count"
```
**Fix Required:**
```python
result = {
    "signals": valid_signals,
    "filtered_count": len(signals) - len(valid_signals),
}
return result
```

**Status:** ❌ NOT FIXED

---

### Issue H11: Exposure Factor Data Presence Not Checked

**Location:** Lines ~1050-1080  
**Severity:** 🟠 HIGH  
**Problem:** Code assumes all exposure factors loaded; doesn't validate presence  
**Impact:** Missing factor data causes silent 0 values or crashes  
**Current Code:**
```python
# Assumes all factors exist:
exp = {
    "value": row.get("exposure"),
    "factor1": row.get("factor1"),  # What if factor1 missing?
}
```
**Fix Required:**
- Check each factor exists before using
- Return `"_missing_factors": ["factor1", "factor3"]` if any missing
- Display warning in panel

**Status:** ❌ NOT FIXED

---

### Issue H12: Load_all() Timeout Doesn't Show Which Fetchers Failed

**Location:** Lines 2731-2741  
**Severity:** 🟠 HIGH  
**Problem:** Timeout logged but doesn't list which fetchers are still running  
**Impact:** Operator can't debug which data source is slow  
**Current Code:**
```python
# Just logs timeout:
logger.warning(f"load_all timed out after {timeout}s")

# Doesn't say which fetchers finished vs are hanging
```
**Fix Required:**
```python
# Track which are done:
completed = [name for name, future in futures_dict.items() if future.done()]
still_running = [name for name, future in futures_dict.items() if not future.done()]

logger.warning(f"Timeout: {len(completed)} done, {len(still_running)} still running: {still_running[:5]}")
```

**Status:** ❌ NOT FIXED

---

### Issue H13: Partial Fetch Failures Not Surfaced in UI

**Location:** Multiple panel functions  
**Severity:** 🟠 HIGH  
**Problem:** When 15 of 28 fetchers timeout, panels show blank instead of degraded  
**Impact:** Operator doesn't see which data sources are down  
**Current Code:**
```python
# Panel just shows:
if not data:
    return Panel(Text("no data"))  # No indication of why

# Should show:
# "Data degraded: 10 fetchers timing out"
```
**Fix Required:**
- Return degraded indicator in fetcher results
- Display in panel: "⚠️ Data incomplete (10 fetchers timing out)"

**Status:** ❌ NOT FIXED

---

### Issue H14: No Cumulative Failure Threshold

**Location:** load_all() function (Lines 2702-2729)  
**Severity:** 🟠 HIGH  
**Problem:** No definition of when dashboard should fail vs show degraded  
**Impact:** Unclear how many fetcher failures = show error to user  
**Current Code:** No threshold defined  
**Fix Required:**
```python
# Define thresholds:
CRITICAL_FETCHERS = {"fetch_positions", "fetch_market", "fetch_perf"}
if any(f in failures for f in CRITICAL_FETCHERS):
    return {"_error": "Critical data source failed"}
elif len(failures) > 15:  # More than half failed
    return {"_degraded": True, "failures": failures}
else:
    return data  # Show with partial results
```

**Status:** ❌ NOT FIXED

---

### Issue H15: Win Rate Excludes Open Trades

**Location:** Lines 1641-1648 (fetch_recent_trades)  
**Severity:** 🟠 HIGH  
**Problem:** Query filters `WHERE status IN ('closed', 'exited')` — excludes open  
**Impact:** Shows 100% win rate with 5 closed trades, ignores 5 open at risk  
**Current Code:**
```python
SELECT symbol, profit_loss_dollars, exit_date FROM algo_trades
WHERE status IN ('closed', 'exited')  # ← EXCLUDES OPEN
AND exit_date >= NOW() - interval '7 days'
```
**Fix Required:** Either:
- Include open trades: `WHERE status IN ('closed', 'exited', 'open')`
- OR label clearly: `"metric": "win_rate_closed_only", "note": "5 open positions excluded"`

**Status:** ❌ NOT FIXED

---

### Issue H16: Win Rate Calculation Doesn't Include Unrealized Risk

**Location:** Lines 1425-1434 (fetch_perf)  
**Severity:** 🟠 HIGH  
**Problem:** Win rate calculated from closed trades only, ignores open position risk  
**Impact:** Shows 100% (5 wins) while 5 open positions have $500 unrealized loss risk  
**Current Code:**
```python
win_rate = (num_wins / (num_wins + num_losses)) * 100
# Only counts closed trades
# Doesn't mention open positions at risk
```
**Fix Required:**
```python
return {
    "win_rate_closed": win_rate,  # 100% on closed
    "open_positions": num_open,   # 5 open
    "unrealized_risk": total_open_loss,
    "_note": "Win rate is closed trades only"
}
```

**Status:** ❌ NOT FIXED

---

### Issue H17: Sharpe Ratio Calculated on Closed Trades Only

**Location:** Line 1422  
**Severity:** 🟠 HIGH  
**Problem:** Sharpe calculated from closed trade P&L, excludes open positions  
**Impact:** Metric doesn't reflect actual portfolio risk  
**Current Code:**
```python
sharpe = calculate_sharpe(closed_trades_only)
# Doesn't include open position volatility
```
**Fix Required:**
```python
sharpe = calculate_sharpe(all_trades_including_open)
# OR flag as: sharpe_closed_only = True
```

**Status:** ❌ NOT FIXED

---

## TIER 3: MEDIUM SEVERITY (20 issues)

### Issue M1: Hardcoded Grade Thresholds Not Configurable

**Location:** Lines 129-151  
**Severity:** 🟡 MEDIUM  
**Problem:** Grade thresholds (A+=90, A=80, B=70, C=60) hardcoded in code  
**Impact:** Can't tune without code changes, no audit trail of changes  
**Current Code:**
```python
GRADE_A_PLUS = 90
GRADE_A = 80
GRADE_B = 70
GRADE_C = 60
# Hardcoded constants, not in database
```
**Fix Required:**
- Add to algo_config table
- Read at startup: `THRESHOLDS = load_grade_thresholds_from_config()`
- Log when thresholds loaded

**Status:** ❌ NOT FIXED

---

### Issue M2: Hardcoded Market Thresholds Not Configurable

**Location:** Lines ~2900-3000  
**Severity:** 🟡 MEDIUM  
**Problem:** VIX 20/30, Up volume 60%, Put/Call 0.8 thresholds hardcoded  
**Impact:** Can't adjust market sensitivity without code changes  
**Current Code:**
```python
VIX_CAUTION = 20
VIX_ALERT = 30
UP_VOLUME_GOOD = 60
PUT_CALL_BULLISH = 0.8
# All hardcoded
```
**Fix Required:** Move to algo_config table

**Status:** ❌ NOT FIXED

---

### Issue M3: Hardcoded Risk Thresholds Not Configurable

**Location:** Lines ~2500-2600  
**Severity:** 🟡 MEDIUM  
**Problem:** VaR percentiles (95%, 99%), CVaR levels hardcoded  
**Impact:** Can't adjust risk tolerance without code changes  
**Current Code:**
```python
VAR_PERCENTILE = 95
CVAR_PERCENTILE = 99
# Hardcoded
```
**Fix Required:** Move to algo_config table

**Status:** ❌ NOT FIXED

---

### Issue M4: Fallback Prices Not Flagged in Display

**Location:** Lines 1603-1612, panel display (~3345)  
**Severity:** 🟡 MEDIUM  
**Problem:** `_missing_price` flag exists but not shown in UI  
**Impact:** Operator doesn't realize price is stale entry_price fallback  
**Current Code:**
```python
# Flag set in fetch:
p["_missing_price"] = True

# But not displayed in panel:
price_display = f"${price:.2f}"  # No warning shown
```
**Status:** ⚠️ PARTIALLY FIXED (flag exists, display missing)

---

### Issue M5: Sector Data Missing Visibility

**Location:** panel_positions(), line ~3345  
**Severity:** 🟡 MEDIUM  
**Problem:** Uses `p.get("sector") or "--"` but doesn't log when sector lookup failed  
**Impact:** User sees "--" but doesn't know if sector data is actually missing  
**Current Code:**
```python
sector = p.get("sector") or "--"
# No indication that sector was missing
```
**Fix Required:**
```python
sector = p.get("sector")
if sector is None:
    logger.warning(f"Sector missing for {symbol}")
    sector_display = "[yellow]--[/]"  # Yellow for missing
else:
    sector_display = sector
```

**Status:** ❌ NOT FIXED

---

### Issue M6: Risk Calculation Status Missing

**Location:** fetch_risk_metrics() results  
**Severity:** 🟡 MEDIUM  
**Problem:** Returns VaR/CVaR values but doesn't indicate if calculation was successful  
**Impact:** Operator trusts metric even if calculation failed or data insufficient  
**Current Code:**
```python
return {
    "var95": var95,      # Could be failed calculation
    "cvar95": cvar95,    # Could be missing data
    # No _has_data or _is_stale flags
}
```
**Status:** ⚠️ PARTIALLY FIXED (flags exist per code review, but not in display)

---

### Issue M7: Economic Data State Unclear

**Location:** panel_economic_pulse(), lines ~3835-3900  
**Severity:** 🟡 MEDIUM  
**Problem:** Displays economic indicators but doesn't warn when data is missing/stale  
**Impact:** User sees empty panel and assumes no data available vs fetch failure  
**Current Code:**
```python
# Returns data but no state indicator:
return {
    "cpi": cpi_value,
    "yield_curve": yc_value,
    # Missing: _data_status: "current" or "stale" or "missing"
}
```
**Status:** ⚠️ PARTIALLY FIXED (`_data_status` exists per code, not displayed)

---

### Issue M8: Swing Score Thresholds Inconsistent

**Location:** Multiple panel functions  
**Severity:** 🟡 MEDIUM  
**Problem:** `get_swing_score_thresholds()` exists but hardcoded values still used in some places  
**Impact:** Swing scores colored differently in different panels  
**Current Code:**
```python
# Central function exists (line 874-882):
def get_swing_score_thresholds():
    return {"excellent": 80, "good": 60}

# But some code still uses hardcoded:
color = G if score >= 75 else Y  # Different threshold!
```
**Fix Required:**
- Find all hardcoded swing score thresholds
- Replace with calls to `get_swing_score_thresholds()`

**Status:** ❌ NOT FIXED

---

### Issue M9: Confidence Levels Not Explained

**Location:** panel_perf_analytics(), lines ~3199-3250  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows "low confidence" label but doesn't explain why (what's needed vs what's available)  
**Impact:** User sees "low confidence" but doesn't know required vs actual data points  
**Current Code:**
```python
confidence = "low"  # Why? Need 252 days, have 100?

# Should show:
confidence_display = "[yellow]Low (need 252+ days, have 100)[/]"
```
**Fix Required:** Add explanation in tooltip or text

**Status:** ❌ NOT FIXED

---

### Issue M10: Calculation Staleness Not Shown

**Location:** panel_perf_analytics()  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows sharpe/sortino without indicating when calculated  
**Impact:** User doesn't know if metrics are current or from yesterday  
**Current Code:**
```python
sharpe_display = f"Sharpe: {sharpe:.2f}"
# When was this calculated? No timestamp.
```
**Fix Required:**
```python
sharpe_display = f"Sharpe: {sharpe:.2f} [dim](at 15:30 ET)[/]"
# Show calculation time
```

**Status:** ❌ NOT FIXED

---

### Issue M11: Circuit Breaker Defaults Not Highlighted

**Location:** panel_algo_health() → circuit breaker section  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows defaults used but doesn't suggest config update  
**Impact:** Operator doesn't realize they're using unsafe defaults  
**Current Code:**
```python
# Shows:
"vix_threshold": 30  # default

# Should show:
"vix_threshold": 30 "[yellow](USING DEFAULT — update config)[/]"
```
**Fix Required:** Flag defaults, add warning suggestion

**Status:** ❌ NOT FIXED

---

### Issue M12: Risk Metrics Missing Data Source Indicators

**Location:** panel_algo_health() → risk section  
**Severity:** 🟡 MEDIUM  
**Problem:** Displays risk metrics without indicating source (DB vs calculated vs missing)  
**Impact:** User doesn't know if metric is reliable (pre-computed vs calculated on-demand)  
**Current Code:**
```python
return {
    "var95": var95,
    # Missing: "_source": "table" or "calculated"
}
```
**Status:** ⚠️ PARTIALLY FIXED (`_source` field exists, not displayed)

---

### Issue M13: Filtered Signal Count Not Displayed

**Location:** panel_signals_compact()  
**Severity:** 🟡 MEDIUM  
**Problem:** Filters invalid signals but doesn't show how many were filtered  
**Impact:** User doesn't know signal count is reduced due to quality issues  
**Current Code:**
```python
# Filters but doesn't return count:
valid_signals = [s for s in signals if s.get("quality_score")]

# Should return:
return {
    "signals": valid_signals,
    "filtered_count": len(signals) - len(valid_signals),  # ← missing
}
```
**Status:** ⚠️ PARTIALLY FIXED (filtering exists, count not returned)

---

### Issue M14: Market Health Missing Threshold Explanations

**Location:** panel_market_full()  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows values but no context (e.g., "VIX 25" — is that good or bad?)  
**Impact:** Operator can't evaluate market health without external reference  
**Current Code:**
```python
display = f"VIX: {vix:.1f}"
# What does VIX 25 mean? Need to know it's >= 20 (caution) but < 30 (alert)
```
**Fix Required:** Add inline explanations:
```python
vix_display = f"VIX: {vix:.1f} [dim](20+=caution, 30+=alert)[/]"
```

**Status:** ❌ NOT FIXED

---

### Issue M15: Stale Data Alerts Not Returned from Fetch Functions

**Location:** fetch_market(), fetch_positions(), fetch_perf(), fetch_economic_pulse(), fetch_circuit_breaker(), fetch_risk_metrics()  
**Severity:** 🟡 MEDIUM  
**Problem:** Functions calculate `stale_alerts` list but don't return it  
**Impact:** Staleness information lost; operator doesn't see stale data warnings  
**Current Code:**
```python
def fetch_market(c):
    stale_alerts = []
    if spy_age > 1:
        stale_alerts.append(f"SPY {spy_age}d old")
    
    return {
        "pct": pct,
        # Missing: "stale_alerts": stale_alerts
    }
```
**Fix Required:** Include in return dict:
```python
return {
    "pct": pct,
    "stale_alerts": stale_alerts,  # ← ADD THIS
}
```

**Status:** ❌ NOT FIXED

---

### Issue M16: Halt Reasons Not Human-Readable

**Location:** panel_market_full(), panel_header_market()  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows halt codes like "dd:20" instead of "Portfolio drawdown >=20%"  
**Impact:** User sees cryptic codes, can't understand why trading halted  
**Current Code:**
```python
halts = mkt.get("halts")  # ["dd:20", "exposure:95"]

# Should use mapping:
HALT_REASON_NAMES = {
    "dd": "Portfolio drawdown",
    "exposure": "Position exposure",
}

halts_display = [f"{HALT_REASON_NAMES[code]}: {value}%" for code, value in halts]
```
**Status:** ⚠️ PARTIALLY FIXED (HALT_REASON_NAMES exists, display may not be using it)

---

### Issue M17: No Unified Data Health Panel

**Location:** Multiple locations, no single aggregation point  
**Severity:** 🟡 MEDIUM  
**Problem:** Data quality checks scattered across 28 fetch functions; no single view  
**Impact:** Operator can't see system health at a glance  
**Current Code:**
```python
# Health checks in:
check_loader_health() — one place
fetch_market() — checks staleness
fetch_positions() — checks for missing prices
fetch_perf() — checks for missing data
# No aggregation point
```
**Fix Required:** Create `panel_data_health()`:
```python
def panel_data_health(health_check):
    """Show freshness status for each critical data source"""
    rows = []
    for table, status in health_check.items():
        rows.append([table, status["last_update"], status["status"]])
    return Table(*rows, title="DATA FRESHNESS")
```

**Status:** ❌ NOT FIXED

---

### Issue M18: Price Source Not Indicated When Using Fallback

**Location:** panel_positions() display  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows current_price but doesn't indicate if it's fallback to entry_price  
**Impact:** P&L calculation may use days-old price without warning  
**Current Code:**
```python
price_display = f"${current_price:.2f}"
# If current_price == entry_price, it's a fallback
# But no indication shown
```
**Fix Required:**
```python
if p.get("_missing_price"):
    price_display = f"${current_price:.2f} [yellow]⚠ stale[/]"
else:
    price_display = f"${current_price:.2f}"
```

**Status:** ❌ NOT FIXED (flag exists, display missing)

---

### Issue M19: No Operator Runbook for Data Quality Alerts

**Location:** Not in dashboard.py, belongs in steering/algo.md  
**Severity:** 🟡 MEDIUM  
**Problem:** When data quality flags appear, operator doesn't know what to do  
**Impact:** Operator unsure of root cause or resolution steps  
**Current State:** No runbook exists  
**Fix Required:** Create troubleshooting guide:
```
When you see "Data degraded" warning:
1. Check which fetchers are failing (listed in alert)
2. Check AWS RDS status (go to AWS console)
3. If RDS restarting, wait 30 seconds
4. If connection timeout, run: scripts/refresh-aws-credentials.ps1
5. If data stale, check loader logs in CloudWatch
```

**Status:** ❌ NOT ADDRESSED

---

### Issue M20: Inconsistent NULL Handling

**Location:** Multiple locations  
**Severity:** 🟡 MEDIUM  
**Problem:** Some code checks `if data`, some checks `len(data)`, some checks `data is not None`  
**Impact:** Inconsistent behavior across similar code paths  
**Current Code Examples:**
```python
# Inconsistent:
if data: ...                    # Treats empty list as false
if len(data) > 0: ...           # Explicit length check
if data is not None: ...        # Explicit None check
if not data or data.get("_error"): ...  # Mixed pattern
```
**Fix Required:** Standardize pattern throughout codebase

**Status:** ❌ NOT FIXED

---

## SUMMARY TABLE

### High Severity Issues (17 total)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| H1 | Port hardcoded to 5432 | Line 242 | ❌ NOT FIXED |
| H2 | No test connection validation | Lines 246-317 | ❌ NOT FIXED |
| H3 | VIX comparison None (loc 1) | Line 3151 | ❌ NOT FIXED |
| H4 | VIX comparison None (loc 2) | Line 3158 | ❌ NOT FIXED |
| H5 | Market breadth hides missing | Line 3173 | ❌ NOT FIXED |
| H6 | Schema validation missing types | Lines 358-492 | ❌ NOT FIXED |
| H7 | Sector ranking no count | Lines 2683-2684 | ❌ NOT FIXED |
| H8 | Trade status not validated | panel_recent_trades | ❌ NOT FIXED |
| H9 | Entry price negative check | Line 1571 | ✅ VERIFIED FIXED |
| H10 | Signal quality no count | Lines 1698-1703 | ❌ NOT FIXED |
| H11 | Exposure factors not checked | Lines 1050-1080 | ❌ NOT FIXED |
| H12 | Timeout no failed fetchers | Lines 2731-2741 | ❌ NOT FIXED |
| H13 | Partial failures not surfaced | Multiple panels | ❌ NOT FIXED |
| H14 | No failure threshold | load_all() | ❌ NOT FIXED |
| H15 | Win rate excludes open | Lines 1641-1648 | ❌ NOT FIXED |
| H16 | Win rate ignores risk | Lines 1425-1434 | ❌ NOT FIXED |
| H17 | Sharpe closed-only | Line 1422 | ❌ NOT FIXED |

---

### Medium Severity Issues (20 total)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| M1 | Hardcoded grades | Lines 129-151 | ❌ NOT FIXED |
| M2 | Hardcoded market thresholds | Lines ~2900-3000 | ❌ NOT FIXED |
| M3 | Hardcoded risk thresholds | Lines ~2500-2600 | ❌ NOT FIXED |
| M4 | Fallback prices not flagged | Lines 1603-1612 | ⚠️ PARTIAL |
| M5 | Sector visibility missing | ~3345 | ❌ NOT FIXED |
| M6 | Risk calculation status | fetch_risk_metrics | ⚠️ PARTIAL |
| M7 | Economic data state | ~3835-3900 | ⚠️ PARTIAL |
| M8 | Swing score inconsistent | Multiple | ❌ NOT FIXED |
| M9 | Confidence not explained | ~3199-3250 | ❌ NOT FIXED |
| M10 | Calculation staleness | panel_perf | ❌ NOT FIXED |
| M11 | Breaker defaults not flagged | panel_algo_health | ❌ NOT FIXED |
| M12 | Risk source not indicated | panel_algo_health | ⚠️ PARTIAL |
| M13 | Filtered signal count | panel_signals | ⚠️ PARTIAL |
| M14 | Market health no explanations | panel_market_full | ❌ NOT FIXED |
| M15 | Stale alerts not returned | 6 fetch functions | ❌ NOT FIXED |
| M16 | Halt reasons cryptic | panel_market_full | ⚠️ PARTIAL |
| M17 | No health panel | Multiple | ❌ NOT FIXED |
| M18 | Price source not indicated | panel_positions | ❌ NOT FIXED |
| M19 | No operator runbook | steering/algo.md | ❌ NOT ADDRESSED |
| M20 | NULL handling inconsistent | Multiple | ❌ NOT FIXED |

---

## QUICK STATS

**High Severity:** 17 issues
- ❌ Not Fixed: 16
- ✅ Verified Fixed: 1

**Medium Severity:** 20 issues
- ❌ Not Fixed: 15
- ⚠️ Partially Fixed: 5
- ❌ Not Addressed: 1

**Total High + Medium:** 37 issues  
**Estimated Fix Time:** 5-7 hours  
**Recommended Order:** High (H1-H17) then Medium (M1-M20)

---

## Next Steps

1. ✅ **REVIEW THIS LIST** — Understand all 37 items
2. 🔧 **START WITH HIGH** — Fix H1-H17 (3-4 hours)
3. 🔧 **THEN MEDIUM** — Fix M1-M20 (2-3 hours)
4. ✔️ **TEST** — Verify each fix works
5. 📚 **UPDATE DOCS** — After all verification complete

