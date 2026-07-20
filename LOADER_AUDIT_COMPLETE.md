# COMPREHENSIVE LOADER AUDIT - Session 291
**Date:** 2026-07-20  
**Status:** Complete Investigation (No Changes Made Yet)

---

## EXECUTIVE SUMMARY

**30 loader files on disk. 22 active. 8 deprecated/orphaned.**

### Issues Found (No Decisions Made - For Review Only)

1. **8 Deprecated/Orphaned Files** - On disk, not in pipeline
2. **1 Inefficient Consolidation** - Single file runs twice 
3. **3 Active Consolidations** - Verified working correctly
4. **4 Tables Still Monitored** - Old tables still in health checks

---

## PART A: ACTIVE LOADERS (22 Total - All Currently Running)

| Loader File | Purpose | Data Sources | Status |
|---|---|---|---|
| load_prices.py | OHLCV daily bars | Alpaca SIP | ✅ Core |
| load_technical_indicators.py | SMA, RSI, MACD, etc | Prices | ✅ Core |
| load_trend_analysis.py | Trend patterns | Prices + Tech | ✅ Core |
| load_economic_data.py | FRED + DXY | FRED API | ✅ Core |
| load_financial_statements.py | SEC financials | SEC EDGAR | ✅ Core |
| load_sec_valuations.py | PE/PB/PS/PEG/FCF | SEC + Prices | ✅ Core |
| load_market_status_daily.py | **CONSOLIDATED**: VIX, breadth, yields, regime, sentiment | Multiple | ✅ Consolidated |
| load_value_quality_growth_metrics.py | **CONSOLIDATED**: Value/Quality/Growth scores | SEC | ✅ Consolidated |
| load_sector_industry_daily.py | **CONSOLIDATED**: Sector perf, rankings, industry data | Prices + Scores | ✅ Consolidated |
| load_company_info_sec.py | Company master data | SEC EDGAR | ✅ SEC Phase 5a |
| load_earnings_calendar_sec.py | Filing dates | SEC EDGAR | ✅ SEC Phase 5b |
| load_risk_metrics_daily.py | **RUNS 2x**: Momentum + Stability | Prices | ⚠️ INEFFICIENT |
| load_positioning_metrics.py | Holdings concentration | SEC data | ✅ Active |
| load_short_interest_finra.py | Short interest | FINRA | ✅ Active |
| load_stock_scores.py | 6-factor composite | All metrics | ✅ Core |
| load_buy_sell_daily.py | Trading signals | Technical + Scores | ✅ Core |
| load_algo_metrics_daily.py | Algorithm metrics | Trading data | ✅ Active |
| load_market_constituents.py | Market symbols | Reference | ✅ Active |
| load_institutional_holdings_13f.py | Institutional holdings | SEC Form 13F | ✅ SEC Phase 2 |
| load_insider_holdings_sec.py | Insider holdings | SEC Form 4/5 | ✅ SEC Phase 2 |
| load_sec_cash_flow_metrics.py | Working capital, capex | SEC statements | ✅ Active |
| load_sec_segment_metrics.py | Segment data | SEC statements | ✅ Active |

**VERDICT:** All 22 are actively configured and running. None can be safely removed without breaking trades.

---

## PART B: DEPRECATED/ORPHANED FILES (8 Total - On Disk, Not Running)

| File | Status | Reason | Risk of Deletion |
|---|---|---|---|
| load_yfinance_snapshot.py | DEPRECATED | Yfinance removed (Session 275+) | **SAFE** - Not used anywhere |
| load_yfinance_derived_metrics.py | DEPRECATED | Yfinance removed (Session 275+) | **SAFE** - Not used anywhere |
| load_market_sentiment.py | DEPRECATED | Consolidated into load_market_status_daily.py | **SAFE** - Not used anywhere |
| load_market_exposure_daily.py | DEPRECATED | Consolidated into load_market_status_daily.py | ⚠️ **TABLE STILL MONITORED** - See below |
| load_sector_performance.py | DEPRECATED | Consolidated into load_sector_industry_daily.py | **SAFE** - Table still written by consolidated loader |
| load_sector_rankings.py | DEPRECATED | Consolidated into load_sector_industry_daily.py | **SAFE** - Table still written by consolidated loader |
| load_market_cap_computed.py | ORPHANED | Unknown origin | **UNKNOWN** - See investigation below |
| load_price_extremes.py | ORPHANED | Unknown origin | **SAFE** - Not referenced anywhere |

**VERDICT:** 6 safe to delete. 2 require investigation.

---

## PART C: INVESTIGATION FINDINGS

### 1. Market Exposure Consolidation Status

**Finding:** `market_exposure_daily` table is STILL actively referenced:
- Monitoring config: `algo/infrastructure/config/data_patrol_config.py`
- Health checks: `algo/orchestration/database_health_monitor.py` (2 references)

**Verification:** `load_market_status_daily.py` confirms it writes market_exposure_daily:
```python
# Line 20: "- market_exposure_daily (regime, exposure %, factors)"
# Line 156-162: Writes all market_exposure_daily fields
```

**Status:** ✅ Consolidation working correctly. Table is active.

