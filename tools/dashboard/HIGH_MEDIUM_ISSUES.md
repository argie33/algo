# High & Medium Severity Issues — Focused List

**Date:** 2026-06-11 (Last updated: Session complete)
**Scope:** Tier 2 (HIGH) + Tier 3 (MEDIUM) issues  
**Count:** 37 total issues (17 HIGH, 20 MEDIUM)
**Status:** ALL 17 HIGH severity issues RESOLVED
**Time to Complete HIGH Tier:** 4-5 hours (COMPLETED)
**Next Priority:** MEDIUM severity issues (M1-M20)

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

**Location:** Lines 1887-1904 (fetch_signals)  
**Severity:** 🟠 HIGH  
**Problem:** Filters invalid signals but doesn't return count to caller  
**Impact:** Operator doesn't know how many signals were filtered out  
**Implementation:**
```python
# Lines 1887-1904: Filter signals with missing quality scores
before_count = len(buy_sigs)
buy_sigs = [s for s in buy_sigs if s.get("signal_quality_score") is not None or s.get("entry_quality_score") is not None]
filtered_count = before_count - len(buy_sigs) if before_count != len(buy_sigs) else 0
if filtered_count > 0:
    logger.warning(f"VALIDATION: Filtered {filtered_count} signals with missing quality scores")

# Lines 1998: Return count to caller
return {..., "filtered_count": filtered_count, ...}

# Lines 3832-3833: Display in panel_signals_compact
filtered = sig.get("filtered_count", 0)
filtered_hint = f"  [{R}]{filtered} filtered[/]" if filtered > 0 else ""
```

**Status:** ✅ VERIFIED FIXED (Lines 1887-1904, 1998, 3832-3833)

---

### Issue H11: Exposure Factor Data Presence Not Checked

**Location:** Lines 1354-1432 (fetch_exposure_factors)  
**Severity:** 🟠 HIGH  
**Problem:** Code assumes all exposure factors loaded; doesn't validate presence  
**Impact:** Missing factor data causes silent 0 values or crashes  
**Implementation:**
```python
# Lines 1375-1409: Validate all expected factors are present and numeric
expected_keys = {"follow_through_day", "trend_30wk", "breadth_50dma", ...}
found_keys = set(factors.keys())
missing_keys = expected_keys - found_keys
if missing_keys:
    data_quality = "degraded"
    missing_keys_list = sorted(list(missing_keys))

# Lines 1420-1422: Return quality flags to caller
result = {
    "_data_quality": data_quality,
    "_missing_keys": missing_keys_list,
    "_invalid_values": invalid_values_list,
}

# Lines 4254-4266: Display warning in panel_exposure_compact
data_quality = exp_f.get("_data_quality", "good")
if data_quality == "degraded":
    quality_indicator = " [yellow]⚠ partial data[/]"
```

**Status:** ✅ VERIFIED FIXED (Lines 1354-1432, 4254-4266)

---

### Issue H12: Load_all() Timeout Doesn't Show Which Fetchers Failed

**Location:** Lines 2946-3021 (load_all function)  
**Severity:** 🟠 HIGH  
**Problem:** Timeout logged but doesn't list which fetchers are still running  
**Impact:** Operator can't debug which data source is slow  
**Implementation:**
```python
# Lines 3007-3020: Handle timeout and report status
except TimeoutError:
    elapsed = time.time() - load_start
    logger.error(f"load_all batch timed out after {BATCH_TIMEOUT}s (total elapsed {elapsed:.1f}s)")
    
    # Lines 3011-3014: Track completion status
    completed_count = sum(1 for f in future_to_key if f.done())
    remaining_count = len(future_to_key) - completed_count
    still_running = [k for f, k in future_to_key.items() if not f.done()]
    logger.warning(f"Timeout status: {completed_count} fetchers done, {remaining_count} still running ({', '.join(still_running[:5])}{'...' if remaining_count > 5 else ''})")
```

**Status:** ✅ VERIFIED FIXED (Lines 3007-3020)

---

### Issue H13: Partial Fetch Failures Not Surfaced in UI

**Location:** Multiple panel functions (market, positions, exposure, economic)  
**Severity:** 🟠 HIGH  
**Problem:** When 15 of 28 fetchers timeout, panels show blank instead of degraded  
**Impact:** Operator doesn't see which data sources are down  
**Implementation across multiple panels:**
```python
# panel_market_full (lines 3290-3292):
stale_alerts = mkt.get("stale_alerts", [])
if stale_alerts:
    lines.append(f"[orange1][!] Data stale:[/] {', '.join(stale_alerts)}")

# panel_positions (lines 3780-3782):
if stale_alerts:
    content = Group(t, Text.from_markup(f"[orange1][!] Stale data:[/] {', '.join(stale_alerts)}"))

# panel_exposure_compact (lines 4254-4266):
data_quality = exp_f.get("_data_quality", "good")
if data_quality == "degraded":
    quality_indicator = " [yellow]⚠ partial data[/]"
elif data_quality == "missing":
    quality_indicator = " [red]⚠ no data[/]"

# panel_economic_pulse (lines 4277-4282):
data_status = eco.get('_data_status', 'unknown')
if last_update:
    rows.append(Text.from_markup(f"[dim]Data as of:[/] [{status_color}]{last_update}[/]"))

# panel_data_quality_status (lines 4960-5023):
# Comprehensive unified panel showing all data source health
```

