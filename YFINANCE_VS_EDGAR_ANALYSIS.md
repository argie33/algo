# yfinance vs EDGAR Data Source Analysis

**Prepared:** 2026-07-16 | **Codebase:** Trading Algorithm  
**Analysis Scope:** All data loaders, external APIs, and downstream metric dependencies

---

## Executive Summary

This trading algo uses a **hybrid data model**:
- **yfinance**: Market data, quote snapshots, economic indicators (30,000+ daily API calls)
- **SEC EDGAR**: Fundamental financial statements (6 statement/period combos per symbol, cached)

**Key Finding:** EDGAR cannot replace yfinance for most use cases. EDGAR provides historical financial statements (quarterly/annual, delayed 30-60 days); yfinance provides real-time/current metrics required for trading. A high-coverage hybrid approach is optimal.

---

## 1. yfinance Data Sources & Usage

### 1.1 What Data is Fetched from yfinance

| Data Type | API Method | Tables Written | Update Frequency | Why yfinance |
|-----------|-----------|-----------------|------------------|-------------|
| **OHLCV Prices** | `yfinance.download()` | price_daily, etf_price_daily | Daily (1d bars) | Index symbols (^VIX, ^GSPC) not on SEC; fastest data source |
| **Quote Snapshots** | `yfinance.Ticker.info` | yfinance_snapshot | Daily (20h freshness) | Real-time metrics, market cap, sector, analyst data |
| **Valuation Metrics** | `Ticker.info` (trailingPE, priceToBook, etc.) | value_metrics | Daily | Current ratios, not available in SEC filings (delayed) |
| **Positioning Metrics** | `Ticker.info` (shortsPercentOfFloat, heldPercentInstitutions) | positioning_metrics | Daily | Real-time short interest, insider/institutional holdings |
| **Analyst Sentiment** | `Ticker.info` (recommendationKey, numberOfAnalysts) | analyst_sentiment_analysis | Daily | Analyst consensus, ratings (not in SEC filings) |
| **Earnings Dates** | `Ticker.info` (earningsDate) | earnings_calendar | Daily | Next earnings announcement (needed for risk mgmt) |
| **Beta & Volatility** | `Ticker.info` (beta) | stability_metrics | Daily | Market correlation beta (technical, not in SEC) |
| **Company Profile** | `Ticker.info` (sector, industry, website) | company_profile | Daily | Industry classification, metadata |
| **VIX (Volatility Index)** | `yfinance.download("^VIX")` | price_daily | Daily | Market volatility for circuit breaker logic (^VIX symbol) |
| **Economic Indicators** | `yfinance.download("DX-Y.NYB")` | economic_data | Daily | US Dollar Index (ICE DXY) - currency exposure |
| **Put/Call Ratio** | `yfinance.Ticker.options` | market_health_daily | Daily | Options chain open interest (not in SEC) |
| **Dividend Data** | `Ticker.info` (dividendYield) | value_metrics | Daily | Current yield (real-time) |
| **FCF Yield** | `Ticker.info` (freeCashflow) | value_metrics | Daily | Market cap / free cash flow ratio |

### 1.2 yfinance API Call Volume & Architecture

**Consolidation Strategy (CRITICAL FIX 2026-07-02):**
```
Before: 6+ loaders each calling yfinance independently (~30,000 API calls/run)
After:  Single load_yfinance_snapshot.py → all 6+ loaders read from DB table

Flow:
  1. load_yfinance_snapshot.py fetches ALL symbols once via Ticker.info (5,300 symbols)
  2. Stores in yfinance_snapshot table (single row per symbol with 27 fields)
  3. Downstream loaders read from snapshot table instead of re-calling yfinance:
     - load_yfinance_derived_metrics.py → value_metrics, positioning_metrics, company_profile, earnings_calendar, analyst_sentiment_analysis
     - All other metric loaders
```

**Call Rate & Circuit Breaking:**
- **Per-process throttling:** 0.3s minimum interval (2026-06-28 optimization)
- **Shared IP circuit breaker:** PostgreSQL-coordinated across 6 ECS tasks
- **Batch fetch:** Symbols grouped in 50-symbol batches for iteration, but each still costs 1 HTTP request
- **Freshness skip:** Symbols with snapshots <20 hours old are skipped (reduces re-runs from ~5,300 → tail only)
- **Retry logic:** Exponential backoff on 429 rate limit errors
- **Caching:** Ticker objects cached 24 hours to reduce API calls under rate limit stress

**Failure Mode:**
- yfinance shared AWS IP frequently banned (Session 184: rate limited 48h straight)
- Fallback: `PRICE_DATA_SOURCE=alpaca` environment variable for price data only
- No fallback for snapshot metrics (PE, analyst data, etc.) - must wait for circuit breaker recovery

### 1.3 Tables Written by yfinance

