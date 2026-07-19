# Complete Data Loader Architecture Audit

**Date:** 2026-07-17  
**Session:** 217  
**Objective:** Trace actual data consumption, identify critical vs optional data, map current architecture, and recommend clean design.

---

## EXECUTIVE SUMMARY

The system has **evolved through consolidation but retains some redundant loaders**. Current state:

### ✅ What's Working Well:
- **Price data pipeline** (stock_prices_daily → technical_data_daily → signals): Clean, fail-closed
- **Financial statement loading** (consolidated FinancialDataLoaders): Single unified task
- **Metric consolidation** (value_quality_growth_metrics): Merges 2 loaders into 1 atomic operation
- **Phase-based architecture**: Clear dependency ordering in orchestrator (9 phases)

### ⚠️ What Needs Cleanup:
- **load_quality_growth_metrics.py**: ORPHANED - not called in terraform, replaced by load_value_quality_growth_metrics.py
- **load_market_health_daily.py**: ORPHANED - consolidated into load_market_status_daily.py
- **load_yfinance_derived_metrics.py**: PARTIALLY USED - only positioning_metrics actually needed (company_profile/analyst_sentiment are dashboard-only enrichment)
- **Redundant consolidations**: Multiple files for same data (market_health vs market_status)

### 🎯 Trading vs Dashboard Data Split:
- **Trading Critical**: price_daily, technical_data_daily, stock_scores, value_metrics
- **Trading Should-Have**: quality_metrics, growth_metrics, positioning_metrics, stability_metrics
- **Dashboard Only**: company_profile, analyst_sentiment_analysis, earnings_calendar

---

## PART 1: DATA CONSUMPTION TRACE

### 1.1 - Stock Scoring (load_stock_scores.py)

**INPUT TABLES CONSUMED:**
```sql
-- Required (FAIL-FAST if missing):
SELECT symbol, roe, roa, operating_margin, net_margin, debt_to_equity, 
       current_ratio, quick_ratio, quality_score, data_unavailable FROM quality_metrics

SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y,
       eps_growth_1y, eps_growth_3y, eps_growth_5y, data_unavailable FROM growth_metrics

SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield,
       data_unavailable FROM value_metrics

SELECT symbol, institutional_ownership, insider_ownership, short_interest_percent,
       data_unavailable FROM positioning_metrics

SELECT symbol, volatility_252d, volatility_60d, volatility_30d, beta, data_unavailable
       FROM stability_metrics

SELECT MAX(date) FROM price_daily  -- For momentum calculation lookback
```

**OUTPUT TABLE:**
- stock_scores (writes: composite_score, momentum_score, quality_score, growth_score, value_score, positioning_score, stability_score, rs_percentile, data_completeness)

**CRITICAL RULES:**
- Minimum 3/6 metrics required for valid score (50% completeness)
- All 5 metric tables must have ≥30% coverage or stock_scores halts with RuntimeError
- Data marked data_unavailable=TRUE is excluded from scoring (graceful degradation)

---

### 1.2 - Signal Generation (load_buy_sell_daily.py + BuySignalGenerator)

**INPUT TABLES CONSUMED:**
```sql
SELECT symbol, date, open, high, low, close, volume, sma_50, sma_200, 
       volume, atr, rsi, macd, macd_signal, ema_21, adx, mansfield_rs 
FROM technical_data_daily

SELECT DISTINCT ON (symbol) symbol, close FROM price_daily 
ORDER BY symbol, date DESC  -- Latest price for momentum calc
```

**OUTPUT TABLE:**
- buy_sell_daily (writes: symbol, date, signal_type, signal_strength, buylevel, stoplevel, entry_score)

**CRITICAL RULES:**
- Requires 95%+ complete OHLCV data (Minervini standard)
- DOES NOT read stock_scores (signal generation independent of composite scores)
- DOES NOT read positioning/quality/growth metrics (pure technical + price-based)

---

### 1.3 - Trend Analysis (load_trend_analysis.py)

**INPUT TABLES CONSUMED:**
```sql
SELECT symbol, date, rsi_14, sma_50, sma_200, roc_20d, roc_60d, roc_252d
FROM technical_data_daily
```

**OUTPUT TABLE:**
- trend_template_data (writes: symbol, minervini_score, weinstein_stage, date)

**CRITICAL RULES:**
- Output used for market regime classification (Phase 1 breadth calculation)
- Does NOT depend on metrics (quality/growth/value/positioning)