### 2. Sector Consolidation Status

**Finding:** `load_sector_industry_daily.py` writes to ALL THREE tables:
- sector_performance (daily % returns)
- sector_ranking (daily rankings + momentum)  
- industry_ranking (industry-level rankings)

**Verification:** Code confirms triple-write pattern (Lines 163, 201, 264-284):
```python
INSERT INTO sector_performance...
INSERT INTO sector_ranking...
INSERT INTO industry_ranking...
```

**Status:** ✅ Consolidation working correctly. All tables active.

### 3. Risk Metrics Inefficiency

**Problem:** `load_risk_metrics_daily.py` is configured to run TWICE:

| Task Name | Table | Timeout | Parallelism |
|---|---|---|---|
| stability_metrics | momentum_metrics (primary) + stability_metrics (side effect) | 4200s | 2 |
| momentum_metrics | momentum_metrics (primary) + stability_metrics (side effect) | 1800s | 2 |

**Impact:** 
- Same file runs twice with same parallelism
- Computes same data twice
- Different timeouts (4200s vs 1800s) suggest old per-metric separation
- Wasted CPU/time since consolidated loader handles both in one pass

**Code Analysis:** File header confirms intentional consolidation (Lines 2-14):
```
Consolidates load_momentum_metrics.py + load_stability_metrics.py into single invocation:
- Computes momentum (1m/3m/6m/12m) from price_daily
- Computes stability (30d/60d/252d vol + beta) from price_daily
- Writes to momentum_metrics table AND stability_metrics table in parallel
```

**Status:** ⚠️ CONSOLIDATION EXISTS but MISCONFIGURED - runs twice instead of once.

### 4. Market Cap Computed - Unknown Purpose

**Finding:** `load_market_cap_computed.py` exists but:
- Not imported anywhere
- Only self-referenced in its own file
- Not clear what it computes or if it's used

**Status:** ❓ NEEDS INVESTIGATION - Check if table is used in trading logic

---

## PART D: CONSOLIDATION VERIFICATION

### Consolidation #1: Market Status Daily ✅
- **Replaces:** market_health_daily, market_exposure_daily, market_sentiment (3 files)
- **Status:** ✅ VERIFIED WORKING
- **Evidence:** Writes all 3 table outputs correctly, still actively monitored

### Consolidation #2: Value Quality Growth ✅
- **Replaces:** value_metrics, quality_metrics, growth_metrics (3 files)
- **Status:** ✅ VERIFIED WORKING
- **Evidence:** Code merged, writes correct tables, used by stock_scores

### Consolidation #3: Sector Industry ✅
- **Replaces:** sector_performance, sector_ranking, industry_ranking (3 files)
- **Status:** ✅ VERIFIED WORKING
- **Evidence:** Writes all 3 tables in single pass

### Consolidation #4: Risk Metrics ⚠️ MISCONFIGURED
- **Intent:** Consolidate momentum + stability into single pass
- **Status:** ⚠️ CONSOLIDATION EXISTS but RUNS TWICE
- **Problem:** Terraform configures as 2 separate tasks, both run full loader
- **Impact:** Wasted compute - should run once, not twice

---

## PART E: SAFE DELETIONS (No Blockers)

**Can be safely deleted today:**

1. `load_yfinance_snapshot.py` - Not imported, yfinance removed
2. `load_yfinance_derived_metrics.py` - Not imported, yfinance removed
3. `load_price_extremes.py` - Not referenced anywhere
4. `load_sector_performance.py` - Deprecated (output still generated by load_sector_industry_daily.py)
5. `load_sector_rankings.py` - Deprecated (output still generated by load_sector_industry_daily.py)
6. `load_market_sentiment.py` - Deprecated (output still generated by load_market_status_daily.py)

**Requires Investigation Before Deletion:**

7. `load_market_cap_computed.py` - Unknown if table is used
8. `load_market_exposure_daily.py` - Has deprecated loader file, but table is still active (generated by market_status_daily)

---

## PART F: RECOMMENDATIONS (For Your Decision)

### Low Risk Changes (Safe to proceed)
- Delete 6 confirmed orphaned loaders (yfinance + unused)
- Update terraform comments to mark consolidations clearly

### Medium Risk Changes (Requires careful testing)
- Fix risk_metrics double-run inefficiency (run once instead of twice)
- Remove old loader files after verifying terraform consolidation

### Requires Investigation First
- Verify if market_cap_computed table is used anywhere in trading logic
- Verify consolidations still work after cleanup

---

## SUMMARY TABLE

| Category | Count | Status | Action |
|---|---|---|---|
| Active Loaders | 22 | ✅ All working | No changes needed |
| Consolidations | 3 | ✅ Verified | No changes needed |
| Misconfigured | 1 | ⚠️ Risk metrics runs 2x | Needs fix |
| Orphaned/Safe | 6 | ✅ Safe to delete | Ready to delete |
| Unknown | 2 | ❓ Needs investigation | Hold for now |

---

## AUDIT COMPLETE

This audit provides full visibility into the loader situation. No changes have been made yet. Ready for prudent decision-making based on complete information.