| Table | Columns | Primary Key | Purpose | Update Frequency |
|-------|---------|-------------|---------|------------------|
| **yfinance_snapshot** | symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, market_cap, held_percent_insiders, held_percent_institutions, short_interest, beta, 52w_high, 52w_low, sector, industry, country, exchange, website, long_name, earnings_date, earnings_dates, recommendation_key, number_of_analysts, analysts_underweight, analysts_overweight, analysts_hold, data_available, unavailable_reason, fetched_at | (symbol) | Single source of truth for all yfinance-derived metrics | Daily, 20h freshness skip |
| **price_daily** | symbol, date, open, high, low, close, volume, adjusted_close | (symbol, date) | Daily OHLCV for stocks (5,000+ symbols) | Daily after market close |
| **etf_price_daily** | symbol, date, open, high, low, close, volume, adjusted_close | (symbol, date) | Daily OHLCV for ETFs (500+ symbols) | Daily after market close |
| **price_weekly** | symbol, date, open, high, low, close, volume, adjusted_close | (symbol, date) | Weekly bars derived from price_daily in SQL (not fetched) | After daily load |
| **price_monthly** | symbol, date, open, high, low, close, volume, adjusted_close | (symbol, date) | Monthly bars derived from price_daily in SQL (not fetched) | After daily load |
| **value_metrics** | symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, market_cap, data_unavailable, reason, updated_at | (symbol) | Valuation multiples for stock scoring | Daily from yfinance_snapshot |
| **positioning_metrics** | symbol, short_interest, held_percent_insiders, held_percent_institutions, data_unavailable, reason, updated_at | (symbol) | Insider/institutional ownership, short interest | Daily from yfinance_snapshot |
| **company_profile** | ticker, long_name, sector, industry, country, exchange, website, data_unavailable, reason, updated_at | (ticker) | Company metadata for dashboard/filtering | Daily from yfinance_snapshot |
| **analyst_sentiment_analysis** | symbol, recommendation_key, number_of_analysts, analysts_overweight, analysts_hold, analysts_underweight, data_unavailable, reason, updated_at | (symbol) | Analyst consensus ratings | Daily from yfinance_snapshot |
| **earnings_calendar** | symbol, earnings_date, fiscal_end_date, data_unavailable, reason, updated_at | (symbol) | Upcoming earnings for risk management | Daily from yfinance_snapshot |
| **market_health_daily** | date, vix_close, vix_high, vix_low, put_call_ratio, yield_curve_2_10, distribution_days, breadth_percent, data_unavailable, reason | (date) | Market regime indicators | Daily |
| **economic_data** | series_id, date, value, data_unavailable, reason | (series_id, date) | FRED series (T10Y2Y, FEDFUNDS, HY OAS, claims) + DXY | Daily |

### 1.4 yfinance Data Quality Issues & Mitigations

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| **Shared AWS IP rate limiting** | Entire pipeline stalls; 429 errors block all loaders for hours | Shared circuit breaker with exponential backoff; fallback to Alpaca for prices; manual trigger scripts |
| **Invalid Crumb errors** | Lambda/ECS environments lose yfinance.download() access | YFinanceWrapper retry logic; per-process caching |
| **Delayed/missing data** | 52-week highs, earnings dates sometimes NULL | Return data_unavailable marker instead of silent fallback per governance |
| **ETF vs stock pricing** | Split price tables (price_daily vs etf_price_daily) | Separate loaders, but both feed same technical_data and market_health tables |
| **Market close time mismatches** | US markets close 4 PM ET; yfinance updates ~5 PM ET; pipeline at 4:05 PM | Grace period: latest 30-min window accepted |

---

## 2. SEC EDGAR Data Sources & Usage

### 2.1 What Data is Fetched from SEC EDGAR

| Data Type | Statement Type | Period(s) | Tables Written | Why EDGAR | Availability |
|-----------|---|---|---|---|---|
| **Revenue** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | Official audited source (XBRL) | ~95% of US-listed companies |
| **Cost of Revenue** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | XBRL standard accounting line item | ~80% of active symbols |
| **Gross Profit** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | Calculated from revenue - COGS | ~80% |
| **Operating Income** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | Business profitability (before financing) | ~90% |
| **Net Income** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | Bottom line (official tax filings) | ~95% |
| **Earnings Per Share** | Income Statement | Annual, Quarterly | annual_income_statement, quarterly_income_statement | Diluted EPS (audited) | ~95% |
| **Total Assets** | Balance Sheet | Annual, Quarterly | annual_balance_sheet, quarterly_balance_sheet | Balance sheet item (audited) | ~95% |
| **Current Assets** | Balance Sheet | Annual, Quarterly | annual_balance_sheet, quarterly_balance_sheet | Liquidity measurement | ~95% |
| **Total Liabilities** | Balance Sheet | Annual, Quarterly | annual_balance_sheet, quarterly_balance_sheet | Debt measurement | ~95% |
| **Current Liabilities** | Balance Sheet | Annual, Quarterly | annual_balance_sheet, quarterly_balance_sheet | Short-term obligations | ~95% |
| **Stockholders' Equity** | Balance Sheet | Annual, Quarterly | annual_balance_sheet, quarterly_balance_sheet | Net worth / book value | ~95% |
| **Operating Cash Flow** | Cash Flow | Annual, Quarterly | annual_cash_flow_statement, quarterly_cash_flow_statement | Cash generation (not accrual earnings) | ~95% |
| **Investing Cash Flow** | Cash Flow | Annual, Quarterly | annual_cash_flow_statement, quarterly_cash_flow_statement | Capital deployment | ~90% |
| **Financing Cash Flow** | Cash Flow | Annual, Quarterly | annual_cash_flow_statement, quarterly_cash_flow_statement | Dividend/debt changes | ~90% |
| **Capital Expenditures** | Cash Flow | Annual, Quarterly | annual_cash_flow_statement, quarterly_cash_flow_statement | CapEx investment | ~90% |

