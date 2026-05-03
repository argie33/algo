# Data Loading — Source of Truth

This is the **canonical inventory** of every data loader. If a loader exists
on disk but isn't in this document, either add it here or delete it.

**Last reconciled:** 2026-05-03 — 59 .py loaders, 39 official + 20 supplementary.

---

## Process — Local First, Then AWS

1. **Load locally** with these loader scripts.
2. **Verify** with `python3 algo_data_patrol.py`.
3. **Run algo** with `python3 algo_orchestrator.py`.
4. **Deploy** to AWS via Docker / Lambda.

**No partial patches. No fake data. Full loads only.**

---

## The 39 Official Loaders

These are the ONLY canonical loaders. Run them in dependency order.

### Phase 1 — Universe & Symbols
1. **loadstocksymbols.py** — Stock/ETF symbols
2. **loaddailycompanydata.py** — Company profile, sector, industry
3. **loadmarketindices.py** — Market indices (^GSPC, etc.)

### Phase 2 — Price Data
4. **loadpricedaily.py** — Daily OHLCV
5. **loadpriceweekly.py** — Weekly aggregates
6. **loadpricemonthly.py** — Monthly aggregates
7. **loadlatestpricedaily.py** — Real-time daily
8. **loadlatestpriceweekly.py** — Real-time weekly
9. **loadlatestpricemonthly.py** — Real-time monthly

### Phase 3 — ETF Data
10. **loadetfpricedaily.py** — ETF daily
11. **loadetfpriceweekly.py** — ETF weekly
12. **loadetfpricemonthly.py** — ETF monthly
13. **loadetfsignals.py** — ETF signals (Pine)

### Phase 4 — Pine BUY/SELL Signals (CRITICAL — algo entry source of truth)
14. **loadbuyselldaily.py** — Daily Pine signals
15. **loadbuysellweekly.py** — Weekly Pine signals
16. **loadbuysellmonthly.py** — Monthly Pine signals
17. **loadbuysell_etf_daily.py** — ETF daily Pine
18. **loadbuysell_etf_weekly.py** — ETF weekly Pine
19. **loadbuysell_etf_monthly.py** — ETF monthly Pine

### Phase 5 — Technical Indicators
20. **loadtechnicalsdaily.py** — Daily SMA/RSI/MACD/ATR

### Phase 6 — Fundamentals (Quarterly + Annual)
21. **loadannualbalancesheet.py**
22. **loadquarterlybalancesheet.py**
23. **loadannualincomestatement.py**
24. **loadquarterlyincomestatement.py**
25. **loadannualcashflow.py**
26. **loadquarterlycashflow.py**
27. **loadttmincomestatement.py**
28. **loadttmcashflow.py**

### Phase 7 — Earnings
29. **loadearningshistory.py** — Historical earnings + surprises
30. **loadearningsrevisions.py** — Estimate revisions
31. **loadearningssurprise.py** — Surprise metrics

### Phase 8 — Stock Scoring & Metrics
32. **loadstockscores.py** — IBD-style composite (quality/growth/value/momentum)
33. **loadfactormetrics.py** — Factor metrics (growth, profitability, etc)
34. **loadrelativeperformance.py** — RS rankings

### Phase 9 — Market Data
35. **loadmarket.py** — Market summary
36. **loadecondata.py** — Economic indicators (FRED)
37. **loadcommodities.py** — Commodity prices
38. **loadseasonality.py** — Seasonal patterns

### Phase 10 — Analyst Sentiment
39. **loadanalystupgradedowngrade.py** — Upgrade/downgrade activity

---

## Algo-Required Supplementary Loaders (20)

These were added as the algo system grew. They are NOT removable — the
orchestrator depends on them. Treat them as canonical, just newer than the
original 39.

### Algo Computed Metrics
- **load_algo_metrics_daily.py** — orchestrates: trend_template, market_health, SQS, completeness
- **load_market_health_daily.py** — IBD-style market state
- **load_trend_template_data.py** — Minervini 8-pt + Weinstein stage