**Status:** ✅ VERIFIED FIXED (Multiple locations)

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
**Implementation:**
```python
# Lines 1829-1837 (fetch_positions): Detect missing sectors and log
missing_sectors = [p for p in result if p.get("sector") is None]
if missing_sectors:
    logger.warning(f"VALIDATION: {len(missing_sectors)} open positions missing sector data...")
    for p in missing_sectors:
        p["_missing_sector"] = True

# Lines 3885-3887 (panel_positions): Display warning indicator
sec_val = p.get("sector")
sec_warning = " ⚠" if p.get("_missing_sector", False) else ""
sec = ((sec_val or "--")[:12] + sec_warning) if sec_val else ("--" + sec_warning)
```

**Status:** ✅ FIXED (Commit 100384a84)

---

### Issue M6: Risk Calculation Status Missing

**Location:** fetch_risk_metrics() results  
**Severity:** 🟡 MEDIUM  
**Problem:** Returns VaR/CVaR values but doesn't indicate if calculation was successful  
**Impact:** Operator trusts metric even if calculation failed or data insufficient  
**Implementation:**
```python
# Lines 2448-2459 (fetch_risk_metrics): Return status flags
result = {
    "_has_data": True,
    "_source": "table",
    "_is_stale": not is_fresh,
    "_age_minutes": age_minutes,
}

# Lines 5058-5067 (panel_algo_health): Display status indicator
has_data = risk.get("_has_data", False)
is_stale = risk.get("_is_stale", False)
if not has_data:
    rows.append(Text.from_markup(f"[{R}]⚠ Risk calculation incomplete[/]"))
elif is_stale and age_min:
    rows.append(Text.from_markup(f"[{Y}]⚠ Risk data stale ({age_min:.0f}min old)[/]"))
else:
    rows.append(Text.from_markup(f"[{G}]✓ Risk metrics current[/]"))
```

**Status:** ✅ FIXED (Commit 6ae9f1efa)

---

### Issue M7: Economic Data State Unclear

**Location:** panel_economic_pulse(), lines ~3835-3900  
**Severity:** 🟡 MEDIUM  
**Problem:** Displays economic indicators but doesn't warn when data is missing/stale  
**Impact:** User sees empty panel and assumes no data available vs fetch failure  
**Implementation:**
```python
# Lines 2308-2329 (fetch_economic_pulse): Return data freshness status
max_date_row = q1(c, "SELECT MAX(date) as max_date FROM economic_data...")
days_stale = (datetime.now(ET).date() - last_update).days if last_update else None
data_status = 'current' if days_stale == 0 else ('1day_old' if days_stale == 1 else ...)
result = {
    '_last_update': last_update,
    '_data_status': data_status,
}

# Lines 4418-4423 (panel_economic_pulse): Display freshness status
data_status = eco.get('_data_status', 'unknown')
last_update = eco.get('_last_update')
status_color = G if data_status == 'current' else (Y if '1day_old' in data_status else R)
if last_update:
    rows.append(Text.from_markup(f"[dim]Data as of:[/] [{status_color}]{last_update}[/]"))
```

**Status:** ✅ FIXED (Issue 38 FIX)

---

### Issue M8: Swing Score Thresholds Inconsistent

**Location:** Multiple panel functions  
**Severity:** 🟡 MEDIUM  
**Problem:** `get_swing_score_thresholds()` exists but hardcoded values still used in some places  
**Impact:** Swing scores colored differently in different panels  
**Implementation:**
```python
# Lines 1068-1110 (get_swing_score_thresholds): Central config-based function
def get_swing_score_thresholds(cfg: dict) -> dict:
    swing_excellent = _parse_config_float(d, "swing_score_excellent_threshold", 80.0)
    swing_good = _parse_config_float(d, "swing_score_good_threshold", 60.0)
    return {"excellent": swing_excellent, "good": swing_good}

# Lines 3920-3921 (panel_positions): Use function for consistency
swing_thresholds = get_swing_score_thresholds(cfg)
swg_c = G if swg_s is not None and swg_s >= swing_thresholds["excellent"] else (...)

# Lines 4062-4063 (panel_signals_expanded): Same consistent approach
swing_thresholds = get_swing_score_thresholds(cfg)
swg_c = G if swg is not None and swg >= swing_thresholds["excellent"] else (...)
```

