# LOADER AUDIT - Session 271 (TODAY)

## Current State

### Stale Data
- yfinance_snapshot: 3 days old, 45.8% unavailable (2,146/4,683 rows marked unavailable)
- Price data: 2 days old (Thursday) - OK for Saturday, but needs verification Monday
- Technical data: 2 days old (Thursday) - OK for Saturday

### Not Running
- yfinance_snapshot: No execution records, not in morning pipeline
- AAII sentiment: UNAVAILABLE since 2026-07-12 (marked as disabled)
- Several loaders missing market_status_daily execution records

### What We Have (Real Data)
- price_daily: 8.68M rows from Alpaca (good!)
- sec_valuations: 10,595 rows (PE/PB/PS/PEG/FCF computed from SEC)
- company_info_sec: 4,855 rows (replaces ~20% yfinance)
- institutional_holdings_13f: 9,423 rows (SEC 13F filings)
- insider_holdings_sec: 1,497 rows (SEC Form 4/5)
- short_interest_finra: Fresh FINRA data (replaces yfinance short%)
- technical_data_daily: 256k+ rows of calculated indicators

## Loaders Depending on yfinance_snapshot

1. load_value_quality_growth_metrics.py - **CRITICAL** (reads for dividend yield)
2. load_positioning_metrics.py - **HIGH** (reads for holdings/analyst)
3. load_market_cap_computed.py - **MEDIUM** (optional enrichment)
4. load_company_info_sec.py - **IRONIC** (SEC loader reading yfinance!)
5. load_earnings_calendar_sec.py - **IRONIC** (SEC loader reading yfinance!)
6. load_insider_holdings_sec.py - **HIGH** (reads for enrichment)
7. load_institutional_holdings_13f.py - **HIGH** (reads for enrichment)
8. load_yfinance_derived_metrics.py - **LEGACY** (deprecated?)

## Solution: Eliminate yfinance_snapshot Dependency

### Step 1: Identify Data We're Missing
- Dividend yield (in yfinance_snapshot, not in SEC data)
- Analyst recommendation counts (in yfinance, not in SEC data)
- Next earnings date (we have earnings_calendar_sec!)

### Step 2: Replace or Remove
- PE/PB/PS/PEG/FCF → Use sec_valuations (DONE!)
- Sector/Industry/Country → Use company_info_sec
- Dividend → **REMOVE** (not critical for positioning)
- Holdings % → Use 13F + Form 4 (DONE!)
- Short % → Use FINRA (DONE!)
- Analyst counts → **REMOVE** (not critical)

### Step 3: Fix Load Order
Morning pipeline must complete BEFORE metrics pipeline:
1. load_prices.py → price_daily
2. load_technical_indicators.py → technical_data_daily
3. load_market_status_daily.py → market_status_daily (currently missing!)
4. Then metrics pipeline can run

### Step 4: Patch Loaders
Remove yfinance_snapshot dependency from:
- [ ] load_value_quality_growth_metrics.py
- [ ] load_positioning_metrics.py
- [ ] load_market_cap_computed.py
- [ ] load_company_info_sec.py (move to SEC-only)
- [ ] load_earnings_calendar_sec.py (move to SEC-only)
- [ ] load_insider_holdings_sec.py (move to SEC-only)
- [ ] load_institutional_holdings_13f.py (move to SEC-only)
- [ ] Delete load_yfinance_derived_metrics.py (merged into consolidated loaders)

## Expected Outcome

- 0% yfinance dependency
- 100% real data from Alpaca + SEC + FINRA
- Faster loader execution (no yfinance API calls)
- More reliable (no yfinance rate limits/bans)
- Bulletproof system with explicit data_unavailable markers
