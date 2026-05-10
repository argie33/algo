# Loader Architecture Audit — Cleanup Recommendations

**Date:** 2026-05-09  
**Context:** 70 loader files exist; only 41 are in official Terraform pipeline; 25 are orphaned  
**Goal:** Clarify which loaders are production vs experimental, remove architectural slop

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| Official loaders in pipeline | 41 | ✓ Scheduled, running |
| Template/example files | 3 | → Moved to `/examples/` |
| Utility infrastructure modules | 3 | ✓ In root (imported by orchestrator) |
| Extended/unscheduled loaders | 19 | **⚠ Decision required** |

---

## Completed Actions

- [x] Moved `loader_base_optimized.py` → `/examples/` (template)
- [x] Moved `loader_with_watermark_example.py` → `/examples/` (example)
- [x] Moved `loader_polars_base.py` → `/examples/` (pattern template)
- [x] Added `loadbuysell_etf_weekly.py` to Terraform file_map + scheduled at 10pm UTC
- [x] Added `loadbuysell_etf_monthly.py` to Terraform file_map + scheduled at 10pm UTC

---

## Remaining Orphaned Loaders — Decision Matrix

### Category A: Bulk/Alternative Implementations
These are alternative approaches to official loaders (either faster bulk version or fallback source).

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `load_eod_bulk.py` | Bulk refresh of price_daily for full universe in 5 min (vs per-symbol) | No (loadpricedaily.py is official) | **DECISION:** Keep as manual/on-demand or replace per-symbol loader? EOD bulk is faster. |
| `loadmultisource_ohlcv.py` | OHLCV with Alpaca primary + yfinance fallback | No (loadpricedaily.py single-source) | **DECISION:** Integrate as fallback for loadpricedaily, or keep as manual backup? |

### Category B: Market/Economic Data Extensions
Additional market data beyond core pipeline.

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `load_market_health_daily.py` | Market health metrics (breadth, distribution, volume) | No | **DECISION:** Is market health needed for algo? If yes, add to Terraform at market_overview time. If no, delete. |
| `loadcommodities.py` | Commodity prices (oil, gold, etc.) | No | **DECISION:** Not in core trading logic. Keep as experimental or delete? |

### Category C: News/Sentiment Extensions
Content-based data beyond included signals.

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `loadnews.py` | Financial news scrape | No | **DECISION:** Not in algo logic. Mark as experimental or delete. |
| `loadsecfilings.py` | SEC filing monitoring | No | **DECISION:** Advanced feature, not used by current signals. Archive or delete. |

### Category D: Technical/Options Analysis
Specialized trading tools beyond daily signals.

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `loadoptionschains.py` | Options market data | No | **DECISION:** For future options trading? Archive if not Phase 1-2 scope. |
| `loadcoveredcallopportunities.py` | Covered call scanning | No | **DECISION:** Advanced strategy, not in algo. Delete or archive. |
| `loadforwardeps.py` | Forward earnings estimates | No (loadearningsestimates.py differs) | **DECISION:** Supplement earnings_surprise? Check if needed. |

### Category E: Rankings/Comparisons
Relative analysis tools not in core signals.

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `loadsectorranking.py` | Sector momentum ranking | No (loadsectors.py is official) | **DECISION:** Duplicate concept? Analyze differences and consolidate or remove. |
| `loadindustryranking.py` | Industry momentum ranking | No | **DECISION:** Complement to sector_ranking? If useful, integrate; if not, delete. |
| `loadbenchmark.py` | Benchmark comparison (SPY vs AAPL, etc.) | No | **DECISION:** For performance analytics? If yes, integrate; if no, delete. |

### Category F: Alternative Signal Generators
Non-standard signal approaches (not in official signal tiers).

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `loadmeanreversionsignals.py` | Mean reversion signals | No (loadbuyselldaily.py is official) | **DECISION:** Alternative signal method? Archive as experimental strategy. |
| `loadrangesignals.py` | Support/resistance range signals | No | **DECISION:** Supplement to trend signals? Archive or delete. |
| `loadswingscores.py` | Swing trade scoring | No | **DECISION:** For swing strategy (not day/trend)? Archive if not used. |

### Category G: Account Integration
Live account data (not reference data).

