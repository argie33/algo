# Dashboard Issues — Priority Matrix & Action Plan

**Created:** 2026-06-10  
**Scope:** All 97+ unresolved issues in dashboard.py and related systems  
**Purpose:** Quick-reference guide for fixing issues in order of business impact

---

## TIER 1: CRITICAL (Fix Today — 2-3 hours)

These issues cause **silent data loss** and **wrong operational decisions**

### T1.1: Data Loss via `or 0` / `or []` Defaults (38 locations)

**What's Wrong:**
- Code shows "0%" when data is missing
- Operator can't tell if algo lost money or data didn't load
- Shows market as "calm" (green) when VIX data is missing

**Where:** 174 matches across dashboard.py (sample lines: 616, 788, 793, 811, 920, 1071, 1539-1540, 3064-3067, 3173)

**Fix:** Create `display_metric()` function:
```python
def display_metric(val, unit="", missing_display="--"):
    if val is None: return missing_display
    return f"{val}{unit}"
```

Then replace patterns like:
```python
# Before:
val = perf.get("win_rate") or 0  # Shows "0%" if missing

# After:
val = perf.get("win_rate")  # Keep as None
display = display_metric(val, "%")  # Shows "--" if missing
```

**Why:** Operator must see "--" when data is missing, not "0"

**Effort:** 1 hour | **Impact:** 🔴 CRITICAL (highest risk)

---

### T1.2: Error Dicts Not Validated Before Use (18+ panels)

**What's Wrong:**
- Fetch returns `{"_error": "timeout"}` on failure
- Panel code does `if data:` and treats dict as valid
- User sees blank panel, doesn't know data is broken

**Where:** Every panel function needs validation

**Fix:** Add check at start of EACH panel:
```python
def panel_positions(positions):
    if not positions or positions.get("_error"):
        return Panel(Text(f"Error: {positions.get('_error', 'no data')}",
                          style="red"), title="[bold]POSITIONS[/]")
    # ... render normally
```

**Why:** Operator must see RED ERROR, not blank panel

**Effort:** 45 min | **Impact:** 🔴 CRITICAL (data reliability)

---

### T1.3: Type Validation Missing (14+ cases)

**What's Wrong:**
- Code does `float(row.get("price") or 0)` without checking type
- If price = "N/A" (string), throws ValueError
- Exception caught, function returns empty dict
- User sees "no data" instead of "ERROR: bad data"

**Where:** All fetch functions that convert strings to numbers

**Fix:** Add validation in `load_all()` before returning:
```python
def validate_types(data):
    errors = []
    for key, val in data.items():
        if isinstance(val, dict) and "_error" not in val:
            # Check each field matches expected type
            if key == "positions":  # Should be list
                if not isinstance(val, list):
                    errors.append(f"{key}: expected list, got {type(val)}")
    if errors:
        return {"_error": "; ".join(errors)}
    return data
```

**Why:** Operator needs to know "data type is broken", not just "no data"

**Effort:** 30 min | **Impact:** 🔴 CRITICAL (error transparency)

---

## TIER 2: HIGH PRIORITY (Fix This Week — 4-5 hours)

### T2.1: Stale Data Not Surfaced (6 locations)

**What's Wrong:**
- fetch_market() logs "SPY data is 5 days old" but doesn't return it
- Panel shows "Market Tier: Pressure" without mentioning stale data
- Operator makes decision on 5-day-old prices

**Where:** Lines 1064-1077 (fetch_market) and 5 other fetchers

**Fix:** Return `stale_alerts` list:
```python
# In fetch_market():
stale_alerts = []
if spy_age > 1:
    stale_alerts.append(f"SPY {spy_age}d old")

return {
    "pct": pct,
    "tier": tier,
    "stale_alerts": stale_alerts,  # ← ADD THIS
}

# In panel_market_full():
if mkt.get("stale_alerts"):
    alerts_str = " ⚠️ " + ", ".join(mkt["stale_alerts"])
    # Display with warning color
```

**Effort:** 1 hour | **Impact:** 🟠 HIGH (prevent stale data decisions)

---

### T2.2: Win Rate Calculation Excludes Open Trades

**What's Wrong:**
- Query filters: `WHERE status IN ('closed', 'exited')`
- Algo has 5 closed (+100%) and 5 open (at risk)
- Shows "Win Rate: 100%" (misleading!)

**Where:** Lines 1641-1648 (fetch_recent_trades)

