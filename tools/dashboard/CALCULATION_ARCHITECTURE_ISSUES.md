# Dashboard Architecture Audit: 45+ Calculation Engine Issues

**Status**: COMPREHENSIVE ANALYSIS  
**Date**: 2026-06-11  
**Scope**: Transform dashboard from a calculation engine to a pure display layer  

---

## THE CORE PROBLEM

The dashboard is currently functioning as a **calculation engine** instead of a **display layer**. It performs work that should happen elsewhere in the system:

```
Current (Wrong):
API/DB → Dashboard (fetch, calculate, validate, filter, transform) → Display

Correct Architecture:
API/DB (fetch, calculate, validate, filter, transform pre-computed) → Dashboard (display only) → User
```

### What Dashboard Should Do
- ✅ Fetch pre-computed data from API or database
- ✅ Format and render for terminal display
- ✅ Show alerts about data quality

### What Dashboard Currently Does (Wrong)
- ❌ Recalculates metrics that should come from API
- ❌ Filters raw data that should come pre-filtered
- ❌ Contains business logic (threshold rules, tier assessment)
- ❌ Validates data that should be clean at insert time
- ❌ Falls back to recalculating when pre-computed missing
- ❌ Has hardcoded configuration

---

## ARCHITECTURAL ISSUES BY CATEGORY

### Category 1: Fallback Calculation Logic (8 issues)
- C1-1: Grade Distribution Fallback (fetch_signals, lines 2040-2106) — HIGH
- C1-2: Signal Quality Filtering (fetch_signals, lines 2017-2038) — HIGH  
- C1-3: Win Rate Including Open Trades (fetch_perf, lines 1857-1859) — HIGH
- C1-4: Confidence Level Recalculation (fetch_perf, lines 1834-1837) — HIGH
- C1-5: Sector Ranking Filtering (fetch_sector_ranking) — MEDIUM
- C1-6: Near-Miss Signal Calculation (fetch_signals, lines 2108-2118) — MEDIUM
- C1-7: Exposure Factor Validation (fetch_exposure_factors) — MEDIUM
- C1-8: Risk Metrics Staleness Check (fetch_risk_metrics) — MEDIUM

### Category 2: Data Filtering & Transformation (10 issues)
- C2-1: Trade Status Validation (panel_recent_trades) — HIGH
- C2-2: Missing Price Fallback (fetch_positions) — HIGH
- C2-3: Sector Data Fallback (fetch_positions) — MEDIUM
- C2-4: P&L Dollar Amount Rounding (fetch_perf, lines 1868-1871) — LOW
- C2-5: Equity Curve Calculation (fetch_perf) — MEDIUM
- C2-6: Sector Position Data Aggregation (panel_sector_compact) — MEDIUM
- C2-7: Signal Sorting & Limiting (fetch_signals, lines 2014-2015) — LOW
- C2-8: Portfolio Exposure Aggregation (fetch_portfolio) — MEDIUM
- C2-9: Recent Trades List Filtering (fetch_recent_trades) — LOW
- C2-10: Swing Score Range Queries (fetch_signals, lines 2124-2129) — LOW

### Category 3: Hardcoded Configuration (8 issues)
- C3-1: MIN_QUALITY_SCORE = 40 (line 2026) — HIGH
- C3-2: METRICS_CALCULATION_MAX_AGE_MINUTES = 120 (line 36) — HIGH
- C3-3: Grade Thresholds Hardcoded Defaults — MEDIUM
- C3-4: Market Health Thresholds Hardcoded — MEDIUM
- C3-5: Risk Thresholds Hardcoded Defaults — MEDIUM
- C3-6: Signal Thresholds Hardcoded Defaults — MEDIUM
- C3-7: UI Display Thresholds (acceptable with defaults) — LOW
- C3-8: Near-Miss Score Range Hardcoded (lines 2108-2111) — MEDIUM

### Category 4: Data Quality Issues (7 issues)
- C4-1: NULL Handling Inconsistency — MEDIUM
- C4-2: Missing Data Indicated by Default Values — MEDIUM
- C4-3: Stale Data Not Surfaced Consistently — MEDIUM
- C4-4: Incomplete Row Handling (sector data) — MEDIUM
- C4-5: Schema Validation Missing Type Checks (lines 710-850) — HIGH
- C4-6: Trade Status Not Validated — HIGH
- C4-7: Portfolio Completeness Not Verified — MEDIUM