### 2.2 EDGAR API Architecture

**Data Flow:**
```
1. SecEdgarClient.get_company_facts(cik) → SEC XBRL API
   - Fetches all XBRL facts for a company in one request
   - Returns nested JSON: facts → us-gaap → concept → units → values
   
2. SecEdgarStatementLoader.fetch_incremental(symbol, since) → SecEdgarClient
   - Converts symbol → CIK (via cached ticker mapping)
   - Extracts specific XBRL concepts (Revenues, Assets, etc.)
   - Filters to annual/quarterly periods
   - Normalizes Decimal NaN values
   
3. store → DB tables (annual_income_statement, etc.)
   - One row per symbol-period combination
   - Fields mapped from XBRL concepts via _INCOME_FIELD_MAPPING, etc.
```

**Rate Limiting:**
- **SEC limit:** <10 requests/sec (firm regulatory limit)
- **Implementation:** 2 req/sec per task (8 req/sec across 4 tasks = safe margin)
- **Caching:** Companyfacts JSON cached in-memory (LRU, 4-entry limit) to avoid re-fetching multi-MB payloads
  - 6 statement/period outputs per symbol = 6 EDGAR API calls before cache
  - With cache: 1 API call, 6 local extractions = 6x faster

**Challenges:**
- **Delayed data:** 10-K/10-Q filed 30-60 days after fiscal period end
- **SEC XBRL quirks:** NaN Decimal values require cleaning; some concepts vary by filer
- **Multiple concepts per metric:** Revenue reported as "Revenues", "Sales Revenue Net", or "Revenue from Contract with Customer" depending on accounting standard used
- **Negative cache:** 404 errors (companies w/o filings, delisted) cached as permanent to avoid repeated failed requests
- **No quarterly data for ~10% of companies** (small caps, foreign issuer ADRs)

### 2.3 Tables Written by SEC EDGAR

| Table | Columns | Primary Key | Coverage | Update Frequency |
|-------|---------|-------------|----------|------------------|
| **annual_income_statement** | symbol, fiscal_year, revenue, cost_of_revenue, gross_profit, operating_income, net_income, earnings_per_share, data_unavailable, reason, updated_at | (symbol, fiscal_year) | ~4,500 symbols (annual filings only) | After 10-K filing (30-60 days late) |
| **quarterly_income_statement** | symbol, fiscal_year, fiscal_quarter, revenue, cost_of_revenue, gross_profit, operating_income, net_income, earnings_per_share, data_unavailable, reason, updated_at | (symbol, fiscal_year, fiscal_quarter) | ~4,200 symbols (quarterly filings) | After 10-Q filing (30-45 days late) |
| **annual_balance_sheet** | symbol, fiscal_year, total_assets, current_assets, total_liabilities, current_liabilities, stockholders_equity, data_unavailable, reason, updated_at | (symbol, fiscal_year) | ~4,500 symbols | After 10-K filing |
| **quarterly_balance_sheet** | symbol, fiscal_year, fiscal_quarter, total_assets, current_assets, total_liabilities, current_liabilities, stockholders_equity, data_unavailable, reason, updated_at | (symbol, fiscal_year, fiscal_quarter) | ~4,200 symbols | After 10-Q filing |
| **annual_cash_flow_statement** | symbol, fiscal_year, operating_cash_flow, investing_cash_flow, financing_cash_flow, capital_expenditures, data_unavailable, reason, updated_at | (symbol, fiscal_year) | ~4,500 symbols | After 10-K filing |
| **quarterly_cash_flow_statement** | symbol, fiscal_year, fiscal_quarter, operating_cash_flow, investing_cash_flow, financing_cash_flow, capital_expenditures, data_unavailable, reason, updated_at | (symbol, fiscal_year, fiscal_quarter) | ~4,200 symbols | After 10-Q filing |

### 2.4 EDGAR Coverage & Gaps

**Available Coverage (US-listed companies):**
- S&P 500: 100%
- Russell 1000: 99%
- Russell 2000: ~80%
- Total US active symbols in algo: ~5,300 → ~4,500 have EDGAR data (85%)