---

### 1.4 - Dashboard API Data Consumption

**Key Routes Reading Metric Data:**

#### /financials endpoint:
```sql
SELECT vm.pe_ratio, vm.pb_ratio, vm.ps_ratio, vm.peg_ratio, vm.dividend_yield,
       qm.roe, qm.operating_margin, qm.net_margin, qm.debt_to_equity,
       pm.institutional_ownership, pm.insider_ownership, pm.short_interest_pct,
       cp.sector, cp.industry
FROM value_metrics vm
LEFT JOIN quality_metrics qm ON vm.symbol = qm.symbol
LEFT JOIN company_profile cp ON vm.symbol = cp.ticker
LEFT JOIN positioning_metrics pm ON vm.symbol = pm.symbol
```

#### /scores endpoint:
```sql
SELECT composite_score, momentum_score, quality_score, growth_score, 
       value_score, positioning_score, stability_score
FROM stock_scores
```

#### /positions endpoint:
```sql
SELECT cp.ticker, cp.sector, cp.short_name 
FROM company_profile cp  -- For enrichment only
```

**DASHBOARD ONLY (NOT USED BY TRADING):**
- analyst_sentiment_analysis (analyst recommendation counts)
- earnings_calendar (next earnings date - used for UI, not trading)
- company_profile.industry (enrichment only)

---

### 1.5 - Orchestrator Phase Data Dependencies

| Phase | Data Read | Data Written | Critical? |
|-------|-----------|--------------|-----------|
| Phase 1 (Data Freshness) | price_daily, market_health_daily, technical_data_daily, value/quality/growth/positioning/stability_metrics | orchestrator_execution_log | CRITICAL |
| Phase 2 (Circuit Breakers) | stock_scores, algo_positions | orchestrator_execution_log | HIGH |
| Phase 3 (Position Monitor) | algo_positions, algo_trades | orchestrator_execution_log | HIGH |
| Phase 4 (Reconciliation) | algo_positions, market prices | orchestrator_execution_log | HIGH |
| Phase 5 (Exposure Policy) | market_exposure_daily, algo_positions | orchestrator_execution_log | MEDIUM |
| Phase 6 (Exit Execution) | algo_positions, buy_sell_daily signals | algo_trades | HIGH |
| Phase 7 (Signal Generation) | price_daily, technical_data_daily, stock_scores, value_metrics | algo_signals | CRITICAL |
| Phase 8 (Entry Execution) | algo_signals, market prices | algo_positions, algo_trades | HIGH |
| Phase 9 (Reconciliation) | algo_trades, market prices | algo_audit_log | HIGH |

---

## PART 2: CRITICAL vs OPTIONAL DATA ASSESSMENT

### TIER 1 - MUST-HAVE FOR TRADING (System Halts Without):
1. **price_daily** - Stock OHLCV prices
   - Used by: Phase 7 momentum, signal generation, all entry/exit logic
   - Source: yfinance (via load_prices)
   - Failure Mode: Phase 1 HALTS orchestrator if <75% symbol coverage

2. **technical_data_daily** - Indicators (RSI, MACD, ATR, SMAs)
   - Used by: Signal generation (buy_sell_daily), Phase 7 entry filtering
   - Source: Computed from price_daily
   - Failure Mode: Phase 1 HALTS orchestrator if stale/incomplete

3. **stock_scores** - Composite signal quality metric
   - Used by: Phase 7 signal filtering (min score threshold), Phase 2 circuit breakers
   - Source: Aggregated from value/quality/growth/positioning/stability metrics
   - Failure Mode: Phase 1 HALTS if no scores computed (min coverage threshold)

### TIER 2 - SHOULD-HAVE FOR OPTIMAL TRADING (Degrades Gracefully):
1. **value_metrics** (PE, PB, PS, PEG, FCF, dividend yield)
   - Used by: stock_scores quality filtering, dashboard fundamentals
   - Source: SEC (via load_sec_valuations) + yfinance (dividend)
   - Failure Mode: stock_scores includes "unavailable" markers, Phase 1 WARNING

2. **quality_metrics** (ROE, margins, debt ratios)
   - Used by: stock_scores quality factor, dashboard fundamentals
   - Source: SEC financial statements (load_quality_growth_metrics)
   - Failure Mode: stock_scores includes "unavailable" markers, Phase 1 WARNING

