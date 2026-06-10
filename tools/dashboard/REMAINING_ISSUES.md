# Remaining Data Quality & Validation Issues (Beyond 24-30)

**Date:** 2026-06-10  
**Scope:** All unresolved data quality issues in dashboard.py and related loaders

---

## CRITICAL ISSUES

### Issue 31: Hardcoded Grade Thresholds Not Configurable
**Location:** Lines 129-151  
**Problem:** Grade thresholds (A+=90, A=80, B=70, C=60) and other indicators (tier thresholds, OAS levels, CPI targets) are hardcoded constants instead of reading from config database

**Impact:**
- Cannot tune grading without code changes
- No audit trail of threshold changes
- Different operators may have different versions deployed

**Severity:** MEDIUM  
**Fix Required:** Add grade thresholds to algo_config table and read from database

---

### Issue 32: Default Values Hiding Missing Data
**Locations:** Lines 698, 703, 1350, 1438-1439, 1688, 1800  
**Examples:**
```python
pct or 0           # Line 698: missing percentage defaults to 0
or 0.0            # Line 703: missing ratio defaults to 0
int(...) or 0      # Line 1350, 1438-1439: missing counts default to 0
int(sig["n"] or 0) # Line 1800: missing signal count defaults to 0
```

**Problem:** Using `or 0` as default silently hides missing data instead of surfacing it

**Impact:**
- Operator sees 0 grades/signals when data is missing
- No indication that data failed to load
- Can't distinguish "no results" from "no data"

**Severity:** HIGH  
**Fix Required:** Return None for missing counts, let dashboard display as "--"

---

### Issue 33: Price Calculations Without Fallback Indicators
**Location:** Multiple panel functions (panel_positions, panel_market_full, etc.)  
**Problem:** Price-based calculations use fallback prices without indicating fallback was used

**Impact:**
- Users see prices but don't know if they're stale
- P&L calculations may use days-old prices
- Distance to stop loss uses potentially stale prices

**Severity:** HIGH  
**Fix Required:** Explicitly flag when prices are fallback values

---

## HIGH SEVERITY ISSUES

### Issue 34: Market Health Panel Missing Threshold Explanations
**Location:** panel_market_full() function  
**Problem:** Market stage, VIX, yield curve displays show values but no context for what's "good" vs "warning"

**Impact:**
- Users can't tell if market is healthy without external reference
- No indication of historical context

**Severity:** MEDIUM  
**Fix Required:** Add threshold labels ("VIX > 35 = caution")

---

### Issue 35: Positions Panel Doesn't Warn About Missing Sector
**Location:** panel_positions(), line 3364  
**Problem:** Uses `p.get("sector") or "--"` but doesn't log when sector lookup failed

**Impact:**
- User sees "--" but doesn't know if sector data is missing or just not set
- No visibility into data quality issue

**Severity:** MEDIUM  
**Fix Required:** Log sector lookup failures, flag in UI

---

### Issue 36: Performance Analytics Panel Doesn't Explain Low Confidence
**Location:** panel_perf_analytics(), lines 3199-3250  
**Problem:** Shows sharpe ratio with "low confidence" label but doesn't explain why

**Impact:**
- User sees "low confidence" but doesn't know required vs actual data points

**Severity:** MEDIUM  
**Fix Required:** Add tooltips explaining (e.g., "252+ snapshots needed for high confidence")

---

### Issue 37: Risk Panel Missing VaR Calculation Status
**Location:** panel_algo_health() -> risk section  
**Problem:** Shows VaR values but doesn't indicate if calculation was successful or if data was insufficient

**Impact:**
- User trusts VaR values even if calculation failed
- No indication of data quality

**Severity:** MEDIUM  
**Fix Required:** Add validation status flag for VaR calculations

---

### Issue 38: Economic Data Panel Doesn't Warn About Missing Indicators
**Location:** panel_economic_pulse(), lines 3835-3900  
**Problem:** Displays economic indicators but doesn't warn when data is missing/stale

**Impact:**
- User sees empty economic panel and assumes no data available
- Doesn't know if CPI/yield curve/SPY data failed to load

**Severity:** MEDIUM  
**Fix Required:** Display explicit "data not available" vs "fetching" states

---

## MEDIUM SEVERITY ISSUES

### Issue 39: Trade History Panel Doesn't Validate Trade Status Values
**Location:** panel_recent_trades()  
**Problem:** Displays trade status without validating it's in valid set