### Algo Operational
- **loadalpacaportfolio.py** — Live Alpaca position sync
- **algo_data_patrol.py** — 10-check watchdog
- **algo_data_freshness.py** — 23-source staleness monitor
- **backfill_historical_scores.py** — historical score backfill

### Sentiment & Behavioral
- **loadaaiidata.py** — AAII bull/bear sentiment
- **loadnaaim.py** — NAAIM exposure
- **loadfeargreed.py** — CNN Fear & Greed
- **loadnews.py** — News sentiment
- **loadanalystsentiment.py** — Analyst sentiment composite

### Specialized Signals & Data
- **loadetfsignals.py** — ETF-specific signals
- **loadmeanreversionsignals.py** — Mean-reversion strategy signals
- **loadrangesignals.py** — Range-bound signals
- **loadcoveredcallopportunities.py** — Options income strategy
- **loadoptionschains.py** — Options chains (used by covered call)
- **loadforwardeps.py** — Forward earnings estimates
- **loadearningsestimates.py** — Earnings consensus

### Calendar & Reference
- **loadcalendar.py** — Economic + earnings calendar
- **loadbenchmark.py** — Custom benchmark portfolios
- **loadsectors.py** — Sector classifications
- **loadsentiment.py** — Sentiment aggregator
- **loadsecfilings.py** — SEC filings metadata
- **loadmultisource_ohlcv.py** — Multi-source price reconciliation

### Loader Infrastructure (NOT trade-related, used as base classes)
- **loader_base_optimized.py** — Base class for optimized loaders
- **loader_metrics.py** — Loader runtime metrics
- **loader_polars_base.py** — Polars-based fast loader base
- **loader_safety.py** — Safety wrappers for upserts

---

## Recently Deleted (2026-05-03)

These were duplicates and have been removed:
- ❌ loadpricedaily_optimal.py — duplicate of loadpricedaily.py
- ❌ loadpricedaily_refactored.py — duplicate of loadpricedaily.py
- ❌ loadcommodities_enhanced.py — duplicate of loadcommodities.py
- ❌ loadquarterlyincomestatement_parallel.py — duplicate of loadquarterlyincomestatement.py

---

## Run Schedule (see LOADER_SCHEDULE.md for full detail)

| Frequency | Loaders | Why |
|---|---|---|
| **Intraday** (every 90min) | loadlatestpricedaily | Live decisions need live prices |
| **End of Day** (5:30pm ET) | All Phase 2-5 daily loaders + load_algo_metrics_daily | Algo decisions on EOD data |
| **Weekly** (Sat 8am) | All Phase 2-5 weekly + loadstockscores + loadaaiidata + loadnaaim | Compute weekly metrics |
| **Monthly** (1st Sat) | All Phase 2-5 monthly + loadfactormetrics | Slow-changing metrics |
| **Quarterly** (post-earnings) | Phase 6 fundamentals + Phase 7 earnings | Tied to earnings cycles |

---

## DO / DON'T (Cleanup discipline)

### ✅ DO
- Add new loaders to this document FIRST, then build
- Delete duplicates immediately when noticed
- Run `python3 algo_data_patrol.py` after every loader run
- Use the loader_base_optimized.py base class for new loaders

### ❌ DON'T
- Create `loaderX_optimal.py` / `loaderX_refactored.py` versions (commit to one)
- Insert default values (0, 'None') when data is missing — skip the row
- Patch data in API routes — fix the loader
- Commit `loaderX_test.py` or `loaderX_debug.py` to the repo

---

## Health Check

```bash
# Show which loaders are stale
python3 algo_data_freshness.py

# Run integrity patrol (catches NULL spikes, identical OHLC, etc.)
python3 algo_data_patrol.py

# Run end-of-day pipeline (patrol → loaders → patrol → orchestrator)
bash run_eod_loaders.sh
```

The frontend's "DATA HEALTH" tab surfaces all of this in real-time at
`/app/health`.