### Category 5: Business Logic in Display Layer (8 issues)
- C5-1: Confidence Level Override (fetch_perf, lines 1834-1837) — HIGH
- C5-2: Grade Classification Logic (fetch_signals, lines 2094-2105) — HIGH
- C5-3: Near-Miss Classification (fetch_signals, lines 2108-2118) — MEDIUM
- C5-4: Win Rate Calculation Rules (fetch_perf, lines 1857-1859) — HIGH
- C5-5: Signal Quality Threshold (fetch_signals, lines 2026-2035) — HIGH
- C5-6: Sector Grouping Logic (panel_sector_compact) — MEDIUM
- C5-7: Stale Data Threshold (multiple locations) — MEDIUM
- C5-8: Data Quality Aggregation (load_all) — MEDIUM

### Category 6: Missing Pre-Computed Fields (6 issues)
- C6-1: Swing Score Classification Missing — MEDIUM
- C6-2: Signal Grade Missing — MEDIUM
- C6-3: Position Risk Flags Missing — MEDIUM
- C6-4: Equity Curve Values Missing — MEDIUM
- C6-5: Sector Summary Missing — MEDIUM
- C6-6: Data Quality Status Missing — MEDIUM

### Category 7: Error Handling Issues (4 issues)
- C7-1: Database Connection Retry Logic in Dashboard — HIGH
- C7-2: Fallback Data Source Selection — HIGH
- C7-3: Missing Data Compensation — MEDIUM
- C7-4: Silent Error Suppression — MEDIUM

### Category 8: Inconsistent APIs (3 issues)
- C8-1: Stale Alerts Format Inconsistent — MEDIUM
- C8-2: Error Indication Format Inconsistent — MEDIUM
- C8-3: Confidence Level Format Inconsistent — MEDIUM

---

## ISSUE SUMMARY

| Category | Count | HIGH | MEDIUM | LOW |
|----------|-------|------|--------|-----|
| Fallback Calculation | 8 | 4 | 4 | 0 |
| Data Transform | 10 | 2 | 5 | 3 |
| Hardcoded Config | 8 | 2 | 5 | 1 |
| Data Quality | 7 | 2 | 5 | 0 |
| Business Logic | 8 | 4 | 4 | 0 |
| Missing Fields | 6 | 0 | 6 | 0 |
| Error Handling | 4 | 2 | 2 | 0 |
| Inconsistent APIs | 3 | 0 | 3 | 0 |
| **TOTAL** | **54** | **16** | **34** | **4** |

---

## REMEDIATION ROADMAP

### Phase 1: API Layer Enhancement
- Ensure all data is pre-computed at source
- Never return fallback values or calculated metrics
- Implement consistent `_data_quality`, `_error`, `_source` flags
- Make config table mandatory (no hardcoded defaults)

### Phase 2: Database Layer Constraints
- Add NOT NULL constraints on required fields
- Add CHECK constraints for enums (trade status, grades, etc.)
- Ensure pre-computed tables always exist and are fresh
- Use triggers to validate data integrity

### Phase 3: Dashboard Layer Refactor
- All fetch_* functions: fetch only, never calculate
- All panel_* functions: format display only, never validate
- No hardcoded configuration
- No business logic in presentation layer

---

## HIGH-SEVERITY ISSUES (16 total)

Critical issues that allow invalid/stale data to reach the operator:

1. C1-1: Grade Distribution Fallback — Hides pre-computed table failures
2. C1-2: Signal Quality Filtering — Quality rules in dashboard
3. C1-3: Win Rate Including Open — Metric calculation in dashboard
4. C1-4: Confidence Override — Two sources of truth for confidence
5. C2-1: Trade Status Validation — Invalid trade statuses not caught
6. C2-2: Missing Price Fallback — P&L calculations use stale prices
7. C3-1: MIN_QUALITY_SCORE Hardcoded — Can't tune without code change
8. C3-2: METRICS_MAX_AGE Hardcoded — Can't tune without code change
9. C4-5: Schema Type Validation Missing — Type errors not caught until runtime
10. C4-6: Trade Status Validation Missing — Invalid data persists
11. C5-1: Confidence Override Logic — Dashboard overrides API values
12. C5-2: Grade Classification — Grading logic in dashboard
13. C5-4: Win Rate Rules — Win rate calculation in dashboard
14. C5-5: Quality Threshold — Signal filtering in dashboard
15. C7-1: DB Connection Retry — Connection logic in dashboard
16. C7-2: Fallback Source Selection — Chooses API vs DB in dashboard

