# Complete Loader → Table Mapping

## Overview
This document maps every Python loader to the database tables it populates. Use this to understand the complete data flow.

---

## PRICE DATA LOADERS

### loadpricedaily.py
**Tables Populated:**
- `price_daily` - Daily OHLCV (open, high, low, close, volume) for all S&P 500 stocks

**Data Coverage:** 515/515 stocks (100%)
**Frequency:** Daily market close
**Key Fields:** symbol, date, open, high, low, close, volume, adjusted_close

---

### loadpriceweekly.py
**Tables Populated:**
- `price_weekly` - Weekly OHLCV aggregated from daily data

**Data Coverage:** 515/515 stocks (100%)
**Frequency:** Weekly (closes Friday)
**Key Fields:** symbol, date, open, high, low, close, volume

---

### loadpricemonthly.py
**Tables Populated:**
- `price_monthly` - Monthly OHLCV aggregated from daily data

**Data Coverage:** 515/515 stocks (100%)
**Frequency:** Monthly (closes last trading day)
**Key Fields:** symbol, date, open, high, low, close, volume

---

### loadlatestpricedaily.py
**Tables Populated:**
- `latest_price_daily` - Cache of most recent daily price for quick lookups

**Data Coverage:** 515/515 stocks (100%)
**Purpose:** Performance optimization for real-time price displays
**Key Fields:** symbol, price, date, change_percent

---

### loadlatestpriceweekly.py
**Tables Populated:**
- `latest_price_weekly` - Cache of most recent weekly price

**Data Coverage:** 515/515 stocks (100%)

---

### loadlatestpricemonthly.py
**Tables Populated:**
- `latest_price_monthly` - Cache of most recent monthly price

**Data Coverage:** 515/515 stocks (100%)

---

## ETF DATA LOADERS

### loadetfpricedaily.py
**Tables Populated:**
- `price_daily` - Daily prices (ETF symbols included, filtered by etf_symbols table)

**ETF Symbols Covered:** SPY, QQQ, IVV, VOO, VTI, AGG, BND, GLD, DBC, DXY, etc.
**Key Fields:** symbol, date, open, high, low, close, volume

---

### loadetfpriceweekly.py
**Tables Populated:**
- `price_weekly` - Weekly ETF prices

**Data Coverage:** All tracked ETFs

---

### loadetfpricemonthly.py
**Tables Populated:**
- `price_monthly` - Monthly ETF prices

**Data Coverage:** All tracked ETFs

---

### loadetfsignals.py
**Tables Populated:**
- `buy_sell_daily` - Trading signals for ETFs (filtered by etf_symbols table)
- `buy_sell_weekly` - Weekly signals for ETFs
- `buy_sell_monthly` - Monthly signals for ETFs

**Purpose:** Buy/sell signals for major ETFs using technical analysis
**Key Fields:** symbol, date, signal (Buy/Sell/None), timeframe

---

## TECHNICAL INDICATOR LOADERS

### loadtechnicalsdaily.py
**Tables Populated:**
- `buy_sell_daily` - Daily buy/sell signals with technical indicators for stocks

**Data Coverage:** 515/515 stocks (100%)
**Indicators Calculated:**
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands (upper, middle, lower)
- SMA (Simple Moving Averages: 20, 50, 200)
- EMA (Exponential Moving Averages: 12, 26)
- ATR (Average True Range)
- ADX (Average Directional Index)

**Key Fields:** symbol, date, signal, rsi, macd, signal_line, histogram, sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx, buylevel

---

### loadtechnicalsweekly.py
**Tables Populated:**
- `buy_sell_weekly` - Weekly signals with technical indicators

**Data Coverage:** 515/515 stocks (100%)
**Same Indicators:** RSI, MACD, SMA, EMA, etc.

---

### loadtechnicalsmonthly.py
**Tables Populated:**
- `buy_sell_monthly` - Monthly signals with technical indicators

**Data Coverage:** 515/515 stocks (100%)

---

## BUY/SELL SIGNAL LOADERS (STOCK SIGNALS)

### loadbuyselldaily.py
**Tables Populated:**
- `buy_sell_daily` - Daily trading signals for all S&P 500 stocks

**Data Coverage:** 515/515 stocks (100%)
**Signal Types:** Buy, Sell, None
**Key Fields:** symbol, date, signal, timeframe, buylevel (signal strength)

---

### loadbuysellweekly.py
**Tables Populated:**
- `buy_sell_weekly` - Weekly trading signals

