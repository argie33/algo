# Dashboard Pre-Computed Tables Architecture

This document describes the required pre-computed tables and loaders for the dashboard to function as a pure display layer instead of a calculation engine.

## Problem Statement

Dashboard currently calculates metrics in real-time that should be pre-computed:
- Equity curve metrics (Sharpe, Sortino, max drawdown, Calmar) — calculated from O(n²) snapshot iterations
- Sector allocations — aggregated per render from position iterations
- R-ladder distributions — bucketed per render
- Portfolio exposure metrics — calculated on demand

This creates performance issues and prevents historical tracking.

## Solution: 4 Pre-Computed Tables

# Comprehensive Issues Audit: Missing Pre-Computed Table Fields

**Date**: 2026-06-12  
**Status**: Ready for implementation  
**Scope**: Identify ALL missing pre-computed fields for dashboard

---

## EXECUTIVE SUMMARY

Dashboard currently **calculates in real-time** what should be **pre-computed**:

- **4 missing tables**: equity_curve_daily, sector_allocation_daily, r_ladder_distribution_daily, portfolio_exposure_daily
- **6 fetch functions** missing output fields
- **3 panels** performing real-time aggregations
- **Est. time**: 12-15 hours

---

## PART 1: MISSING PRE-COMPUTED TABLES

### Table 1: equity_curve_daily (NEW — REQUIRED)

**Purpose**: Daily portfolio metrics (Sharpe, Sortino, max drawdown, Calmar)  
**Updated**: EOD by loaders  
**Consumed**: fetch_perf(), panel_perf_metrics()  

| Column | Type | Source |
|--------|------|--------|
| date | DATE PK | Step Function |
| total_portfolio_value | DECIMAL(15,2) | Aggregation |
| rolling_sharpe_252d | DECIMAL(8,4) | Loader calc |
| rolling_sortino_252d | DECIMAL(8,4) | Loader calc |
| max_drawdown_ytd_pct | DECIMAL(8,4) | Loader calc |
| calmar_ratio | DECIMAL(8,4) | Loader calc |

**Current**: Dashboard calculates from snapshots (O(n²) Sharpe/Sortino)  
**Issue**: Real-time calculation every fetch  

**Missing in fetch_perf()**:
- sharpe_252d
- sortino_252d
- max_drawdown_ytd
- calmar_ratio

---

### Table 2: sector_allocation_daily (NEW — REQUIRED)

**Purpose**: Daily sector exposures  
**Updated**: Step Function (positions refresh)  
**Consumed**: panel_sector_compact(), fetch_portfolio()  

| Column | Type |
|--------|------|
| date | DATE |
| sector_name | VARCHAR(50) |
| symbol_count | INTEGER |
| total_position_value | DECIMAL(15,2) |
| pct_portfolio | DECIMAL(8,4) |

**PK**: (date, sector_name)  

**Current**: Dashboard iterates positions, groups by sector (O(n) per render)  
**Issue**: No historical tracking

---

### Table 3: r_ladder_distribution_daily (NEW — REQUIRED)

**Purpose**: R-multiple risk distribution  
**Updated**: Step Function (positions)  
**Consumed**: panel_risk_ladder()  

| Column | Type |
|--------|------|
| date | DATE |
| r_multiple_bucket | VARCHAR(20) |
| position_count | INTEGER |
| total_position_value | DECIMAL(15,2) |

**PK**: (date, r_multiple_bucket)  
**Buckets**: < -2R, -2R to -1R, -1R to 0R, 0R to 1R, 1R to 2R, > 2R

---

### Table 4: portfolio_exposure_daily (NEW — REQUIRED)

**Purpose**: Portfolio metrics (heat, concentration, win %)  
**Updated**: Step Function (positions)  
**Consumed**: fetch_portfolio()  

| Column | Type |
|--------|------|
| date | DATE PK |
| total_portfolio_value | DECIMAL(15,2) |
| total_position_value | DECIMAL(15,2) |
| cash_available | DECIMAL(15,2) |
| total_position_count | INTEGER |
| portfolio_heat | VARCHAR(20) |
| largest_position_pct | DECIMAL(8,4) |

---

## PART 2: DASHBOARD FETCH FUNCTIONS

### fetch_perf() — Missing Equity Curve Fields

**Currently**:
- Calculates Sharpe, Sortino, max drawdown (50+ lines)
- Returns equity_vals (raw array)

**Should Return** (from equity_curve_daily):
- sharpe_252d
- sortino_252d  
- max_drawdown_ytd
- calmar_ratio
- equity_dates (alignment)

**Fix**: Remove all calculation, fetch 1 row from table

---

### fetch_positions() — Calculates R-Multiple Per Render

**Issue**: Line 677-681 calculates R-multiple on every dashboard refresh

**Fix**: Pre-compute in algo_trades when trade entered

---

### fetch_portfolio() — Currently Empty

**Should Return**:
- portfolio (from portfolio_exposure_daily)
- sector_allocation (from sector_allocation_daily)
- r_ladder (from r_ladder_distribution_daily)

---

## PART 3: IMPLEMENTATION TIMELINE

### Phase 1: Schema (2h)
- Create 4 migration files
- Define indexes, constraints
- Test in staging

### Phase 2: Loaders (6h)
- equity_curve_loader (2h)
- sector_allocation_loader (2h)
- r_ladder_loader (1h)
- portfolio_exposure_loader (1h)
- Backfill 2025-01-01 to today

### Phase 3: Dashboard (3h)
- Update fetch_perf() (30min)
- Create fetch_sector_allocation() (30min)
- Create fetch_r_ladder() (30min)
- Update fetch_portfolio() (30min)
- Test (1h)

---

## SUCCESS CRITERIA

✅ All 4 tables populated daily  
✅ fetch_perf() ≤30 lines (no calc)  
✅ fetch_portfolio() returns all metrics  
✅ Historical data backfilled  
✅ All fetches < 100ms  
✅ No O(n) aggregations on render  

**Total**: 12-15 hours