**Missing Coverage (15%):**
- **IPOs <90 days old** (no filings yet)
- **Delisted companies** (hard delists, OTC)
- **Foreign ADRs** (some file 20-F annually only)
- **Blank check / SPACs** (minimal financials until merger)
- **Micro caps** (symbols with <$50M market cap often don't file)

---

## 3. Data Gaps: What yfinance Provides That EDGAR Cannot

### 3.1 Market Data (No EDGAR Alternative)

| Metric | Source | Why EDGAR Can't | Frequency | Critical? |
|--------|--------|---|---|---|
| **OHLCV Prices** | yfinance | Not in SEC filings (market data, not company filings) | Real-time | YES |
| **VIX Index** | yfinance (^VIX ticker) | Index, not a company; no SEC filings for indices | Real-time | YES (circuit breaker) |
| **US Dollar Index (DXY)** | yfinance (DX-Y.NYB) | Currency index; not a security | Daily | NO (enrichment) |
| **Put/Call Ratio** | yfinance options chain | Real-time options data; not in SEC filings | Daily | NO (enrichment) |
| **Dividends (trailing)** | yfinance (dividendYield) | EDGAR has declared, not real-time payments | Real-time | NO (enrichment) |

### 3.2 Quote Snapshots (Current Metrics, Not Historical)

| Metric | Source | EDGAR Alternative | Frequency | Gap |
|--------|--------|---|---|---|
| **Trailing P/E Ratio** | yfinance `trailingPE` | Must compute: price / (latest_eps * diluted_shares) | Real-time | EDGAR EPS is quarterly, delayed 45 days; yfinance is daily |
| **Price-to-Book** | yfinance `priceToBook` | Must compute: market_cap / total_equity | Real-time | EDGAR equity is Q/A, delayed 30-60 days |
| **Price-to-Sales** | yfinance `priceToSalesTrailing12Months` | Must compute: market_cap / (trailing_revenue) | Real-time | EDGAR revenue is delayed |
| **PEG Ratio** | yfinance `pegRatio` | Not available in EDGAR (requires analyst estimates) | Real-time | EDGAR has no earnings growth estimates |
| **Market Cap** | yfinance `marketCap` | Can compute: price * shares_outstanding | Real-time | EDGAR shares outstanding is delayed |
| **Free Cash Flow Yield** | yfinance computed from FCF | Must compute: fcf / market_cap | Real-time | Market cap is real-time; FCF is annual (delayed) |
| **Beta** | yfinance `beta` | Not in EDGAR; must compute 252-day correlation | Daily | EDGAR has no price history |
| **52-week High/Low** | yfinance | Not in EDGAR; must read price_daily table | Daily | EDGAR has no prices |

### 3.3 Analyst Data (Not in SEC Filings)

| Metric | Source | EDGAR Alternative | Availability |
|--------|--------|---|---|
| **Recommendation Key** | yfinance `recommendationKey` | Not available (no consensus ratings in 10-K/10-Q) | ~70% of active symbols |
| **Analyst Count** | yfinance `numberOfAnalysts` | Not available | ~70% of active symbols |
| **Overweight/Hold/Underweight Counts** | yfinance | Not available | ~70% of active symbols |
| **Analyst Upgrades/Downgrades** | Bloomberg, Seeking Alpha (not in algo) | Not in SEC filings (proprietary research) | N/A |
| **Price Targets** | Bloomberg, Seeking Alpha | Not in SEC filings | N/A |

### 3.4 Real-Time Positioning Data (Not in SEC Filings)

| Metric | Source | EDGAR Alternative | Lag |
|--------|--------|---|---|
| **Short Interest (% of float)** | yfinance `shortPercentOfFloat` | Not in SEC filings; sourced from exchange data | Delayed 2 weeks (SEC short sale file) |
| **Insider Ownership %** | yfinance `insidersPercentHeld` | In 10-K/4 filings, but stale (annual or transaction-based) | 30-60 days old for 10-K; real-time for Form 4s (separate feed) |
| **Institutional Ownership %** | yfinance `heldPercentInstitutions` | In 13F filings (quarterly, 45 days late); 10-K has director/officer holdings only | Quarterly, 45 days old |

### 3.5 Technical & Economic Data (No Fundamental Equivalent)

| Metric | Source | Why Not EDGAR |
|--------|--------|---|
| **Moving Averages (SMA, EMA)** | Computed from price_daily | Technical; requires price history |
| **RSI, MACD, ATR, ADX** | Computed from price_daily | Technical indicators; no accounting equivalent |
| **Bollinger Bands** | Computed from price_daily | Technical; volatility-based |
| **VCP (Volatility Contraction Pattern)** | Computed from price_daily | Technical; chart pattern recognition |
| **Fed Funds Rate, Yield Curve, Initial Claims** | FRED (yfinance for DXY only) | Macroeconomic; not company-specific |

---

## 4. EDGAR Opportunities: What COULD Potentially Replace yfinance

### 4.1 Analysis: Can SEC Filings Replace Quote Snapshots?

**Conclusion: Partial replacement only, with significant tradeoffs.**

| Use Case | yfinance Current | EDGAR Alternative | Feasibility | Tradeoffs |
|----------|---|---|---|---|
| **Value scoring (PE, PB, PS)** | Daily, real-time | Compute from quarterly financials + current price | Medium | Requires daily price updates (not EDGAR); valuations 30-60 days stale |
| **Growth metrics** | Analyst estimates (PEG) | Compute from historical revenue/EPS growth (5-year) | High | No forward guidance (must use historical); estimates missing |
| **Dividend yield** | Real-time trailing | Compute from annual dividend payments (trailing 12m) | Medium | Historical; forward yield missing; special dividends not tracked |
| **Book value per share** | Via priceToBook | Compute: total_equity / shares_outstanding | High | Shares outstanding from 10-K (annual); must handle dilution |
| **Profitability margins** | In snapshot | Compute: net_income/revenue, operating_income/revenue | High | Annual/quarterly only; historical not real-time |
| **Debt ratios** | Not in snapshot | Compute: total_liabilities/total_assets, debt/equity | High | Annual/quarterly only; balance sheet dates lag |
| **ROE, ROA** | Not in snapshot | Compute: net_income/equity, net_income/assets | High | Annual/quarterly; must handle negative values |
| **Free cash flow yield** | In snapshot (computed) | Compute: operating_cash_flow - capex / market_cap | Medium | Annual/quarterly; market cap needs real-time price |
| **Earnings date** | In snapshot | Not in SEC filings; Form 8-K announcements | Low | Must track 8-K filings or use third-party feed |
| **Insider ownership %** | In snapshot | Form 4 filings (transaction-level) or 10-K (annual holdings) | Medium | Real-time from Form 4s requires separate SEC filing tracking |
| **Institutional ownership %** | In snapshot | 13F filings (quarterly, 45 days late) | Low | Delayed 45 days; 10-K only has director holdings |
| **Short interest %** | In snapshot | Not in SEC filings; must use FINRA short sale file | Low | Delayed 2 weeks; separate data source needed |

### 4.2 Data Quality Issues with SEC-Only Approach

**Issue 1: Stale Valuation Multiples**
```
Today (2026-07-16): AAPL trading $250
Latest EDGAR 10-Q: Filed 2026-04-30 (78 days ago) with Q2 EPS = $1.50

yfinance trailingPE: 250 / 6.25 (annualized) = 40x
EDGAR-computed trailingPE: 250 / 1.50 (Q2 only) = 167x (misleading!)

Workaround: Track last 4 quarters of earnings manually → stale after each earnings release
```

**Issue 2: Missing Forward Guidance**
```
PEG Ratio (Price / Earnings Growth Rate):
- yfinance gets analyst growth estimates (unavailable in EDGAR)
- EDGAR alternative: compute historical 5-year EPS CAGR
- Problem: Historical growth ≠ forward growth; misses inflection points

Example: Amazon 2016 (accelerating growth) vs 2022 (decelerating)
Historical PEG would underestimate 2016, overestimate 2022
```

**Issue 3: Quarterly vs Annual Data Frequency**
```
Quarterly income statements available ~45 days after period end
Annual income statements available ~60 days after year-end (10-K)

Trading app updates daily; value_metrics scores refresh daily
EDGAR update: 1x per quarter at best → scores stale for 3 months
```

**Issue 4: Special Events Not Tracked**
```
Dividends: yfinance has trailing 12m; EDGAR has declared only
Earnings surprises: yfinance estimates/actual; EDGAR actual only (no expectations)
Stock splits: yfinance adjusts automatically; EDGAR requires manual adjustments
```

### 4.3 Most Feasible Hybrid Approach

**IF EDGAR were to replace yfinance for fundamentals:**

1. **Keep yfinance for:**
   - Real-time prices (OHLCV)
   - Market sentiment (VIX, put/call, analyst ratings)
   - Daily quote snapshots (current PE, dividend yield, market cap)
   - 52-week high/low

2. **Compute from EDGAR for:**
   - ROE, ROA (from annual balance sheet + income statement)
   - Debt ratios (current liabilities/assets)
   - Operating/gross margins
   - 5-year revenue/EPS growth rates
   - Free cash flow metrics (OCF - CapEx)

3. **Require separate feeds for:**
   - Short interest (FINRA, not SEC)
   - Insider transactions (Form 4 tracking, not in EDGAR companyfacts)
   - Earnings estimates (not in EDGAR; Bloomberg/FactSet only)

---

## 5. Data Freshness & Update Cadence

### 5.1 Update Frequency Matrix

| Data Source | Table(s) | Fetch Frequency | Typical Delay | Max Age Allowed |
|-------------|---|---|---|---|
| **yfinance (prices)** | price_daily, etf_price_daily | Daily (after 4 PM ET) | 30-60 min (4:30 PM ET) | 1 day (max grace 4:05-4:35 PM) |
| **yfinance (snapshot)** | yfinance_snapshot | Daily (5:00 PM ET start) | ~2-3 hours (runs 2-3h) | 20 hours (freshness skip) |
| **yfinance (VIX)** | price_daily (^VIX symbol) | Daily (included in price loader) | 30-60 min | 1 day (CRITICAL for circuit breaker) |
| **yfinance (DXY)** | economic_data | Daily (load_economic_data) | 1-2 hours | 1 day |
| **SEC EDGAR** | annual/quarterly statements | Quarterly (10-K/10-Q) | 30-60 days after period end | 90 days (acceptable for scoring) |
| **FRED** | economic_data (FRED series) | Daily | 1 day (next business day) | 2 days |
| **Technical indicators** | technical_data_daily | Daily (computed from prices) | 15-20 min after prices load | 1 day |
| **Market health** | market_health_daily | Daily | 30-45 min after prices | 1 day |
| **Stock scores** | stock_scores | Daily (after metrics load) | 2-3 hours after market close | 1 day |

### 5.2 Critical Path (Evening Pipeline)

```
16:00 → Market close; yfinance starts collecting data
16:30 → Phase 1: Fetch prices (price_daily loads)
17:00 → VIX, economic data available in DB
17:15 → Phase 2: Compute technical indicators (SMA, RSI, etc.)
17:35 → Phase 3: Load yfinance_snapshot (5,300 symbols × quoteSummary)
       → (This takes 2-3 hours due to API throttling)
18:00 → Phase 4: Load financial statements (SEC EDGAR) – runs in parallel
20:30 → Phase 5: Compute quality/growth metrics (from EDGAR)
20:45 → Phase 6: Compute value metrics (from yfinance_snapshot)
21:00 → Phase 7: Compute risk metrics (from prices + market_health)
21:15 → Phase 8: Final stock scoring (all inputs ready)
22:00 → Complete; pipeline result persisted to algo_orchestrator_runs

Data freshness guarantee:
  - Prices: <2 hours old ✓
  - Technical: <2.5 hours old ✓
  - Valuations (PE, PB): <5 hours old ✓
  - Fundamentals (ROE, debt): 30-60 days old (acceptable)
  - Analyst ratings: <5 hours old ✓
```

### 5.3 Freshness Issues & Recovery

| Issue | Cause | Detection | Recovery |
|-------|-------|-----------|----------|
| **yfinance rate limited** | Shared AWS IP banned | VIX or prices not updated for >2 hours | Wait 5-24 hours; manual trigger; Alpaca fallback for prices |
| **SEC EDGAR unreachable** | Rate limit exceeded or API timeout | quarterly_income_statement stale >7 days | Restart load_financial_statements with retries |
| **FRED API key missing** | Secrets manager not configured | economic_data missing FRED series | Manually set FRED_API_KEY env var |
| **Market close delay** | Prices delayed >45 min from market close | technical_data_daily has old prices; circuit breaker may halt | Wait for prices; manual refresh if critical |

---

## 6. Dependency Analysis: Data Source → Metric Tables

### 6.1 Dependency Graph (Data Source → Metric Table)

```
╔════════════════════════════════════════════════════════════════╗
║                    DATA SOURCES                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  yfinance.download(prices)  yfinance.Ticker.info   SEC EDGAR  ║
║         ↓                          ↓                  ↓        ║
║   price_daily           yfinance_snapshot      financial_stmt  ║
║   etf_price_daily                                               ║
║         ↓                          ↓                  ↓        ║
║         └──────────────┬──────────┴────────────────┬──────────┘
║                        ↓                           ↓           ║
║              ╔═════════════════╗      ╔════════════════════╗   ║
║              ║ METRIC TABLES   ║      ║  METRIC TABLES     ║   ║
║              ╚═════════════════╝      ╚════════════════════╝   ║
║                        ↓                           ↓           ║
║       • technical_data_daily                • quality_metrics  ║
║       • market_health_daily       (ROE, margins, debt ratios)   ║
║       • value_metrics                                          ║
║       • positioning_metrics              • growth_metrics      ║
║       • analyst_sentiment_analysis    (revenue/EPS growth)     ║
║       • stability_metrics                                      ║
║       • earnings_calendar                 • risk_metrics       ║
║       • company_profile              (P&L correlation, VaR)    ║
║                                                                ║
║              ╚═══════════════════════════════════════════════╝ ║
║                        ↓ (all feed into)                      ║
║                    stock_scores                               ║
║                  (daily rankings)                             ║
╚════════════════════════════════════════════════════════════════╝
```

### 6.2 Per-Metric-Table Dependency Breakdown

| Metric Table | Primary Data Source | Secondary | Tertiary | Dependency Notes |
|---|---|---|---|---|
| **value_metrics** | yfinance_snapshot (PE, PB, PS, PEG, div yield, FCF yield) | price_daily (market cap derived) | None | Single snapshot read; daily update; data_available flag if yfinance fails |
| **positioning_metrics** | yfinance_snapshot (short %, insider %, institution %) | None | None | Single snapshot read; daily update; optional enrichment (non-critical) |
| **analyst_sentiment_analysis** | yfinance_snapshot (analyst counts, recommendation key) | None | None | Single snapshot read; daily update; ~70% coverage (missing for delisted) |
| **earnings_calendar** | yfinance_snapshot (earnings_date) | None | None | Single snapshot read; daily update; used for risk management |
| **company_profile** | yfinance_snapshot (sector, industry, country, exchange, website, name) | None | None | Single snapshot read; daily update; used for filtering/grouping |
| **stability_metrics** | yfinance_snapshot (beta) | technical_data_daily (volatility, correlation) | None | Beta from yfinance; volatility computed from prices; CRITICAL for stability score |
| **technical_data_daily** | price_daily (OHLCV for all symbols) | None | None | Computed indicators: SMA, RSI, MACD, Bollinger, ATR, ADX, VCP; 15-25 min run |
| **market_health_daily** | price_daily (^VIX), economic_data (yield curve) | technical_data_daily (optional) | None | VIX CRITICAL (circuit breaker); put/call optional; yield curve for regime |
| **quality_metrics** | annual_balance_sheet, annual_income_statement (SEC EDGAR) | quarterly_income_statement (optional) | None | Computed: ROE, ROA, margins, debt ratios; 30-60 days old (EDGAR delay) |
| **growth_metrics** | annual_income_statement (SEC EDGAR, 5-10 years) | quarterly_income_statement (optional) | None | Computed: revenue/EPS growth; 30-60 days old; requires >3 years history |
| **risk_metrics_daily** | market_health_daily (VIX, breadth, market stage) | price_daily (P&L correlation) | portfolio_positions | Portfolio-level: beta, correlation, VaR; depends on holdings |
| **stock_scores** | value_metrics, quality_metrics, growth_metrics, stability_metrics, positioning_metrics | technical_data_daily (optional momentum) | None | Composite score: 60% fundamentals, 25% value, 15% technical; all 5 tables required |

### 6.3 Critical Dependency Chains

**Chain 1: Evening EOD Pipeline (Metrics → Scores)**
```
Trigger: 4:05 PM ET
    ↓
1. Price Loader (yfinance)
   → price_daily loaded (~30 min)
   ↓
2. Technical Indicators (compute from prices)
   → technical_data_daily loaded (~20 min)
   ↓
3. Market Health (VIX from prices, yield curve from FRED)
   → market_health_daily loaded (~10 min)
   ↓
4. yfinance Snapshot (parallel with steps 1-3)
   → yfinance_snapshot loaded (~2-3 hours)
   ↓
5. Derived Metrics (read yfinance_snapshot)
   → value_metrics, positioning_metrics, company_profile, earnings_calendar loaded (~30 min)
   ↓
6. EDGAR Statements (parallel with steps 1-5)
   → annual_income_statement, annual_balance_sheet, annual_cash_flow loaded (~1 hour)
   ↓
7. Quality/Growth Metrics (read EDGAR)
   → quality_metrics, growth_metrics loaded (~30 min)
   ↓
8. Stability Metrics (read yfinance beta + technical volatility)
   → stability_metrics loaded (~10 min)
   ↓
9. Stock Scores (read all 5 metrics tables)
   → stock_scores loaded (~20 min)
   ↓
Complete: ~4.5 hours total; pipeline data age <5 hours
```

**Chain 2: Quality Score Dependency (BLOCKED SCENARIO)**
```
If SEC EDGAR fails:
  → quality_metrics not loaded
  → growth_metrics not loaded
  → stock_scores cannot compute fundamentals component
  → RESULT: Stock scores incomplete; trading signals degraded
  
Mitigation: Load stock_scores with data_unavailable markers for symbols without EDGAR
```

**Chain 3: Price Feed Failure (CRITICAL BLOCKER)**
```
If price_daily fails (yfinance banned):
  → technical_data_daily blocked (needs prices)
  → market_health_daily blocked (needs VIX)
  → stability_metrics blocked (needs volatility)
  → stock_scores blocked (missing 15% technical + 10% stability)
  
Mitigation: PRICE_DATA_SOURCE=alpaca fallback; manual trigger for recovery
```

---

## 7. Feasibility Analysis: EDGAR Replacement Scenarios

### 7.1 Scenario A: Drop yfinance, Use EDGAR + Computed Metrics Only

**Cost:** Eliminates $0 direct (both free APIs)  
**Feasibility:** LOW (50% score loss)  
**Tradeoffs:**

| Metric | Before (yfinance) | After (EDGAR computed) | Score Impact |
|--------|---|---|---|
| **PE Ratio** | Real-time (daily) | Quarterly EPS (30-60d stale) | -10% (valuation timing off) |
| **Dividend Yield** | Real-time | Annual dividend (stale) | -5% (current yield wrong) |
| **Beta** | 252-day correlation | Must compute from price_daily (same as now) | No change |
| **Analyst Ratings** | yfinance consensus | Dropped entirely | -5% (sentiment lost) |
| **Short Interest** | Real-time | Delayed 2 weeks (separate source) | -10% (positioning stale) |
| **Market Health (VIX)** | Real-time | N/A (not in EDGAR) | -15% CRITICAL (circuit breaker breaks) |
| **Earnings Date** | Real-time | Not in EDGAR; requires 8-K tracking | -5% (risk mgmt degraded) |
| **Insider/Inst Holdings** | Real-time (snapshot) | Annual/quarterly (10-K/10-Q) | -10% (positioning stale) |

**Verdict:** VIX unavailable = deal-breaker. Cannot drop yfinance without alternative market data feed. Score quality drops 15% minimum.

---

### 7.2 Scenario B: Hybrid (Keep yfinance for prices/sentiment, augment EDGAR for fundamentals)

**Cost:** $0 (both free)  
**Feasibility:** HIGH (maintains current quality)  
**Implementation:** Current system architecture ✓

**Keeps:**
- yfinance for prices, VIX, analyst ratings, real-time valuations
- SEC EDGAR for audited financials, ROE, debt ratios, growth trends

**Possible enhancements:**
- Add 13F filing tracking for institutional ownership (5 days after quarter-end)
- Add Form 4 tracking for insider transactions (3 business days)
- Add 8-K tracking for earnings dates (real-time)

---

### 7.3 Scenario C: Replace yfinance Valuations with Bloomberg Terminal / FactSet

**Cost:** $20K-50K/year per terminal  
**Feasibility:** MEDIUM (data quality better, cost prohibitive)  
**Tradeoff:** Marginal improvement (real-time vs daily) doesn't justify cost for algo scale

---

## 8. Risk & Tradeoff Analysis

### 8.1 Current Hybrid Approach (yfinance + EDGAR) - BASELINE

| Risk | Severity | Mitigation | Residual |
|------|----------|-----------|----------|
| yfinance IP ban (shared AWS NAT) | High | Circuit breaker + Alpaca price fallback | Medium (10-20 min delays on snapshots) |
| EDGAR 404 (no filing for symbol) | Medium | Negative cache + data_unavailable marker | Low (handled gracefully) |
| Stale EDGAR data (30-60d delay) | Low | Acceptable for fundamentals; scores refresh quarterly | Low (known lag) |
| NaN Decimal values in EDGAR | Low | Cleaning in SecLoaderBase._clean_decimal() | Low (handled) |
| Missing analyst data (30% of symbols) | Low | data_unavailable marker; score degrades gracefully | Low (optional enrichment) |

### 8.2 EDGAR-Only Approach - RISKS

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| **Market data unavailable** | VIX, put/call, 52w high/low missing | 100% | Cannot implement without alternative feed |
| **Valuations stale** | PE, PB ratios 30-60d old | 100% | Trading signals miss earnings surprises |
| **Analyst sentiment lost** | Scores lose momentum component | 100% | Recommendation key unavailable in EDGAR |
| **Short interest unavailable** | Positioning metrics missing | 100% | Must supplement with FINRA short sale file |
| **Earnings dates missing** | Risk management degraded | 100% | Must track 8-K filings separately |
| **Circuit breaker breaks** | Trading halts malfunction | 100% | CRITICAL - cannot trade safely |

**Verdict:** EDGAR-only is not viable without additional data sources. Hybrid is optimal.

---

## 9. Implementation Roadmap (If Expanding EDGAR Usage)

### Phase 1: Enhance EDGAR Coverage (0-2 weeks)
- [ ] Add Form 4 (insider transaction) tracking for real-time insider ownership changes
- [ ] Add 13F filing tracking for institutional ownership (quarterly, 45 days late but better than quarterly snapshot)
- [ ] Add 8-K tracking for earnings date announcements (replaces yfinance earnings_date with more reliable source)

### Phase 2: Compute Additional Metrics from EDGAR (2-4 weeks)
- [ ] Compute TTM (trailing twelve months) for growth metrics (manual aggregation of last 4 quarters)
- [ ] Add forward estimate comparison: historical growth vs analyst estimates (requires separate feed: FactSet, Bloomberg, or Seeking Alpha estimates)
- [ ] Add dividend history computation from SEC filings (annual reports mention dividend policy)

### Phase 3: Reduce yfinance Dependency (4-8 weeks)
- [ ] Replace yfinance valuations (PE, PB, PS) with EDGAR-computed where possible
- [ ] Replace analyst ratings with alternative: MarketSmith, Yahoo Finance comments, or Seeking Alpha
- [ ] Verify score quality metrics don't degrade

### Phase 4: Fallback Architecture (8+ weeks)
- [ ] Implement polygon.io or Intrinio as yfinance fallback for prices and snapshot data
- [ ] Implement circuit breaker for data source switching
- [ ] Test failover scenarios

---

## 10. Summary Table: Data Source Comparison

| Dimension | yfinance | SEC EDGAR | Winner |
|-----------|----------|-----------|--------|
| **Coverage** | 95%+ US stocks + ETFs + indices | 85% US stocks (no ETFs, no indices) | yfinance |
| **Update Frequency** | Real-time to daily | Quarterly/annual (30-60d lag) | yfinance |
| **Data Quality** | Good (crowd-sourced corrections) | Excellent (audited, official) | EDGAR |
| **Cost** | Free | Free | Tie |
| **API Rate Limits** | 200 req/min per IP (shared AWS issue) | 10 req/sec (firm, but manageable) | EDGAR |
| **Reliability** | Poor (shared IP bans, invalid crumbs) | Excellent (stable SEC infra) | EDGAR |
| **Analyst Data** | Yes (ratings, counts) | No | yfinance |
| **Market Data (VIX, indices)** | Yes | No | yfinance |
| **Fundamentals (ROE, debt)** | No (snapshot only) | Yes (detailed statements) | EDGAR |
| **Real-Time Valuations** | Yes (current PE, yield) | No (30-60d stale) | yfinance |
| **Insider/Institutional Data** | Snapshot only | Annual/Q updates | Tie (different sources) |

### Recommendation: **STAY HYBRID**

The optimal architecture is **yfinance + SEC EDGAR**, with fallback strategies:

1. **Use yfinance for:**
   - OHLCV prices (can fallback to Alpaca)
   - Real-time metrics (PE, div yield, market cap)
   - Market sentiment (VIX, analyst ratings)
   - Quote snapshots (investor dashboard)

2. **Use SEC EDGAR for:**
   - Audited financial statements (highest quality)
   - Quality metrics (ROE, margins, debt ratios)
   - Growth metrics (historical revenue/EPS growth)
   - Risk metrics (leverage, coverage)

3. **Implement fallbacks:**
   - Alpaca for price data if yfinance banned
   - Polygon.io or Intrinio for snapshot metrics if yfinance unavailable
   - Form 4/13F tracking for insider/institutional ownership

4. **Monitor:**
   - yfinance IP ban status via circuit breaker
   - EDGAR API rate limit and error rates
   - Data staleness for each metric table
   - Score quality degradation due to missing data

---

## Appendix: File Reference

**Key Files Analyzed:**

1. `loaders/load_yfinance_snapshot.py` - Consolidated yfinance snapshot loader (5,300 symbols, 27 fields, single fetch)
2. `loaders/load_yfinance_derived_metrics.py` - Reads yfinance_snapshot, outputs 6 metric tables
3. `loaders/load_prices.py` - OHLCV price fetcher from yfinance
4. `loaders/load_economic_data.py` - FRED + DXY economic indicators
5. `loaders/load_financial_statements.py` - SEC EDGAR financial statements loader
6. `loaders/load_quality_growth_metrics.py` - Computed metrics from EDGAR financials
7. `loaders/load_technical_indicators.py` - Technical indicators from price_daily
8. `loaders/load_market_health_daily.py` - Market regime from VIX, yield curve, breadth
9. `loaders/market_health_fetchers.py` - VIX, put/call, yield curve fetchers
10. `utils/external/yfinance.py` - yfinance wrapper with circuit breaker
11. `utils/external/sec_edgar_client.py` - SEC EDGAR XBRL API client
12. `utils/external/sec_edgar.py` - SEC module wrapper

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-16  
**Analysis Scope:** 5,300 active symbols, all data loaders, daily pipeline (22:00 UTC complete)