**Data Coverage:** 515/515 stocks (100%)

---

### loadbuysellmonthly.py
**Tables Populated:**
- `buy_sell_monthly` - Monthly trading signals

**Data Coverage:** 515/515 stocks (100%)

---

### loadbuysell_etf_daily.py
**Tables Populated:**
- `buy_sell_daily` - Daily signals for ETFs (merged with stock signals)

**Key Note:** ETF signals are stored in the SAME tables as stock signals, filtered by etf_symbols table

---

### loadbuysell_etf_weekly.py
**Tables Populated:**
- `buy_sell_weekly` - Weekly ETF signals

---

### loadbuysell_etf_monthly.py
**Tables Populated:**
- `buy_sell_monthly` - Monthly ETF signals

---

## COMPANY DATA LOADER (CONSOLIDATES MULTIPLE SOURCES)

### loaddailycompanydata.py
**Tables Populated:**
- `company_profile` - Company name, sector, industry, market cap, etc.
- `institutional_positioning` - Institution type, shares held, ownership %
- `positioning_metrics` - Institutional ownership, short interest, etc.
- `insider_transactions` - Individual insider buy/sell activity
- `insider_roster` - Current insider holdings
- `earnings_estimates` - Analyst EPS estimates (quarterly)
- `earnings_history` - Actual reported EPS (historical)
- `key_metrics` - PE ratio, PB ratio, debt ratios, etc.

**Data Coverage:**
- Company profile: 515/515 (100%)
- Earnings estimates: 7/515 (1.4%) ← **Critical gap: yfinance has limited earnings estimate data**
- Institutional positioning: 209/515 (40.6%)
- Insider data: 515/515 (100%)
- Key metrics: ~400/515 (77%)

**Root Cause of Gaps:** 
- yfinance API returns limited analyst estimate data for many stocks
- Consider alternative data source (FactSet, Seeking Alpha API)

**Key Note:** This is a consolidation of what used to be:
- loadinfo.py (company profile)
- loadpositioning.py (institutional holders)
- loadinsiders.py (insider transactions)
- loadearningsestimate.py (analyst estimates)
- loadearningshistory.py (historical earnings)

---

## ANALYST DATA LOADERS

### loadanalystsentiment.py
**Tables Populated:**
- `analyst_sentiment_analysis` - Analyst ratings (buy/hold/sell), price targets, rating changes

**Data Coverage:** 359/515 (69.7%)
**Key Fields:** symbol, rating, rating_change, target_price, date, analyst_count

---

### loadanalystupgradedowngrade.py
**Tables Populated:**
- `analyst_upgrade_downgrade` - Recent analyst rating changes with dates and rationales

**Data Coverage:** 193/515 (37.5%)
**Key Fields:** symbol, date, action (upgrade/downgrade), from_rating, to_rating, analyst_name

---

## OPTIONS DATA LOADER

### loadoptionschains.py
**Tables Populated:**
- `options_chains` - Options contract details (calls, puts, strike prices, volumes)

**Data Coverage:** 1/515 (0.2%) ← **Critical gap: yfinance options API very limited**
**Key Fields:** symbol, expiration_date, strike, option_type (call/put), bid, ask, volume, open_interest, implied_volatility

**Root Cause of Gap:**
- yfinance options API is incomplete and times out frequently
- Most brokers require API authentication for real-time options data
- Alternative: Use yfinance.Ticker.option_chain() with better error handling

---

## FINANCIAL STATEMENT LOADERS

### loadannualincomestatement.py
**Tables Populated:**
- `annual_income_statement` - Revenue, costs, net income, EPS

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, period, total_revenue, cost_of_revenue, net_income, eps, period_end_date

---

### loadannualbalancesheet.py
**Tables Populated:**
- `annual_balance_sheet` - Assets, liabilities, equity

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, period, total_assets, total_liabilities, stockholders_equity, period_end_date

---

### loadannualcashflow.py
**Tables Populated:**
- `annual_cash_flow` - Operating, investing, financing cash flows

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, period, operating_cash_flow, investing_cash_flow, financing_cash_flow

---

### loadquarterlyincomestatement.py
**Tables Populated:**
- `quarterly_income_statement` - Quarterly revenue, costs, net income

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, quarter, total_revenue, net_income, period_end_date

---

### loadquarterlybalancesheet.py
**Tables Populated:**
- `quarterly_balance_sheet` - Quarterly balance sheet items

**Data Coverage:** 515/515 stocks (100%)

---