| Loader | Purpose | In Official Pipeline | Recommendation |
|--------|---------|---------------------|-----------------|
| `loadalpacaportfolio.py` | Sync Alpaca account state | No | **DECISION:** For live position import? Needs reconciliation integration. Archive if using internal algo_positions. |

---

## Utility Modules (Non-Loader)

These are helper modules used by the orchestrator/loaders, NOT data loaders. They should remain in root.

| Module | Purpose | Usage |
|--------|---------|-------|
| `loader_safety.py` | Timeout + signal handling wrapper | Imported by `algo_orchestrator.py` |
| `loader_metrics.py` | Loader performance tracking | Imported by `algo_orchestrator.py` |
| `loader_sla_tracker.py` | SLA monitoring for loader health | Imported by `algo_orchestrator.py` |

**Action:** Keep in root (core infrastructure).

---

## Recommended Process

**For each orphaned loader, decide:**

1. **DELETE** — Not needed, not in scope, no callers
2. **ARCHIVE** — Future phase or optional strategy; move to `/experimental/` or `docs/archived_loaders/`
3. **INTEGRATE** — Add to Terraform with proper schedule and ECS task definition

**Example decisions (to be confirmed by user):**

- `load_eod_bulk.py` — **DECISION NEEDED:** Replace loadpricedaily (faster) or keep as manual fallback?
- `loadnews.py` — **DELETE** (not in algo, no sentiment integration)
- `loadalpacaportfolio.py` — **DECISION NEEDED:** Is live position import required, or only algo_positions table?
- `loadmultisource_ohlcv.py` — **DECIDE:** Fallback source needed, or just yfinance?
- `load_market_health_daily.py` — **DECISION NEEDED:** Is market breadth used by circuit breakers?

---

## Files to Delete (Likely)

If not needed for trading algo:
- `loadnews.py`
- `loadcoveredcallopportunities.py`
- `loadrangesignals.py`
- `loadmeanreversionsignals.py`
- `loadsecfilings.py`
- `loadoptionschains.py`
- `loadcommodities.py`

---

## Files to Archive (Low Priority/Future)

If needed but not Phase 1:
- `load_market_health_daily.py` — Market breadth/distribution metrics
- `loadbenchmark.py` — Performance benchmarking
- `loadsectorranking.py` — Sector momentum (supplement to sector data?)
- `loadswingscores.py` — Swing trade signals (not day/trend scope)
- `loadindustryranking.py` — Industry momentum
- `loadforwardeps.py` — Forward earnings (check vs loadearningsestimates.py)
- `loadalpacaportfolio.py` — Live account sync (check if needed vs algo_positions)

---

## Next Steps

1. User reviews this matrix and provides decisions for each loader
2. Execute consolidation:
   - Move decided archival loaders to `/experimental/` or delete
   - Integrate any loaders marked for inclusion (add to Terraform)
   - Document why each loader exists (in code comments or README)
3. Verify no other code imports the removed loaders (grep -r)
4. Update terraform and documentation

---

## Current Pipeline (41 Official Loaders)

**Tier 1 — Reference Data (3:30am ET / 8:30am UTC)**
- stock_symbols

**Tier 2 — Price Data (4:00am ET / 9:00am UTC)**
- stock_prices_daily, weekly, monthly
- etf_prices_daily, weekly, monthly

**Tier 3 — Technical Data (4:15am ET / 9:15am UTC)**
- trend_template_data
- technicals_daily

**Tier 4 — Financial Data (10:00am ET / 3pm UTC)**
- financials_annual_income, balance, cashflow
- financials_quarterly_income, balance, cashflow
- financials_ttm_income, cashflow

**Tier 5 — Earnings Data (11:00am ET / 4pm UTC)**
- earnings_history, revisions, surprise

**Tier 6 — Market Data (12:00pm ET / 5pm UTC)**
- market_overview, market_indices, sectors, relative_performance, seasonality
- econ_data, aaiidata, naaim_data, feargreed, calendar

**Tier 7 — Analysis Data (1:00pm ET / 6pm UTC)**
- analyst_sentiment, analyst_upgrades, social_sentiment, factor_metrics
- stock_scores

**Tier 8 — Trading Signals (5:00pm ET / 10pm UTC)**
- signals_daily, weekly, monthly
- signals_etf_daily, weekly, monthly
- etf_signals

**Tier 9 — Metrics (5:15pm ET / 10:15pm UTC)**
- algo_metrics_daily
