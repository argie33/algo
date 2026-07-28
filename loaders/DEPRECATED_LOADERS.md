# Deprecated Loader Files

These loaders have been consolidated, replaced, or are no longer used in the active pipeline. They are kept for historical reference but should NOT be run.

## Fully Deprecated (Consolidated into other loaders)

### load_sector_performance.py
**Reason**: Consolidated into `load_sector_industry_daily.py` (Session 274)  
**Replaced By**: load_sector_industry_daily.py  
**Data Impact**: sector_performance table now updated by sector_industry_daily loader  
**Status**: ARCHIVED - do not use

### load_sector_rankings.py
**Reason**: Consolidated into `load_sector_industry_daily.py` (Session 274)  
**Replaced By**: load_sector_industry_daily.py  
**Data Impact**: sector_ranking table now updated by sector_industry_daily loader  
**Status**: ARCHIVED - do not use

### load_market_sentiment.py
**Reason**: Consolidated into `load_market_status_daily.py` (Phase 2 consolidation)  
**Replaced By**: load_market_status_daily.py  
**Data Impact**: market_sentiment table now updated by market_status_daily loader  
**Status**: ARCHIVED - do not use

### load_market_exposure_daily.py
**Reason**: Consolidated into `load_market_status_daily.py` (Phase 2 consolidation)  
**Replaced By**: load_market_status_daily.py  
**Data Impact**: market_exposure_daily table now updated by market_status_daily loader  
**Status**: ARCHIVED - do not use

### load_price_extremes.py
**Reason**: No active loader task defined (no business use identified)  
**Replaced By**: None (functionality not needed)  
**Data Impact**: price_extremes_52week table stale (no updates since consolidation)  
**Status**: ORPHANED - can be deleted

### load_market_cap_computed.py
**Reason**: Functionality absorbed into other loaders (load_financial_statements, etc.)  
**Replaced By**: Multiple loaders (SEC financials, etc.)  
**Data Impact**: market_cap_computed table - orphaned, no active loader  
**Status**: ORPHANED - can be deleted

### load_sec_cash_flow_metrics.py
**Reason**: Audit (2026-07-27) found its 3 fields exactly duplicate formulas already computed
elsewhere: `free_cash_flow`/`operating_cash_flow` are the identical `operating_cf - capex`
formula `load_value_quality_growth_metrics.py` already writes to `quality_metrics`, already
scored (`_score_quality`/`_enhance_quality_score` via `fcf_to_net_income`) and displayed
(`lambda/api/routes/stocks.py`'s `fcf_data` CTE, `scores.py`'s `quality_inputs.free_cashflow`);
`cash_conversion_rate` is identical to `quality_metrics.ocf_to_net_income`; `working_capital` is
a strictly weaker, non-size-normalized version of `quality_metrics.current_ratio`/`quick_ratio`
(already scored/displayed). Zero incremental signal for the real SEC API cost.  
**Replaced By**: Nothing needed - `quality_metrics` (via `load_value_quality_growth_metrics.py`)
already covers everything this loader computed.  
**Data Impact**: `sec_cash_flow_metrics` table frozen at 5508 rows from its last run
(2026-07-27) - added to `algo/monitoring/pipeline_health.py`'s `KNOWN_DEPRECATED_TABLES` so it
reports DEPRECATED once that data ages past the 7-day secondary-table SLA, not a false
STALE/CRITICAL alarm.  
**Status**: REMOVED from `scripts/local_loader_scheduler.py` and
`terraform/modules/{loaders,pipeline}/main.tf` - file kept on disk for historical reference,
do not re-wire it in without first shipping a real consumer that isn't already covered by
`quality_metrics` (see `steering/DATA_LOADERS.md`'s matching FIXED note for the full trace).

## Deprecated Data Sources (yfinance)

### load_yfinance_snapshot.py
**Reason**: yfinance deprecated Session 275+ (API rate limiting, unreliability, $99/mo cost)  
**Replaced By**: Multiple SEC-based loaders:
  - load_sec_valuations.py (PE/PB/PS/PEG)
  - load_company_info_sec.py (company info)
  - load_earnings_calendar_sec.py (earnings)
  - load_institutional_holdings_13f.py (institutional holdings)
  - load_insider_holdings_sec.py (insider holdings)
**Data Impact**: yfinance_snapshot table no longer updated (frozen at Session 275)  
**Status**: DEPRECATED - removed from terraform config, no longer runs

### load_yfinance_derived_metrics.py
**Reason**: yfinance deprecated Session 275+ 
**Replaced By**: Multiple SEC-based loaders (see above)  
**Data Impact**: Deprecated table outputs (company_profile, analyst_sentiment, etc.) no longer updated  
**Status**: DEPRECATED - removed from terraform config, no longer runs

### analyst_sentiment_analysis / analyst_upgrade_downgrade tables - RESTORED 2026-07-27, no longer deprecated
**Formerly**: Both were populated by load_yfinance_derived_metrics.py (above) and went
permanently empty when it was retired (~2 months with zero writer, silently scoring
`algo/signals/advanced_filters.py::_analyst_score()`'s catalyst subscore 0 and making
`/api/sentiment/analyst/*` correctly fail-fast on stale data). An earlier pass wrongly
concluded no usable free source existed at all for either table - it does.
**Restored by**: `loaders/load_analyst_upgrade_downgrade.py` and
`loaders/load_analyst_sentiment_analysis.py`, both backed by
`utils/external/yfinance_analyst_ratings.py`. `yf.Ticker.upgrades_downgrades` and
`yf.Ticker.recommendations_summary`/`analyst_price_targets` are real, live-verified working
feeds - SEC/EDGAR still doesn't publish analyst ratings, so this is the same "unofficial but
real, transparently documented" tradeoff already accepted for put/call ratio
(`loaders/market_health_fetchers.py::PutCallRatioFetcher`), not a departure from this
project's official-sources-first policy.
**Wiring**: both loaders run in `scripts/local_loader_scheduler.py` locally and in
`eod_pipeline`'s `AaiiSentiment -> AnalystUpgradeDowngrade -> AnalystSentimentAnalysis ->
MarketStatusDaily` chain in prod (`terraform/modules/pipeline/main.tf`); both tables are
monitored for staleness like any other real loader (removed from
`algo/monitoring/pipeline_health.py`'s `KNOWN_DEPRECATED_TABLES`/exclusion list).
**Status**: ACTIVE - not deprecated, do not re-delete or re-add to the exclusion list.

## Migration References

All deprecated functionality has been replaced with 100% real data sources:
- **Prices**: Alpaca SIP data (free tier, 200 calls/min)
- **Fundamentals**: SEC EDGAR filings (free, authoritative)
- **Holdings**: SEC 13G/Form 4-5 (free, official)
- **Short Interest**: FINRA (free, official)
- **Economics**: FRED API (free)

**Impact**: 5,300+ fewer API calls/day, faster pipeline, more reliable data, $99/month savings.

## How to Clean Up

**Done (Session 295, 2026-07-19):** all 8 files listed above (`load_sector_performance.py`,
`load_sector_rankings.py`, `load_market_sentiment.py`, `load_market_exposure_daily.py`,
`load_price_extremes.py`, `load_market_cap_computed.py`, `load_yfinance_snapshot.py`,
`load_yfinance_derived_metrics.py`) were actually deleted from `loaders/` in commit
`9f39753f8` - confirmed 2026-07-20, none exist on disk anymore. This section previously
still described them as pending archival; that was stale.

**Last Updated**: Session 314 (2026-07-20)