3. **growth_metrics** (revenue/EPS growth 1y/3y/5y)
   - Used by: stock_scores growth factor
   - Source: SEC financial statements
   - Failure Mode: stock_scores includes "unavailable" markers, Phase 1 WARNING

4. **positioning_metrics** (institutional/insider ownership, short interest)
   - Used by: stock_scores positioning factor
   - Source: yfinance (via load_yfinance_derived_metrics)
   - Failure Mode: stock_scores includes "unavailable" markers, Phase 1 WARNING

5. **stability_metrics** (volatility, beta)
   - Used by: stock_scores stability factor, risk management
   - Source: Computed from price history + yfinance beta
   - Failure Mode: stock_scores includes "unavailable" markers, Phase 1 WARNING

### TIER 3 - NICE-TO-HAVE (Dashboard Enrichment Only):
1. **company_profile** (sector, industry, exchange, website)
   - Used by: Dashboard display, sector allocation, NOT trading logic
   - Source: yfinance (via load_yfinance_derived_metrics)
   - Failure Mode: Dashboard shows missing sector (handled gracefully), no trading impact

2. **analyst_sentiment_analysis** (analyst counts, recommendation)
   - Used by: Dashboard signal confirmation enrichment ONLY
   - Source: yfinance
   - Failure Mode: Dashboard missing analyst counts, no trading impact

3. **earnings_calendar** (next earnings date)
   - Used by: Dashboard UI, optional blackout window (Phase 5 checks market_exposure_daily instead)
   - Source: yfinance
   - Failure Mode: Dashboard missing earnings dates, no trading impact

4. **algo_metrics_daily** (portfolio statistics)
   - Used by: Dashboard portfolio widget ONLY
   - Source: Computed from audit_log
   - Failure Mode: Dashboard missing portfolio stats, no trading impact

---

## PART 3: DATA SOURCES & AVAILABILITY

### Primary Sources:
| Source | Cost/Day | Rate Limit | Fallback | Used For |
|--------|----------|-----------|----------|----------|
| **SEC EDGAR** | Free | 10 req/s | None | Income statements, balance sheets, cash flow |
| **yfinance** | Free (but rate-limited) | ~1500 req/day (~10-minute aggregate) | Fallbacks in loader | Prices, valuations, beta, volatility, sector info |
| **FRED** | Free | Unlimited | None | Economic data (DXY, inflation) |
| **Market Data** | Free via yfinance | Rate-limited | OHLC fallback | Prices, volumes |

### What Data CANNOT Be Replaced:
- **Price OHLCV**: yfinance only option (no free alternative)
- **SEC Financials**: Must have SEC data or cannot compute quality/growth/valuations
- **Beta/Volatility**: yfinance or must compute from scratch (slow)

### What Data Could Be Replaced:
- **company_profile** (sector/industry): Could load once, update rarely
- **analyst_sentiment**: Optional enrichment only
- **earnings_calendar**: Could hardcode, update monthly

---

## PART 4: CURRENT LOADER INVENTORY

### ACTIVELY DEPLOYED (Called in Terraform):
```
✅ load_market_constituents.py          → stock_symbols
✅ load_prices.py                       → price_daily, price_weekly, price_monthly
✅ load_technical_indicators.py         → technical_data_daily
✅ load_trend_analysis.py               → trend_template_data
✅ load_yfinance_snapshot.py            → yfinance_snapshot
✅ load_financial_statements.py         → annual_income_statement, annual_balance_sheet, annual_cash_flow
✅ load_sec_valuations.py               → sec_valuations (computed from financials)
✅ load_value_quality_growth_metrics.py → value_metrics, quality_metrics, growth_metrics (CONSOLIDATED)
✅ load_yfinance_derived_metrics.py     → positioning_metrics, company_profile, earnings_calendar, analyst_sentiment_analysis
✅ load_risk_metrics_daily.py           → stability_metrics
✅ load_stock_scores.py                 → stock_scores
✅ load_buy_sell_daily.py               → buy_sell_daily
✅ load_market_status_daily.py          → market_health_daily, market_sentiment, market_exposure_daily
✅ load_sector_rankings.py              → sector_ranking
✅ load_sector_industry_daily.py        → sector_performance
✅ load_algo_metrics_daily.py           → algo_metrics_daily
✅ load_economic_data.py                → economic_data
```

