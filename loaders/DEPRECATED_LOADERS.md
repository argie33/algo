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

### analyst_sentiment_analysis / analyst_upgrade_downgrade tables (no loader file - never had one post-migration)
**Reason**: Both were populated by load_yfinance_derived_metrics.py (above) and went permanently
empty when it was retired. Unlike the other yfinance-era tables, these have **no SEC/Alpaca/
FRED/FINRA equivalent** - analyst ratings/upgrades/downgrades are third-party opinion data
that isn't published in SEC filings or any of this project's other official free sources, so
there is nothing to migrate them to (confirmed 2026-07-27: 0 rows, no writer anywhere in the
codebase, no candidate replacement table exists in the schema).
**Replaced By**: Nothing - this data category has no free/official source under this
project's data-sourcing policy (see "Migration References" above).
**Data Impact**: `/api/sentiment/data` and `/api/sentiment/summary`'s `analyst` field
correctly report unavailable/null (verified 2026-07-27, not silently zeroed) rather than
serving fake data - this is the honest terminal state for this feature, not a bug to fix
with a data-source swap. Reviving it would mean building a new paid/scraped analyst-ratings
pipeline, a product decision, not a loader fix.
**Status**: DEPRECATED - already in algo/monitoring/pipeline_health.py KNOWN_DEPRECATED_TABLES

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