### loadquarterlycashflow.py
**Tables Populated:**
- `quarterly_cash_flow` - Quarterly cash flow statements

**Data Coverage:** 515/515 stocks (100%)

---

### loadttmincomestatement.py
**Tables Populated:**
- `ttm_income_statement` - Trailing Twelve Months (TTM) income data for trailing analysis

**Data Coverage:** 515/515 stocks (100%)
**Purpose:** Shows most recent 12 months of financial performance

---

### loadttmcashflow.py
**Tables Populated:**
- `ttm_cash_flow` - TTM cash flow data

**Data Coverage:** 515/515 stocks (100%)

---

## EARNINGS DATA LOADERS

### loadearningshistory.py
**Tables Populated:**
- `earnings_history` - Historical actual reported earnings by quarter

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, quarter, actual_eps, reported_date, period_end_date

**Note:** This is now consolidated into loaddailycompanydata.py

---

### loadearningsrevisions.py
**Tables Populated:**
- `earnings_revisions` - Analyst estimate revisions over time

**Data Coverage:** Variable (~300-400/515)
**Key Fields:** symbol, date, estimate_before, estimate_after, revision_count

---

## SECTOR & INDUSTRY LOADERS

### loadsectors.py
**Tables Populated:**
- `sectors` - Static list of sector definitions

**Data Coverage:** ~11 major sectors (Technology, Healthcare, Finance, etc.)
**Purpose:** Reference table for sector grouping

---

### loadsectorranking.py
**Tables Populated:**
- `sector_ranking` - Sector performance rankings and metrics

**Data Coverage:** 11/11 sectors (100%)
**Key Fields:** sector_name, rank, performance, momentum, avg_pe_ratio, market_cap

---

### loadindustryranking.py
**Tables Populated:**
- `industry_ranking` - Industry performance rankings

**Data Coverage:** ~140 industries (100% of tracked industries)
**Key Fields:** industry_name, rank, performance, momentum, stocks_count

---

## STOCK SCORE LOADERS

### loadstockscores.py
**Tables Populated:**
- `stock_scores` - Composite quality scores for each stock

**Data Coverage:** 515/515 stocks (100%)
**Score Components:**
- Quality score (profitability, balance sheet strength)
- Growth score (revenue/earnings growth rates)
- Stability score (earnings consistency, dividend stability)
- Momentum score (relative strength, trend)
- Value score (PE ratio vs peers, free cash flow yield)
- Positioning score (analyst sentiment, insider activity)

**Key Fields:** symbol, date, quality_score, growth_score, stability_score, momentum_score, value_score, positioning_score, composite_score

---

## MACRO & MARKET DATA LOADERS

### loadmarket.py
**Tables Populated:**
- `market_data` - Overall market indices and macro overview

**Data Coverage:** US market (SPY, QQQ, DIA, VIX, etc.)
**Key Fields:** index_symbol, price, change_percent, date, market_cap (aggregate)

---

### loadmarketindices.py
**Tables Populated:**
- `market_indices` - Additional market indices for comparative analysis

**Data Coverage:** 20+ indices (Russell 2000, Nikkei, DAX, CAC40, etc.)

---

### loadfactormetrics.py
**Tables Populated:**
- `factor_metrics` - Factor model exposures (value, momentum, quality, low volatility)

**Data Coverage:** 515/515 stocks (100%)
**Key Fields:** symbol, date, value_exposure, momentum_exposure, quality_exposure, size_exposure, volatility_exposure

---

## OTHER DATA LOADERS

### loadfeargreed.py
**Tables Populated:**
- `cnn_fear_greed_index` - Daily CNN Fear & Greed index

**Data Coverage:** 1 index, daily updates
**Key Fields:** date, fear_greed_value (0-100), trend

---

### loadnaaim.py
**Tables Populated:**
- `naaim_index` - Investor sentiment from NAAIM (National Association of Active Investment Managers)

**Data Coverage:** Weekly updates
**Key Fields:** date, bullish_percent, neutral_percent, bearish_percent

---

### loadcommodities.py
**Tables Populated:**
- `commodities_data` - Futures prices for major commodities

**Data Coverage:** Crude oil, natural gas, gold, copper, wheat, etc.
**Key Fields:** commodity_symbol, date, price, change_percent

---

### loadecondata.py
**Tables Populated:**
- `economic_data` - Economic indicators (GDP, unemployment, inflation, etc.)

**Data Coverage:** US economic data, monthly/quarterly
**Key Fields:** indicator_name, date, value, previous_value, forecast