**Fix:** Include open trades OR label clearly:
```python
# Option A: Include open trades
WHERE status IN ('closed', 'exited', 'open')

# Option B: Label clearly
return {
    "win_rate": 100,  # closed trades only
    "_closed_only_note": "5 open positions not included",
}
```

**Effort:** 30 min | **Impact:** 🟠 HIGH (prevent misleading metrics)

---

### T2.3: VIX Comparison Uses 0 for None (2+ locations)

**What's Wrong:**
- Code: `vc = R if (mkt.get("vix") or 0) >= 30`
- If vix = None: becomes `0 >= 30` → False → GREEN color
- Operator thinks market is calm, actually VIX data is missing

**Where:** Lines 3151, 3158, 3173

**Fix:**
```python
if mkt.get("vix") is None:
    vix_s = "--"
    vc = Y  # Yellow = unknown
else:
    vix = float(mkt.get("vix"))
    vc = R if vix >= 30 else (Y if vix >= 20 else G)
```

**Effort:** 20 min | **Impact:** 🟠 HIGH (prevent wrong market signal)

---

### T2.4: Unified Data Health Panel Missing

**What's Wrong:**
- Data quality checks scattered across 28 fetch functions
- No single place to see which data is fresh/stale/broken
- Operator can't tell system health at a glance

**Where:** All fetch functions, but no aggregation point

**Fix:** Create `panel_data_health()`:
```python
def panel_data_health(health_check):
    """Show freshness status for each critical data source"""
    rows = []
    for table, status in health_check.items():
        color = "green" if status["fresh"] else "yellow" if status["stale"] else "red"
        rows.append([table, status["last_update"], status["status"]])
    return Table(*rows, title="[bold]DATA FRESHNESS[/]")
```

**Effort:** 1.5 hours | **Impact:** 🟠 HIGH (operator visibility)

---

## TIER 3: MEDIUM PRIORITY (Fix Next 2 Weeks — 3-4 hours)

### T3.1: Hardcoded Grade Thresholds Not Configurable

**Where:** Lines 129-151  
**Fix:** Move to algo_config table, read at startup  
**Impact:** 🟡 MEDIUM (operational flexibility)

### T3.2: Threshold Explanations Missing

**Where:** Market health panel (VIX, Up Volume, etc.)  
**Fix:** Add inline explanations: "VIX > 20 = caution"  
**Impact:** 🟡 MEDIUM (operator education)

### T3.3: Sector Data Missing Visibility

**Where:** panel_positions(), line ~3345  
**Fix:** Log when sector lookup fails, flag in UI  
**Impact:** 🟡 MEDIUM (data quality awareness)

### T3.4: Risk Calculation Status Not Indicated

**Where:** Risk metrics panel  
**Fix:** Show "(current)" vs "(stale)" vs "(incomplete)" status  
**Impact:** 🟡 MEDIUM (metric reliability)

### T3.5: Economic Data State Unclear

**Where:** panel_economic_pulse()  
**Fix:** Show explicit "data not available" vs "fetching" vs "current"  
**Impact:** 🟡 MEDIUM (operator understanding)

### T3.6: Signal Quality Metrics Not Displayed

**Where:** panel_signals_compact()  
**Fix:** Show count of filtered signals  
**Impact:** 🟡 MEDIUM (data quality awareness)

### T3.7: Swing Score Threshold Inconsistency

**Where:** Multiple panel functions  
**Fix:** Use centralized `get_swing_score_thresholds()`  
**Impact:** 🟡 MEDIUM (consistency)

### T3.8: Calculation Staleness Not Shown

**Where:** Rolling metrics (Sharpe, Sortino)  
**Fix:** Display "calculated at HH:MM ET"  
**Impact:** 🟡 MEDIUM (metric freshness)

### T3.9: Circuit Breaker Defaults Not Highlighted

**Where:** Circuit breaker panel  
**Fix:** Highlight when defaults are used, suggest config update  
**Impact:** 🟡 MEDIUM (config awareness)

### T3.10: Risk Metrics Missing Data Source Indicators

**Where:** Risk section of algo_health panel  
**Fix:** Show `_source: "table"` vs `_source: "calculated"`  
**Impact:** 🟡 MEDIUM (transparency)

---

## TIER 4: LOW PRIORITY (Fix as Time Allows — 2-3 hours)

### T4.1: Operator Runbook Missing

**What:** No guide on what to do when data quality flags appear  
**Fix:** Create troubleshooting guide in steering/algo.md  
**Impact:** 🟢 LOW (operational runbook)

### T4.2: Trade Status Not Validated