### ORPHANED/OBSOLETE LOADERS (Still in repo, NOT called in terraform):
```
❌ load_quality_growth_metrics.py       → [REPLACED BY load_value_quality_growth_metrics.py]
❌ load_market_health_daily.py          → [CONSOLIDATED INTO load_market_status_daily.py]
```

### REDUNDANT RESPONSIBILITIES:
```
⚠️  load_yfinance_derived_metrics.py    → Outputs 5 tables, only positioning_metrics is trading-critical
                                         → company_profile, analyst_sentiment, earnings_calendar are dashboard-only
                                         → Could be split: critical (positioning) vs dashboard (company_profile)
```

---

## PART 5: CURRENT DATA FLOW PROBLEMS

### Problem 1: Consolidation Incompleteness
**Issue**: load_quality_growth_metrics.py still exists but isn't called. Creates confusion about which loader to use.

**Root Cause**: Session 204-208 consolidated loaders but didn't delete old files.

**Impact**: Developers might accidentally call the wrong loader; maintenance confusion.

**Solution**: DELETE load_quality_growth_metrics.py (already replaced by load_value_quality_growth_metrics.py)

---

### Problem 2: Dashboard Data Mixed with Trading Data
**Issue**: load_yfinance_derived_metrics.py writes to 5 tables:
- positioning_metrics (TRADING-CRITICAL for stock_scores)
- company_profile (DASHBOARD ONLY - enrichment)
- earnings_calendar (DASHBOARD ONLY - enrichment)
- analyst_sentiment_analysis (DASHBOARD ONLY - enrichment)

**Root Cause**: Session 204 consolidated 6 loaders into 1 for efficiency, but mixed concerns.

**Impact**: Terraform shows all 5 tables as "metrics" when 4 are actually dashboard enrichment. Harder to understand what's critical for trading.

**Solution Options**:
- **Option A (Cleaner)**: Split load_yfinance_derived_metrics into:
  - load_positioning_metrics.py (CRITICAL - feeds stock_scores)
  - load_dashboard_enrichment.py (OPTIONAL - company_profile, analyst_sentiment, earnings_calendar)
- **Option B (Current)**: Keep consolidated but document that only positioning_metrics is trading-critical

---

### Problem 3: Unclear Data Freshness Requirements
**Issue**: Phase 1 checks ALL metric tables (value, quality, growth, positioning, stability) as HALT-level freshness checks.

**Reality**: 
- value_metrics is CRITICAL (PE/PB filtering)
- quality_metrics is SHOULD-HAVE but can degrade gracefully
- growth_metrics is SHOULD-HAVE but can degrade gracefully  
- positioning_metrics is NICE-TO-HAVE (optional signal enhancement)
- stability_metrics is NICE-TO-HAVE (optional risk management)

**Root Cause**: Phase 1 treats all metrics equally instead of tiering criticality.

**Impact**: Pipeline halts unnecessarily if SEC data is incomplete (affects quality/growth); positioning/stability optional.

**Solution**: Tiered Phase 1 validation:
- HALT if: price_daily stale, technical_data_daily stale, stock_scores empty
- WARN if: value_metrics incomplete, quality/growth incomplete (ok for trading to proceed), positioning/stability optional

---

## PART 6: CORRECT ARCHITECTURE (RECOMMENDED)

### CLEAN DATA LOADER HIERARCHY:

```
┌─────────────────────────────────────────────────────────────────┐
│              CLEAN LOADER ARCHITECTURE v2.0                      │
└─────────────────────────────────────────────────────────────────┘

LAYER 1: FOUNDATION (Universe + Prices) - CRITICAL
─────────────────────────────────────────────────
Inputs:  None
Outputs: stock_symbols, price_daily, price_weekly, price_monthly
Loaders: load_market_constituents, load_prices
Failure: HALT (system cannot proceed)
Timeout: 30min (prices) + 5min (symbols)

     ↓

LAYER 2: SIGNALS & MARKET STATE - CRITICAL
────────────────────────────────────────────
Inputs:  price_daily
Outputs: technical_data_daily, trend_template_data, market_health_daily
Loaders: load_technical_indicators, load_trend_analysis, load_market_status_daily
Failure: HALT (signal generation needs technical data)
Timeout: 60min (technical) + 15min (trend) + 15min (market health)

     ↓

LAYER 3: SOURCE DATA ENRICHMENT - OPTIONAL (Graceful Degradation)
──────────────────────────────────────────────────────────────────
Inputs:  None
Outputs: yfinance_snapshot, annual_income_statement, annual_balance_sheet, 
         annual_cash_flow, sec_valuations
Loaders: load_yfinance_snapshot, load_financial_statements, load_sec_valuations
Failure: WARN (stock_scores will have data_unavailable markers, but trading proceeds)
Timeout: 120min (financial) + 120min (yfinance) + 30min (valuations)

     ↓

LAYER 4: COMPUTED METRICS - OPTIONAL (Graceful Degradation)
────────────────────────────────────────────────────────────
Inputs:  financial_statements, yfinance_snapshot, sec_valuations
Outputs: value_metrics, quality_metrics, growth_metrics, 
         positioning_metrics, stability_metrics
Loaders: load_value_quality_growth_metrics, load_yfinance_derived_metrics,
         load_risk_metrics_daily (split positioning_metrics vs company_profile)
Failure: WARN (metric tables have data_unavailable markers, trading continues)
Timeout: 120min (value/quality/growth) + 60min (positioning) + 60min (stability)

     ↓

LAYER 5: DECISION SUPPORT - CRITICAL
──────────────────────────────────────
Inputs:  value_metrics, quality_metrics, growth_metrics, positioning_metrics,
         stability_metrics, price_daily
Outputs: stock_scores, buy_sell_daily
Loaders: load_stock_scores, load_buy_sell_daily
Failure: HALT if stock_scores empty (min coverage threshold not met)
Timeout: 60min (scores) + 30min (signals)

     ↓

LAYER 6: DASHBOARD ENRICHMENT - OPTIONAL
──────────────────────────────────────────
Inputs:  yfinance_snapshot (already loaded)
Outputs: company_profile, analyst_sentiment_analysis, earnings_calendar
Loaders: load_dashboard_enrichment (NEW - split from yfinance_derived)
Failure: INFO ONLY (dashboard displays gracefully with missing data)
Timeout: 30min

     ↓

LAYER 7: MARKET CONTEXT - OPTIONAL
────────────────────────────────────
Inputs:  price_daily, sector_constituents
Outputs: sector_ranking, sector_performance, market_exposure_daily, algo_metrics_daily
Loaders: load_sector_rankings, load_sector_industry_daily, market_status_daily (redundant?),
         load_algo_metrics_daily, load_economic_data
Failure: INFO ONLY
Timeout: 30min each
```

### CONSOLIDATED LOADERS (Recommended):

**Currently Correct (Keep As-Is):**
- ✅ load_value_quality_growth_metrics.py (consolidates 2 old loaders)
- ✅ load_financial_statements.py (consolidates 6 period/statement combos)
- ✅ load_market_status_daily.py (consolidates market health + exposure + sentiment)

**Needs Splitting (Separate Concerns):**
- ⚠️ load_yfinance_derived_metrics.py (SPLIT INTO):
  - load_positioning_metrics.py (CRITICAL - feed stock_scores)
  - load_dashboard_enrichment.py (OPTIONAL - company_profile, analyst_sentiment, earnings_calendar)

**Should Be Deleted (Already Replaced):**
- ❌ load_quality_growth_metrics.py (DELETE - redundant with load_value_quality_growth_metrics.py)
- ❌ load_market_health_daily.py (DELETE - redundant with load_market_status_daily.py)

---

## PART 7: LOADER DELETION/CONSOLIDATION ROADMAP

### IMMEDIATE (Safe, No Risk):

**1. Delete load_quality_growth_metrics.py**
- Status: ORPHANED (not called anywhere, load_value_quality_growth_metrics replaces it)
- Risk: NONE (already replaced)
- Effort: 5 min (delete file, update .gitignore)

**2. Delete load_market_health_daily.py**
- Status: ORPHANED (not called anywhere, load_market_status_daily replaces it)
- Risk: NONE (already replaced)
- Effort: 5 min (delete file)

### SHORT-TERM (Recommended, Low Risk):

**3. Split load_yfinance_derived_metrics.py**
- Create load_positioning_metrics.py (read from yfinance_snapshot, write to positioning_metrics ONLY)
- Create load_dashboard_enrichment.py (read from yfinance_snapshot, write to company_profile, analyst_sentiment_analysis, earnings_calendar)
- Update terraform to call both loaders separately
- Rationale: Separates trading-critical from dashboard-only; clearer intent
- Risk: MEDIUM (requires terraform changes + testing)
- Effort: 4-6 hours (code split, tests, terraform)
- Timeline: Session 220+

