# Loader Architecture & Consolidation Map

**Status:** Production (18 active loaders, 4 consolidated from original 22+)

---

## Active Loaders (18)

### Tier 1: Core Market Data (3)
1. **load_prices.py** → `price_daily`, `price_weekly`, `price_monthly`
   - Upstream: Alpaca SIP (primary) + yfinance fallback
   - Schedule: 2:00 AM ET (Morning pipeline)
   - Criticality: CRITICAL (blocks technical indicators, all downstream)

2. **load_market_constituents.py** → `stock_symbols`
   - Upstream: NASDAQ + NYSE lists from yfinance
   - Schedule: 2:00 AM ET (Morning pipeline)
   - Criticality: CRITICAL (defines symbol universe)

3. **load_technical_indicators.py** → `technical_data_daily`
   - Upstream: Vectorized compute over `price_daily`
   - Schedule: 2:00 AM ET (Morning pipeline)
   - Criticality: CRITICAL (blocks buy/sell signals, momentum scoring)

### Tier 2: Yfinance Derivatives (2)
4. **load_yfinance_snapshot.py** → `yfinance_snapshot`
   - Upstream: yfinance quoteSummary API (fetched once per symbol per day)
   - Schedule: 9:15 AM ET (Reference pipeline)
   - Criticality: HIGH (upstream for consolidated yfinance_derived_metrics)

5. **load_yfinance_derived_metrics.py** → 5 tables
   - **Consolidated:** Merges 6 separate loaders into one
     - ~~load_company_profile.py~~ → `company_profile`
     - ~~load_value_metrics.py~~ → `value_metrics`
     - ~~load_positioning_metrics.py~~ → `positioning_metrics`
     - ~~load_earnings_calendar.py~~ → `earnings_calendar`
     - ~~load_analyst_analysis.py~~ → `analyst_sentiment_analysis`
     - ~~load_earnings_history.py~~ (not implemented)
   - Upstream: `yfinance_snapshot` (reads once, writes to 5 tables in parallel)
   - Schedule: 9:15 AM ET (Reference pipeline)
   - Criticality: HIGH (stock profile, dividend yield, short interest)
   - **Why consolidated:** Read-once-write-many pattern eliminates 5 redundant ECS tasks, reduces 4:20 PM bottleneck ~80%

### Tier 3: Fundamental Data (2)
6. **load_financial_statements.py** → `annual_income_statement`, `quarterly_income_statement`, `annual_balance_sheet`, `quarterly_balance_sheet`
   - Upstream: SEC EDGAR (companyfacts, 2 req/s, LRU cache per CIK)
   - Schedule: 7:00 PM ET (Computed metrics pipeline)
   - Criticality: HIGH (blocks quality_metrics, growth_metrics)

7. **load_market_health_daily.py** → `market_health_daily`
   - Upstream: Computed from VIX, advance/decline, breadth data
   - Schedule: 2:00 AM ET (Morning pipeline) + 4:05 PM ET (EOD pipeline)
   - Criticality: HIGH (breadth calculations for trend analysis)

### Tier 4: Metric Loaders (5)
8. **load_quality_growth_metrics.py** → `quality_metrics`, `growth_metrics`
   - **Consolidated:** Merges compute_quality_metrics + compute_growth_metrics
   - Upstream: SEC financials, dividend history
   - Schedule: 7:00 PM ET (Computed metrics pipeline)
   - Criticality: CRITICAL (feeds stock_scores)

9. **load_risk_metrics_daily.py** → `stability_metrics`, `momentum_metrics`
   - **Consolidated:** Merges ~~load_momentum_metrics.py~~ + ~~load_stability_metrics.py~~
   - Upstream: Price data (beta calc), returns (momentum calc)
   - Schedule: 7:00 PM ET (Computed metrics pipeline)
   - Criticality: CRITICAL (feeds stock_scores)

10. **load_stock_scores.py** → `stock_scores`
    - Upstream: All metric tables (quality, growth, value, positioning, stability, momentum)
    - Schedule: 7:00 PM ET (Computed metrics pipeline)
    - Criticality: CRITICAL (drives Phase 7 signal generation)

11. **load_market_exposure_daily.py** → `market_exposure_daily`
    - Upstream: Portfolio positions, sector weights
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: MEDIUM (portfolio risk monitoring)

12. **load_economic_data.py** → `economic_data`
    - **Consolidated:** Merges ~~load_fred_economic_data.py~~ + ~~load_dxy_index.py~~
    - Upstream: FRED API (T10Y2Y, FEDFUNDS, BAMLH0A0HYM2, ICSA) + yfinance (DXY)
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: LOW (macro signals, optional)

### Tier 5: Signal Generation (3)
13. **load_buy_sell_daily.py** → `buy_sell_daily`
    - Upstream: Trend template, technical data, price data
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: CRITICAL (generates daily buy/sell signals)