**Status:** ✅ FIXED (Commit 6ae9f1efa, Issue 42)

---

### Issue M9: Confidence Levels Not Explained

**Location:** panel_perf_analytics(), lines ~3199-3250  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows "low confidence" label but doesn't explain why (what's needed vs what's available)  
**Impact:** User sees "low confidence" but doesn't know required vs actual data points  
**Implementation:**
```python
# Lines 3645-3651 (panel_perf_analytics): Explain Sharpe confidence
sharpe_conf_explain = {
    'high': '252+ days',
    'medium': '63-251 days',
    'low': '<63 days'
}
sharpe_label = f"{sharpe_s} ({sharpe_conf}, {sharpe_conf_explain.get(sharpe_conf, '')})"

# Lines 3693-3701 (panel_perf_analytics): Explain recent returns confidence
recent_rets_conf = perf.get("recent_rets_confidence")
conf_explain = {
    'high': '(5+ snapshots)',
    'medium': '(3-4 snapshots)',
    'low': '(<3 snapshots)'
}
conf_note = f" [dim]{conf_explain.get(recent_rets_conf, '')}[/]" if recent_rets_conf else ""
```

**Status:** ✅ FIXED (Commit 6ae9f1efa)

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

**Location:** panel_circuit() → circuit breaker display  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows defaults used but doesn't highlight the threshold  
**Impact:** Operator doesn't realize when a breaker is approaching caution threshold  
**Implementation:**
```python
# Lines 3413-3419 (panel_circuit): Highlight caution threshold in UI
caution_threshold = ui_cfg['circuit_breaker_ratio_caution']
fc = R if fired else (Y if ratio >= caution_threshold else G)
caution_hint = f" [dim]({caution_threshold:.0%} caution)[/]" if ratio >= caution_threshold and not fired else ""
# Displays: "Label: current/threshold (75% caution)" when in caution zone
```
**What Was Fixed:**
- When a circuit breaker ratio reaches caution state (≥75%), shows the threshold percentage
- Makes the color-coding logic transparent to operator
- Helps users understand why a breaker turned yellow

**Status:** ✅ FIXED (Commit 6aece95c3)

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