---

### loadrelativeperformance.py
**Tables Populated:**
- `relative_performance` - Stock performance vs benchmark (SPY)

**Data Coverage:** 515/515 stocks
**Key Fields:** symbol, period, return_vs_spy, alpha, beta, sharpe_ratio

---

### loadseasonality.py
**Tables Populated:**
- `seasonality_data` - Average returns by month/quarter historically

**Data Coverage:** Historical patterns for stocks and sectors
**Key Fields:** symbol, month, avg_return, win_rate, period_avg_return

---

### loadsecfilings.py
**Tables Populated:**
- `sec_filings` - Recent SEC filings (10-K, 10-Q, 8-K)

**Data Coverage:** Latest filings for 515 stocks
**Key Fields:** symbol, filing_type, filing_date, url, key_dates

---

## SUMMARY BY DATA COVERAGE

### 100% Coverage (515/515)
- Price data (daily, weekly, monthly)
- Technical signals (daily, weekly, monthly)
- Buy/sell signals (stocks and ETFs)
- Financial statements (annual, quarterly, TTM)
- Earnings history (actual reported)
- Stock scores
- Company fundamentals (basic)
- Factor metrics
- Relative performance
- All latest price caches

### 70%+ Coverage (359-400/515)
- Analyst sentiment (69.7% - 359/515)
- Key metrics (77%)
- Economic data

### 40-70% Coverage
- Institutional positioning (40.6% - 209/515)
- Analyst upgrades (37.5% - 193/515)
- Earnings revisions (~60%)

### <5% Coverage (BROKEN)
- Earnings estimates (1.4% - 7/515) ← **yfinance API limitation**
- Options chains (0.2% - 1/515) ← **yfinance API limitation**

---

## DEBUGGING LOADERS

### Check if a loader populated data:
```sql
-- Example: Check earnings_estimates data
SELECT COUNT(DISTINCT symbol) FROM earnings_estimates;

-- Check institutional_positioning
SELECT COUNT(DISTINCT symbol) FROM institutional_positioning;

-- Check buy_sell signals
SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily 
WHERE signal IN ('Buy', 'Sell');

-- Check sector ranking
SELECT COUNT(*) FROM sector_ranking;
```

### Run a single loader (for debugging):
```bash
python loadanalystsentiment.py
# Watch for errors in console output
# Check corresponding table with SELECT COUNT queries
```

### Run all loaders in parallel (complete data refresh):
```bash
bash run-all-loaders.sh
# Takes 30-60 minutes depending on API rate limits
# Check /tmp/*.log for individual loader progress
```

---

## CRITICAL ISSUES & SOLUTIONS

### Issue 1: earnings_estimates Only 7/515 Stocks
**Root Cause:** yfinance API doesn't provide comprehensive analyst estimates
**Solution Options:**
1. Use earnings_history instead (has 515/515 stocks with actual earnings)
2. Integrate with FactSet API (requires subscription)
3. Integrate with Seeking Alpha API (beta, requires scraping)
4. Mark as "Not Available" in frontend, don't show 0s

**Recommendation:** Use earnings_history for actual earnings, find separate source for estimates

---

### Issue 2: options_chains Only 1/515 Stocks
**Root Cause:** yfinance options API is incomplete and times out
**Solution Options:**
1. Implement retry logic with exponential backoff
2. Use polygon.io or IEX Cloud (requires subscription, better data)
3. Disable options endpoint until data source improves
4. Use Alpaca API for paper trading options (limited data but reliable)

**Recommendation:** Implement retry logic + timeout handlers, or disable until better data source available

---

### Issue 3: Some Analyst Data Only 37-70% Coverage
**Root Cause:** Not all stocks have active analyst coverage
**Solution:** This is normal - not all stocks have analyst ratings
**Action:** Frontend should handle missing data gracefully (empty state, no chart)

---

## Future Improvements

1. **Add Data Source Configuration**
   - Allow switching between yfinance, IEX Cloud, Polygon, etc.
   - Store source metadata in database

2. **Implement Loader Health Monitoring**
   - Log completion status for each loader
   - Alert when data coverage drops below threshold
   - Track API rate limit usage

3. **Add Incremental Loader Mode**
   - Don't re-fetch entire history each time
   - Only update new/changed data
   - Reduce API calls and run time

4. **Better Error Handling**
   - Gracefully skip failed symbols instead of failing entire loader
   - Partial updates to database instead of rollback on error
   - Better logging of what succeeded vs failed