### MEDIUM-TERM (Optional Optimizations):

**4. Eliminate Redundant Sector Loaders**
- Issue: load_sector_rankings.py + load_sector_industry_daily.py might duplicate work
- Investigation Needed: Do they write same/different columns to sector_ranking/sector_performance?
- Decision: Merge or document which is primary source
- Effort: 2-3 hours investigation

**5. Consolidate Market Context Loaders**
- Issue: load_sector_rankings, load_sector_industry_daily, load_economic_data are all OPTIONAL
- Opportunity: Could consolidate into single load_market_context_daily task
- Benefit: Reduce ECS tasks by 2, save $0.05/run
- Risk: LOW (none critical for trading)
- Effort: 4-6 hours
- Timeline: Session 221+

---

## PART 8: CRITICAL DATA REQUIREMENTS FOR TRADING

### Minimum Viable Trading (MVP):
```
MUST-HAVE:
  ✓ price_daily (OHLCV) - prices for all symbols
  ✓ technical_data_daily (RSI, SMA50, SMA200, MACD, ATR) - for signal generation
  ✓ stock_scores (composite score ≥50% complete) - for entry filtering

Optional but Recommended:
  ⚠ value_metrics (PE/PB/PS) - improves trade quality but can degrade
  ⚠ stability_metrics (beta/volatility) - improves risk assessment
```

### Robust Trading (Recommended):
```
Critical (HALT if missing):
  ✓ price_daily (100% coverage for active symbols)
  ✓ technical_data_daily (same-day completion, 95%+ OHLCV complete)
  ✓ stock_scores (≥70% stocks with real scores, not all data_unavailable markers)

Should-Have (WARN if stale, proceed with degradation):
  ⚠ value_metrics (≥30% coverage) - quality filtering
  ⚠ quality_metrics (≥20% coverage) - quality scoring
  ⚠ growth_metrics (≥20% coverage) - growth scoring
  ⚠ positioning_metrics (≥30% coverage) - signal weighting
  ⚠ stability_metrics (≥30% coverage) - risk management

Dashboard Enhancement (Optional):
  ℹ company_profile - sector display
  ℹ analyst_sentiment_analysis - signal confirmation
  ℹ earnings_calendar - blackout window management
```

---

## PART 9: WHAT TO DELETE vs KEEP

### DELETE Immediately (100% Safe):
- ❌ loaders/load_quality_growth_metrics.py
- ❌ loaders/load_market_health_daily.py

### KEEP (Core Trading):
- ✅ loaders/load_prices.py
- ✅ loaders/load_technical_indicators.py
- ✅ loaders/load_stock_scores.py
- ✅ loaders/load_buy_sell_daily.py
- ✅ loaders/load_value_quality_growth_metrics.py
- ✅ loaders/load_sec_valuations.py
- ✅ loaders/load_financial_statements.py
- ✅ loaders/load_trend_analysis.py
- ✅ loaders/load_yfinance_snapshot.py

### KEEP (Market Context):
- ✅ loaders/load_market_status_daily.py
- ✅ loaders/load_market_constituents.py
- ✅ loaders/load_risk_metrics_daily.py
- ✅ loaders/load_sector_rankings.py
- ✅ loaders/load_sector_industry_daily.py
- ✅ loaders/load_economic_data.py
- ✅ loaders/load_algo_metrics_daily.py

### CONSIDER SPLITTING (Separate Concerns):
- ⚠️ loaders/load_yfinance_derived_metrics.py
  - Split into: load_positioning_metrics.py (critical) + load_dashboard_enrichment.py (optional)

---

## SUMMARY TABLE: CORRECT LOADER ARCHITECTURE

