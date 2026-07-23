# Scoring System End-to-End Audit - Session 302

**Date:** 2026-07-23  
**Goal:** Ensure score data flows end-to-end through loaders → calculation → orchestrator → APIs → dashboard  
**Status:** IN PROGRESS - Data pipeline running, API fixes implemented, verification pending

---

## Overview

The scoring system has been significantly enhanced with new input data and UI components. This audit verifies:
1. ✅ Loaders fetch required data
2. ✅ Calculations compute composite + 6 factors
3. ✅ Orchestrator uses scores for gating
4. ✅ APIs expose scores and inputs
5. ❓ Dashboard displays scores (TESTING)

---

## Critical Gaps Identified & Fixed

### Gap #1: API Response Missing Factor Input Objects (FIXED)
**Problem:** UI ScoresDashboard component expected `quality_inputs`, `momentum_inputs`, etc. objects, but API was only returning flat field names.  
**Evidence:** FactorInputs component (line 896) checks for input objects and shows "No detailed metrics available (API did not return inputs object)" when missing.  
**Fix:** Added `_build_factor_inputs()` function to scores.py API to build structured objects mapping flat fields to schema keys.  
**Commits:**
- 28d6239bb: Build factor input objects in API response
- 74dccd839: Correct momentum field mappings

### Gap #2: Data Coverage Issues (PENDING VERIFICATION)
**Audit Data (pre-refresh):**
| Metric | Coverage | Status |
|--------|----------|--------|
| positioning_metrics | 0.3% | 🔴 Upstream loader failure |
| momentum_metrics | 9.7% (1 day only) | ⚠️ Needs full lookback |
| value_metrics | 48.5% | ⚠️ PE data gaps |
| signal_quality_scores | 0.2% | ⚠️ Depends on buy_sell_daily |
| stock_scores | 89.6% | ✅ Good |
| quality_metrics | 90.4% | ✅ Good |
| stability_metrics | 95.0% | ✅ Excellent |
| growth_metrics | 85.1% | ✅ Good |

**Target:** >= 80% coverage per GOVERNANCE rules  
**Status:** Waiting for fresh data load to re-audit

---

## System Architecture Verified

### Loaders
All loaders confirmed present in `loaders/loader_registry.py`:
- ✅ load_value_quality_growth_metrics.py → value/quality/growth metrics
- ✅ load_risk_metrics_daily.py → momentum/stability metrics
- ✅ load_positioning_metrics.py → positioning metrics
- ✅ load_stock_scores.py → composite + 6 factor scores
- ✅ load_signal_quality_scores.py → signal quality scores
- ✅ load_buy_sell_daily.py → trading signals

### Score Calculation
Weights verified in load_stock_scores.py:
- quality: 25% (margins, profitability, leverage, growth)
- growth: 20% (revenue/EPS growth rates)
- value: 20% (valuation ratios - PE/PB/PS/PEG/FCF)
- positioning: 15% (institutional/insider ownership, short interest)
- stability: 12% (volatility, beta, debt/assets)
- momentum: 8% (price returns, technical indicators)
- **Total:** 100%

**Minimum metrics:** 4/6 required for diversity (prevents single-metric bias)  
**Completeness gate:** >= 70% for GOVERNANCE compliance

### UI Components
- ✅ ScoresDashboard.jsx: Main scores page with multiple tabs
- ✅ StockScoreAccordion.jsx: Factor detail display
- ✅ FactorInputs component: Displays metric inputs from API
- ✅ Schemas defined: QUALITY_SCHEMA, MOMENTUM_SCHEMA, VALUE_SCHEMA, GROWTH_SCHEMA, POSITIONING_SCHEMA, STABILITY_SCHEMA

### APIs
- ✅ /api/scores/stockscores: Returns all scores + 50+ metric fields
- ✅ Filters: data_completeness >= 70%, sp500_only option, symbol search
- ✅ Sorting: By composite_score, quality_score, momentum_score, etc.
- ✅ Field mapping: 50+ metric fields now organized into factor input objects

---

## Field Name Mappings (API → UI Schema)