**What:** Display trade status without validating against enum  
**Fix:** Validate status in enum, log invalid values  
**Impact:** 🟢 LOW (data validation)

### T4.3: Halt Reasons Not Human-Readable

**What:** Show halt codes like "dd:20" instead of "Portfolio drawdown >=20%"  
**Fix:** Use HALT_REASON_NAMES mapping  
**Impact:** 🟢 LOW (UX improvement)

---

## MASTER CHECKLIST: Tier 1 (Critical) Tasks

```
TIER 1 CRITICAL FIXES (2-3 hours total)

□ T1.1 (1 hour): Fix "or 0" / "or []" patterns
  - Create display_metric() function
  - Replace 38+ instances across panels
  - Test: show "--" for missing, not "0"
  
□ T1.2 (45 min): Add error validation to 18+ panels
  - Add check: if not data or data.get("_error"): return ErrorPanel(...)
  - Test: intentionally fail one fetcher
  - Verify error displayed (not blank panel)
  
□ T1.3 (30 min): Add type validation to load_all()
  - Try/except around float/int conversions
  - Return error dict on type mismatch
  - Test: pass bad data types, confirm error shown

TIER 1 VERIFICATION (required before any deployment)

□ Dashboard shows "--" for missing values, not "0"
□ Error panels show RED with error message
□ Type errors show "ERROR: invalid data type" not crash
□ All 97 tests pass (unit + integration)
□ Manual smoke test: run dashboard, verify health
```

---

## Quick Reference: Lines to Fix

### Lines with `or 0` / `or []` (Find & Replace Opportunities)

```
616: status = (p.get("status") or "").lower().strip()
788: f = int(min(float(pct or 0), 100) / 100 * w)
793: r = min(float(pts or 0) / float(max_pts or 1), 1.0)
811: vals = [v for v in (values or []) if ...]
920: pr = row.get("phase_results") or []
928: overall = (row.get("overall_status") or "").lower()
937-939: Multiple "or []" in list creation
1071: halts = exp.get("halt_reasons") or []
1461: closed_count = int(...get("closed_count") or 0)
1539-1540: num_wins/losses with "or 0"
1629: row_count = int(table_check.get("cnt") or 0)
1818: total_n = int(total_r["n"] or 0)
... and 160+ more
```

### Lines with Error Dict Not Checked

```
(Every panel function needs validation at start:)
- panel_positions()
- panel_market_full()
- panel_signals_compact()
- panel_economic_pulse()
- panel_algo_health()
- panel_perf_analytics()
- ... (18+ total)
```

### Lines with Type Conversions Needing Validation

```
1414: maxdd = float(perf.get("max_drawdown_pct")) if ... else 0.0
2024-2026: fg = float(row.get("fear_greed_index") or 0)
2927: spy = f"${mkt['spy']:.2f}" if mkt.get("spy") else "--"
3050-3051: upvol = mkt.get("upvol"); nh = mkt.get("nh"); ...
... (14+ locations)
```

---

## Summary Table

| Tier | Category | Count | Hours | Impact | Status |
|------|----------|-------|-------|--------|--------|
| **1** | Data loss (or 0) | 38 | 1.0 | 🔴 CRITICAL | TODO |
| **1** | Error validation | 18 | 0.75 | 🔴 CRITICAL | TODO |
| **1** | Type validation | 14 | 0.5 | 🔴 CRITICAL | TODO |
| **2** | Stale data surfacing | 6 | 1.0 | 🟠 HIGH | TODO |
| **2** | Win rate filtering | 1 | 0.5 | 🟠 HIGH | TODO |
| **2** | VIX None handling | 2 | 0.33 | 🟠 HIGH | TODO |
| **2** | Health panel | 1 | 1.5 | 🟠 HIGH | TODO |
| **3** | Config & visibility | 10 | 3.0 | 🟡 MEDIUM | TODO |
| **4** | Runbook & UX | 3 | 1.5 | 🟢 LOW | TODO |
| | **TOTAL** | **93** | **9.5** | | **ALL TODO** |

---

## Next Action

**✅ ACCEPT THIS AUDIT**

Choose your approach:
1. **Fix all TIER 1 (2-3 hours)** → Deploy with confidence
2. **Fix TIER 1 + TIER 2 (6-8 hours)** → Comprehensive fix
3. **Fix everything (11-15 hours)** → Complete system overhaul

**Recommendation:** Fix TIER 1 + TIER 2 (6-8 hours) — gets you 90% of the way there.