| Loader Name | Input Tables | Output Tables | Critical? | Consolidated From | Status |
|-------------|--------------|---------------|-----------|-------------------|--------|
| load_market_constituents | None | stock_symbols | MEDIUM | (new) | ✅ KEEP |
| load_prices | None | price_daily, price_weekly, price_monthly | CRITICAL | (core) | ✅ KEEP |
| load_yfinance_snapshot | None | yfinance_snapshot | HIGH | (core) | ✅ KEEP |
| load_financial_statements | None | annual_income_statement, annual_balance_sheet, annual_cash_flow | HIGH | income+balance+cashflow loaders | ✅ KEEP |
| load_sec_valuations | annual_income_statement, annual_balance_sheet, price_daily | sec_valuations | HIGH | (new, Phase 5) | ✅ KEEP |
| load_value_quality_growth_metrics | annual_income_statement, yfinance_snapshot | value_metrics, quality_metrics, growth_metrics | HIGH | value_metrics + quality_growth_metrics | ✅ KEEP |
| load_yfinance_derived_metrics | yfinance_snapshot | positioning_metrics, company_profile, analyst_sentiment_analysis, earnings_calendar | MIXED | value+position+company+analyst+earnings loaders | ⚠️ SPLIT |
| load_risk_metrics_daily | price_daily, yfinance_snapshot | stability_metrics, momentum_metrics | HIGH | (core) | ✅ KEEP |
| load_stock_scores | value_metrics, quality_metrics, growth_metrics, positioning_metrics, stability_metrics, price_daily | stock_scores | CRITICAL | (core) | ✅ KEEP |
| load_technical_indicators | price_daily | technical_data_daily | CRITICAL | (core) | ✅ KEEP |
| load_trend_analysis | technical_data_daily | trend_template_data | HIGH | (core, renamed) | ✅ KEEP |
| load_buy_sell_daily | price_daily, technical_data_daily, stock_scores | buy_sell_daily | CRITICAL | (core) | ✅ KEEP |
| load_market_status_daily | price_daily, sector_ranking, technical_data_daily | market_health_daily, market_exposure_daily, market_sentiment | HIGH | market_health + market_exposure + market_sentiment | ✅ KEEP |
| load_sector_rankings | price_daily, stock_symbols | sector_ranking | MEDIUM | (core) | ✅ KEEP |
| load_sector_industry_daily | stock_symbols | sector_performance | MEDIUM | (core) | ✅ KEEP |
| load_algo_metrics_daily | algo_audit_log | algo_metrics_daily | LOW | (dashboard) | ✅ KEEP |
| load_economic_data | None | economic_data | LOW | (context) | ✅ KEEP |
| load_quality_growth_metrics | (deprecated) | (deprecated) | N/A | (replaced) | ❌ DELETE |
| load_market_health_daily | (deprecated) | (deprecated) | N/A | (replaced) | ❌ DELETE |

---

## FINAL RECOMMENDATIONS

### Phase 1: Cleanup (This Week)
1. Delete load_quality_growth_metrics.py (orphaned)
2. Delete load_market_health_daily.py (orphaned)
3. Document that load_value_quality_growth_metrics.py is the current quality/growth source
4. Document that load_market_status_daily.py is the current market health source

### Phase 2: Clarify Data Tier (Next Week)
1. Update Phase 1 freshness validation to separate CRITICAL vs WARNING tier metrics
2. HALT on: price_daily, technical_data_daily, stock_scores
3. WARN on: value_metrics, quality_metrics, growth_metrics (optional SEC data)
4. DEBUG on: positioning_metrics, stability_metrics (enrichment)

### Phase 3: Split Concerns (Future)
1. Split load_yfinance_derived_metrics into:
   - load_positioning_metrics.py (CRITICAL for stock_scores)
   - load_dashboard_enrichment.py (OPTIONAL for UI)
2. Update terraform to call both separately
3. Adjust timeline: positioning_metrics earlier (critical path), dashboard_enrichment later (non-blocking)

### Phase 4: Long-term Roadmap
1. Investigate sector loader redundancy
2. Consider consolidating market context loaders
3. Explore caching company_profile (rarely changes)
4. Consider removing earnings_calendar (dashboard only, rarely used)

---

## SUCCESS CRITERIA

✅ **Architecture Clean When:**
- All orphaned loaders deleted (quality_growth_metrics, market_health_daily)
- All remaining loaders clearly mapped to output tables
- No file has two sources writing same table (no conflict)
- CRITICAL vs OPTIONAL tiers documented in code
- terraform clearly shows trading vs dashboard loaders
- Phase 1 validation reflects actual criticality (not all metrics = HALT)

✅ **Data Quality Clean When:**
- stock_scores validates minimum 3/6 metric coverage (currently does this ✓)
- All data_unavailable markers properly propagated through pipeline
- No silent degradation (either fully available or explicitly marked unavailable)
- Dashboard gracefully handles missing company_profile/analyst_sentiment (no crashes)
- Trading continues even if positioned/stability metrics stale (only value/technical are CRITICAL)