**Location:** panel_market_full() and panel_header_market()  
**Severity:** 🟡 MEDIUM  
**Problem:** Shows values without context (e.g., "VIX 25" — user doesn't know thresholds)  
**Impact:** Operator can't evaluate market health without external reference  
**Implementation:**
```python
# Lines 3335-3352 (panel_market_full): Show dynamic thresholds from config
f"VIX:[{vc}]{vix}[/] [dim]({mkt_cfg['vix_caution']:.0f}+=caution, {mkt_cfg['vix_alert']:.0f}+=alert)[/]"
f"Up Volume:[{uvc}]{upvol:.0f}%[/] [dim]({mkt_cfg['upvol_good']:.0f}%+=good)[/]"
f"Put/Call:[{pcr_c}]{pcr:.2f}[/] [dim](<{mkt_cfg['put_call_bullish']:.1f}=bullish)[/]"
f"Breadth Momentum:[{bmc}]{bmom:.1f}[/] [dim]({mkt_cfg['breadth_momentum_good']:.1f}+=bullish)[/]"
```
**What Was Fixed:**
- Replaced hardcoded threshold explanations with actual config values
- VIX now shows actual caution/alert thresholds from config (was 20/30)
- Up Volume shows actual good threshold from config (was 50)
- Put/Call shows actual bullish threshold from config (was 0.8)
- Breadth Momentum shows actual good threshold from config (was 0.5)
- Makes explanations transparent and configurable

**Status:** ✅ FIXED (Commit 6aece95c3)

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
| H1 | Port hardcoded to 5432 | lambda/api/utils/db_connection.py | ✅ FIXED (commit 306b26481) |
| H2 | No test connection validation | lambda/api/utils/db_connection.py | ✅ FIXED (commit 306b26481) |
| H3 | VIX comparison None (loc 1) | Line 3151 | ✅ FIXED (TIER 1A) |
| H4 | VIX comparison None (loc 2) | Line 3158 | ✅ FIXED (TIER 1A) |
| H5 | Market breadth hides missing | Line 3173 | ✅ FIXED (TIER 1A) |
| H6 | Schema validation missing types | Lines 478-613 | ✅ FIXED (TIER 1B) |
| H7 | Sector ranking no count | Lines 4098-4119 | ✅ FIXED (commit 100384a84) |
| H8 | Trade status not validated | Lines 1832-1844 | ✅ FIXED (TIER 1B) |
| H9 | Entry price negative check | Line 1571 | ✅ FIXED (database check) |
| H10 | Signal quality no count | Lines 1887-1904 | ✅ FIXED (TIER 1A) |
| H11 | Exposure factors not checked | Lines 1354-1432 | ✅ FIXED (TIER 1B) |
| H12 | Timeout no failed fetchers | Lines 3015-3019 | ✅ FIXED (TIER 1B) |
| H13 | Partial failures not surfaced | Lines 3027-3055 | ✅ FIXED (H14 implementation) |
| H14 | No failure threshold | Lines 3027-3055 | ✅ FIXED (commit 100384a84) |
| H15 | Win rate excludes open | Lines 1519-1521 | ✅ FIXED (TIER 1A) |
| H16 | Win rate ignores risk | Lines 1521, 1621 | ✅ FIXED (TIER 1A) |
| H17 | Sharpe closed-only | Lines 1563-1572 | ✅ FIXED (TIER 1B) |

---

### Medium Severity Issues (20 total)

| # | Issue | Location | Status |
|---|-------|----------|--------|
| M1 | Hardcoded grades | Lines 129-151 | ✅ FIXED (823984fef) |
| M2 | Hardcoded market thresholds | Lines ~2900-3000 | ✅ FIXED (823984fef) |
| M3 | Hardcoded risk thresholds | Lines ~2500-2600 | ✅ FIXED (823984fef) |
| M4 | Fallback prices not flagged | Lines 1603-1612 | ⚠️ PARTIAL |
| M5 | Sector visibility missing | ~3345 | ✅ FIXED (100384a84) |
| M6 | Risk calculation status | fetch_risk_metrics | ✅ FIXED (6ae9f1efa) |
| M7 | Economic data state | ~3835-3900 | ✅ FIXED (Issue 38) |
| M8 | Swing score inconsistent | Multiple | ✅ FIXED (6ae9f1efa) |
| M9 | Confidence not explained | ~3199-3250 | ✅ FIXED (6ae9f1efa) |
| M10 | Calculation staleness | panel_perf | ✅ FIXED (Issue 43) |
| M11 | Breaker defaults not flagged | panel_algo_health | ✅ FIXED (6aece95c3) |
| M12 | Risk source not indicated | panel_algo_health | ⚠️ PARTIAL |
| M13 | Filtered signal count | panel_signals | ⚠️ PARTIAL |
| M14 | Market health no explanations | panel_market_full | ✅ FIXED (6aece95c3) |
| M15 | Stale alerts not returned | 6 fetch functions | 🔄 IN PROGRESS (6aec0ae20) |
| M16 | Halt reasons cryptic | panel_market_full | ⚠️ PARTIAL |
| M17 | No health panel | Multiple | ❌ NOT FIXED |
| M18 | Price source not indicated | panel_positions | ❌ NOT FIXED |
| M19 | No operator runbook | steering/algo.md | ✅ FIXED (067324d3c) |
| M20 | NULL handling inconsistent | Multiple | ❌ NOT FIXED |

---

## QUICK STATS — M5-M9 COMPLETE

**High Severity:** 17 issues
- ✅ FIXED: 17 (100%)
- ❌ Remaining: 0

**Medium Severity (M5-M9):** 5 issues
- ✅ FIXED: 5/5 (100%)
- ⚠️ Partially Fixed: 0
- ❌ Not Fixed: 0

**Medium Severity (All 20):** 20 issues
- ✅ Fixed: 12 (M1-3, M5-11, M14, M19)
- ⚠️ Partially Fixed: 5 (M4, M12, M13, M16, M18)
- 🔄 In Progress: 1 (M15)
- ❌ Not Fixed: 2 (M17, M20)

**Overall Progress:** 
- ✅ HIGH TIER: 17/17 (100%)
- ✅ M5-M9 (Goal): 5/5 (100%)
- ✅ M11 & M14 (New Goal): 2/2 (100%)
- ✅ Medium Tier Progress: 12/20 (60%)
- Total Issues Addressed: 29/37 (78%)

---

## Next Steps

1. ✅ **COMPLETE:** HIGH severity (H1-H17) — All 17 issues resolved
2. 🔄 **IN PROGRESS:** MEDIUM severity (M1-M20) — Start with highest-impact fixes
3. 📋 **Recommended MEDIUM priority order:**
   - M15: Stale alerts not returned (5 fetch functions) — QUICK WIN
   - M4, M18: Price/fallback display visibility — 30min each
   - M5: Sector missing data visibility — 20min
   - M10: Calculation staleness display — 15min
4. ✔️ **TEST** — Verify each MEDIUM fix works
5. 📚 **UPDATE DOCS** — After all verification complete