### Quality Inputs
| API Field | Schema Key |
|-----------|-----------|
| roe_pct | return_on_equity_pct ✓ |
| roa_val | return_on_assets_pct ✓ |
| operating_margin_val | operating_margin_pct ✓ |
| net_margin_val | profit_margin_pct ✓ |
| debt_to_equity | debt_to_equity ✓ |
| current_ratio_val | current_ratio ✓ |
| quick_ratio_val | quick_ratio ✓ |
| interest_coverage_val | interest_coverage ✓ |
| debt_to_assets_val | debt_to_assets ✓ |
| (others) | Various - may be None if not in API response |

### Momentum Inputs
| API Field | Schema Key |
|-----------|-----------|
| current_price | current_price ✓ |
| price_vs_52w_high_val | price_vs_52w_high ✓ |
| price_vs_sma_50 | price_vs_sma_50 ✓ |
| price_vs_sma_200 | price_vs_sma_200 ✓ |
| momentum_3m_val | momentum_3m ✓ |
| momentum_6m_val | momentum_6m ✓ |
| momentum_12m_val | momentum_12_3 ✓ |
| tdd_rsi | rsi ✓ |
| tdd_macd | macd ✓ |

### Value Inputs
| API Field | Schema Key |
|-----------|-----------|
| trailing_pe | stock_pe ✓ |
| price_to_book | stock_pb ✓ |
| ps_ratio_val | stock_ps ✓ |
| peg_ratio_val | peg_ratio ✓ |
| fcf_yield_val | fcf_yield ✓ |
| dividend_yield | stock_dividend_yield ✓ |

### Growth, Positioning, Stability
- All field mappings implemented in scores.py `_build_factor_inputs()` function
- Unmapped schema keys will receive None and be skipped by UI

---

## Next Steps (PENDING)

1. **Wait for Data Pipeline:** Metrics pipeline should complete in 10-20 minutes
2. **Run Verification Tool:** `python verify_scoring_integration.py` to check data coverage
3. **Test Dashboard:** 
   - Open Scores Dashboard
   - Verify composite scores display
   - Click on a stock to expand
   - Verify factor input tables display (should no longer show "No detailed metrics available")
   - Check that all available metrics display with proper formatting
4. **Verify Coverage:**
   - Re-audit data coverage per the table above
   - Identify any remaining gaps
   - Investigate root causes of low-coverage metrics
5. **Dashboard Regression Testing:**
   - All 9 dashboard tabs functional
   - No JavaScript errors in console
   - Scores update correctly when sorting/filtering

---

## Known Issues to Investigate

1. **Momentum Metrics:** Only 1 day of data (9.7% coverage) - may need full lookback implementation
2. **Positioning Metrics:** 0.3% coverage - upstream 13F/Form4/FINRA loaders may have issues
3. **Value Metrics:** 48.5% coverage - PE ratio data gaps (yfinance API or coverage limitations)
4. **Signal Quality Scores:** 0.2% coverage - depends on buy_sell_daily population

---

## Files Modified (Session 302)

| File | Change | Commit |
|------|--------|--------|
| lambda/api/routes/scores.py | Build factor input objects | 28d6239bb, 74dccd839 |

## Testing Checklist

- [ ] Data pipeline completes successfully
- [ ] verify_scoring_integration.py shows >= 80% coverage for key metrics
- [ ] Dashboard loads without errors
- [ ] Factor inputs display correctly (not "No detailed metrics available")
- [ ] All 6 factor scores render
- [ ] Sort/filter by all score types works
- [ ] Signal quality gate (Phase 8) enforces min_signal_quality_score >= 75
- [ ] Portfolio/trader APIs return complete score data

---

## Related Documentation

- `CLAUDE.md` - Quick start guide (Session 301 production-ready status)
- `steering/GOVERNANCE.md` - Score requirements and trading gates
- `steering/DATA_LOADERS.md` - Loader infrastructure
- `verify_scoring_integration.py` - Automated verification tool

---

**Status:** Awaiting data load completion and dashboard verification  
**Owner:** Claude Code (Session 302)