**Impact:**
- Invalid status values display without warning
- Could indicate corrupt data

**Severity:** LOW  
**Fix Required:** Validate status against enum, log invalid values

---

### Issue 40: Exposure Panel Doesn't Explain Halt Reasons
**Location:** panel_market_full(), exposure section  
**Problem:** Shows halt_reasons as array but doesn't explain what each means

**Impact:**
- User sees halt list but can't act on information

**Severity:** LOW  
**Fix Required:** Map halt_reason codes to human-readable explanations

---

### Issue 41: Signal Quality Metrics Not Displayed
**Location:** panel_signals_compact()  
**Problem:** Filters invalid signals but doesn't show how many were filtered

**Impact:**
- User doesn't know signal count is reduced due to quality issues
- No visibility into data quality

**Severity:** MEDIUM  
**Fix Required:** Display count of filtered signals

---

### Issue 42: Swing Score Threshold Inconsistency
**Location:** Multiple locations  
**Problem:** Swing score colored at different thresholds in different places

**Impact:**
- Inconsistent color coding confuses users
- Can't rely on color to indicate quality consistently

**Severity:** MEDIUM  
**Fix Required:** Centralize swing score thresholds (already partially done with get_swing_score_thresholds())

---

### Issue 43: No Indication of Calculation Staleness in Performance Metrics
**Location:** panel_perf_analytics()  
**Problem:** Displays rolling sharpe/sortino without indicating when they were last calculated

**Impact:**
- User doesn't know if metrics are current or from yesterday
- Can't assess reliability of decisions based on stale metrics

**Severity:** MEDIUM  
**Fix Required:** Show "calculated at: HH:MM ET" for all computed metrics

---

### Issue 44: Circuit Breaker Panel Doesn't Explain Threshold Overrides
**Location:** panel_algo_health() -> circuit breaker section  
**Problem:** Shows defaults used but doesn't explain consequences

**Impact:**
- Operator doesn't realize they're using unsafe defaults
- No action to fix stale config

**Severity:** MEDIUM  
**Fix Required:** Highlight that defaults are being used, suggest config update

---

### Issue 45: Risk Metrics Missing Data Source Indicators
**Location:** panel_algo_health() -> risk section  
**Problem:** Displays calculated metrics without indicating source (database vs calculated vs missing)

**Impact:**
- User doesn't know if metrics are from loader or calculated dynamically

**Severity:** LOW  
**Fix Required:** Add `_source` field to risk dict, display in UI

---

## PROCESS ISSUES

### Issue 46: No Unified Data Quality Status Panel
**Problem:** Data health checks scattered across multiple functions, no single source of truth

**Fix:** Create dedicated `panel_data_health()` showing:
- Fresh vs stale vs error for each critical table
- Age of latest data for each source
- Count of missing/invalid records

---

### Issue 47: No Operator Runbook for Data Quality Alerts
**Problem:** When data quality flags appear, operator doesn't know what to do

**Fix:** Create troubleshooting guide in steering/algo.md:
- What each stale/missing flag means
- Root cause for each condition
- Action to take to resolve

---

## Summary

| Issue | Severity | Type |
|-------|----------|------|
| 31 | MEDIUM | Hardcoded thresholds |
| 32 | HIGH | Default values hiding data |
| 33 | HIGH | Fallback prices not flagged |
| 34 | MEDIUM | Market health missing context |
| 35 | MEDIUM | Sector data missing visibility |
| 36 | MEDIUM | Confidence scores not explained |
| 37 | MEDIUM | Risk calculation status missing |
| 38 | MEDIUM | Economic data state unclear |
| 39 | LOW | Trade status not validated |
| 40 | LOW | Halt reasons not explained |
| 41 | MEDIUM | Filtered signal count hidden |
| 42 | MEDIUM | Swing score threshold inconsistency |
| 43 | MEDIUM | Calculation staleness not shown |
| 44 | MEDIUM | Config defaults not highlighted |
| 45 | LOW | Risk source not indicated |
| 46 | MEDIUM | No unified health panel |
| 47 | MEDIUM | No operator runbook |
| **TOTAL** | **17 Issues** | |

---

## Next Steps

1. ✅ Verify issues 24-30 (completed)
2. 🔄 Fix issues 31-47 (in progress)
3. 📋 Create operator runbook (issue 47)
4. 🧪 End-to-end testing with edge cases
5. ✨ Ensure all data quality issues surface explicitly