14. **load_algo_metrics_daily.py** → `algo_metrics_daily`
    - Upstream: Trade history, portfolio state
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: LOW (monitoring/reporting)

15. **load_market_sentiment.py** → `market_sentiment`
    - Upstream: VIX, breadth data
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: LOW (fear/greed index)

### Tier 6: Rankings & Analysis (3)
16. **load_sector_rankings.py** → `sector_ranking`
    - Upstream: Sector performance, breadth
    - Schedule: 2:00 AM ET (Morning pipeline)
    - Criticality: LOW (sector rotations)

17. **load_sector_performance.py** → `sector_performance`
    - Upstream: Price data per sector
    - Schedule: 4:05 PM ET (EOD pipeline)
    - Criticality: LOW (analysis only)

18. **load_trend_analysis.py** → `trend_template_data`
    - Upstream: Technical data, SMA, RSI
    - Schedule: 2:00 AM ET (Morning pipeline)
    - Criticality: HIGH (Minervini/Weinstein trend scoring for market health, buy/sell signals)

---

## Consolidation Summary

**Original count:** 22+ separate loaders
**Current count:** 18 active loaders (4 consolidated)

**Consolidated loaders:**
| Original Files | Consolidated Into | Reason |
|---|---|---|
| 6 yfinance-derived loaders | `load_yfinance_derived_metrics.py` | All read same upstream table, write different outputs. Parallelized writes, reduced 5 redundant ECS tasks |
| 2 metrics loaders | `load_quality_growth_metrics.py` | Both depend on SEC financials, share computation overhead |
| 2 economic loaders | `load_economic_data.py` | Both write same table, eliminated race condition |
| 2 risk metrics loaders | `load_risk_metrics_daily.py` | Both compute from price data, can parallelize writes |

---

## Pipeline Execution Schedule (MON-FRI ET)

### Morning (2:00 AM)
- load_prices.py
- load_market_constituents.py
- load_technical_indicators.py
- load_market_health_daily.py
- load_trend_analysis.py
- load_sector_rankings.py

### Reference (9:15 AM)
- load_yfinance_snapshot.py
- load_yfinance_derived_metrics.py

### EOD (4:05 PM)
- load_prices.py (bulk refresh)
- load_technical_indicators.py (vectorized refresh)
- load_trend_analysis.py (vectorized refresh)
- load_market_health_daily.py
- load_buy_sell_daily.py
- load_algo_metrics_daily.py
- load_sector_performance.py
- load_market_exposure_daily.py
- load_market_sentiment.py
- load_economic_data.py

### Computed Metrics (7:00 PM)
- load_financial_statements.py (SEC EDGAR, cached per CIK, 30-45 min)
- load_quality_growth_metrics.py
- load_risk_metrics_daily.py
- load_stock_scores.py

---

## Dead/Deprecated Loaders (DO NOT USE)

- ~~load_company_profile.py~~ → Use load_yfinance_derived_metrics.py
- ~~load_value_metrics.py~~ → Use load_yfinance_derived_metrics.py
- ~~load_positioning_metrics.py~~ → Use load_yfinance_derived_metrics.py
- ~~load_earnings_calendar.py~~ → Use load_yfinance_derived_metrics.py
- ~~load_analyst_analysis.py~~ → Use load_yfinance_derived_metrics.py
- ~~load_earnings_history.py~~ → Not implemented
- ~~load_momentum_metrics.py~~ → Use load_risk_metrics_daily.py
- ~~load_stability_metrics.py~~ → Use load_risk_metrics_daily.py
- ~~load_fred_economic_data.py~~ → Use load_economic_data.py
- ~~load_dxy_index.py~~ → Use load_economic_data.py
- ~~load_trend_criteria_data.py~~ → Renamed to load_trend_analysis.py
- ~~load_company_cache.py~~ → Use load_yfinance_snapshot.py
- ~~load_fundamental_metrics.py~~ → Use load_yfinance_derived_metrics.py or load_quality_growth_metrics.py

---

## Architecture Principles (see DATA_LOADERS.md)

1. **One query per table per run** — bulk prefetch, not N+1 symbol loops
2. **Fetch each external payload once per run** — cache, reuse, LRU where needed
3. **Derive, don't re-fetch** — SQL-derived weekly/monthly bars, cached per-symbol
4. **Write incrementally with watermarks** — per-symbol high-water-marks, skip already-processed rows
5. **Batch the write path** — chunked COPY + upsert, not per-symbol staging cycles
6. **All yfinance traffic through one funnel** — YFinanceWrapper + IP circuit breaker coordination
7. **Don't discard good data on transient blips** — fail-fast or explicit data_unavailable, not silent fallback

---

## Verification

Run:
```bash
python3 scripts/verify_loaders_health.py    # Check all loaders
python3 scripts/monitor_data_staleness.py   # Check data freshness
```
