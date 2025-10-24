# Comprehensive Data Pipeline & Scoring System Analysis

**Generated**: 2025-10-23  
**Scope**: `/home/stocks/algo` - Complete codebase analysis  
**Key Findings**: 70+ data loaders, 6 score category systems, significant hardcoded/mock data issues

---

## EXECUTIVE SUMMARY

### Data Pipeline Overview
```
Raw Data Sources → Load*.py Scripts → PostgreSQL Database → Lambda Routes → Frontend UI
```

**Status**: Mixed - Real data collection working, but scoring system incomplete with hardcoded fallbacks.

### Critical Issues Found
1. **Sentiment Data**: Random fake data generation (CRITICAL)
2. **Correlation Matrices**: Hardcoded values instead of calculated (CRITICAL)
3. **Confidence Scores**: Default 90% instead of calculated from data (MEDIUM)
4. **Positioning Quality**: Default 0.5 for all holders (HIGH)

---

## PART 1: DATA LOADERS INVENTORY

### A. Price Data Loaders (7 variants × 3 timeframes = 21 loaders)

#### Daily Price Data
- **loadpricedaily.py** - Daily OHLCV from yfinance
- **loadlatestpricedaily.py** - Latest daily snapshot
- **loadpricedaily_optimized.py** - Optimized version
- **Tables**: `price_daily`, `etf_price_daily`
- **Output Format**: 
  ```sql
  (symbol, date, open, high, low, close, volume, dividend, split, 
   sma_20, sma_50, sma_200, rsi_14, macd, bb_upper, bb_lower)
  ```
- **Data Source**: yfinance
- **Status**: ✅ WORKING

#### Weekly & Monthly Data
- **loadpriceweekly.py** / **loadpricemonthly.py** - Aggregated from daily
- **loadlatestpriceweekly.py** / **loadlatestpricemonthly.py**
- **Status**: ✅ WORKING

#### Buy/Sell Signal Data
- **loadbuysellly.py**, **loadbuysellweekly.py**, **loadbuysellmonthly.py** (3)
- **Latest versions**: loadlatestbuyselldaily/weekly/monthly.py (3)
- **Tables**: `buy_sell_daily`, `buy_sell_weekly`, `buy_sell_monthly`
- **Output**: Buy/sell signals with strength scores
- **Status**: ✅ WORKING

---

### B. Technical Analysis Loaders (9 variants)

#### Technical Indicators
- **loadtechnicalsdaily.py** / **loadtechnicalsdaily_optimized.py**
- **loadtechnicalpatterns.py** - Pattern recognition
- **loadpatternrecognition.py** - Advanced ML-based patterns
- **Tables**:
  - `technical_data_daily/weekly/monthly`
  - `detected_patterns`
  - `pattern_performance`
  - `pattern_ml_models`
- **Data**: RSI, MACD, Bollinger Bands, moving averages, pattern scores
- **Status**: ✅ WORKING

#### Buy/Sell Signals (Specialized)
- Combination of price action + technical indicators
- Stored in `buy_sell_*` tables
- Status: ✅ WORKING

---

### C. Fundamental Data Loaders (Financial Statements)

#### Annual Statements
- **loadannualincomestatement.py** - Revenue, operating income, net income
- **loadannualbalancesheet.py** - Assets, liabilities, equity
- **loadannualcashflow.py** - Operating, investing, financing cash flows
- **loadttmincomestatement.py** - Trailing twelve months
- **loadttmcashflow.py** - TTM cash flows
- **Status**: ✅ WORKING - Data from yfinance

#### Quarterly Statements
- **loadquarterlyincomestatement.py**
- **loadquarterlybalancesheet.py**
- **loadquarterlycashflow.py**
- **Status**: ✅ WORKING

#### Derived Metrics from Financials
- **loadfinancials.py** - Creates:
  - `profitability_metrics` (ROE, ROA, margins)
  - `balance_sheet_strength` (debt ratios, liquidity)
  - `valuation_multiples` (P/E, P/B, EV/EBITDA)
  - `growth_metrics` (revenue growth, earnings growth)
- **Status**: ✅ WORKING

---

### D. Earnings & Estimates Loaders (5 loaders)

- **loadearningsestimate.py** - Forward EPS estimates
- **loadearningshistory.py** - Historical earnings with surprises
- **loadearningsmetrics.py** - Earnings quality, consistency
- **loadrevenueestimate.py** - Revenue estimates
- **loadsanalystsentiment.py** - Analyst ratings and price targets
- **Tables**: `earnings_estimates`, `earnings_history`, `earnings_metrics`
- **Status**: ✅ WORKING (from yfinance)

---

### E. Sentiment & Social Data Loaders (5 loaders)

#### Analyst Sentiment
- **loadsanalystsentiment.py**
- **Tables**: `analyst_sentiment_analysis`, `analyst_upgrade_downgrade`
- **Data**: Ratings (buy/hold/sell), price targets, recommendations
- **Source**: yfinance
- **Status**: ✅ WORKING

#### Social Sentiment (CRITICAL ISSUES)
- **loadsentiment.py** - GENERATES FAKE RANDOM DATA ❌
  - Google Trends: Returns NULL (needs `pytrends`)
  - Reddit: Returns NULL (needs PRAW API setup)
  - News sentiment: Returns NULL/0.0
  - **Issue**: No fallback - just returns empty
  
- **loadsentiment_real_data.py** - Alternative implementation (newer)
  - Attempts to use real Google Trends
  - Still has fallbacks to None/0.0
  
- **loadsentiment_realtime.py** - Real-time updates
  - Creates `realtime_sentiment_analysis` table
  - Status: Limited functionality

- **Tables**: 
  - `sentiment_data` (old structure)
  - `analyst_sentiment_analysis`
  - `social_sentiment_analysis`
  - `realtime_sentiment_analysis`

- **Status**: ⚠️ PARTIALLY WORKING - No real social media data

---

### F. Risk & Positioning Loaders (3 loaders)

#### Risk Metrics
- **loadriskmetrics.py**
- **Tables**:
  - `portfolio_risk_metrics` (VaR, Sharpe, Sortino)
  - `risk_alerts`
  - `market_risk_indicators`
- **Status**: ✅ WORKING - Calculates from price data

#### Positioning Data
- **loadpositioning.py** - Institutional & insider positioning
- **Tables**: `positioning_data`
- **Data**: 
  - Institutional ownership (% and counts)
  - Insider buying/selling
  - Short interest
  - Options flow
- **Status**: ⚠️ PARTIAL - Has default holder quality = 0.5

---

### G. Sector & Industry Loaders (3 loaders)

- **loadsectors.py** - Sector rankings and performance
- **load_sector_performance.py** - Sector momentum analysis
- **loadsectors_fast_optimized.py** - Optimized version
- **Tables**: `sector_ranking`, `industry_ranking`
- **Data**: Performance, momentum, ranking trends
- **Status**: ✅ WORKING - Based on aggregate price data

---

### H. Economic Data Loaders (4 loaders)

- **loadecondata.py** - FRED API economic indicators
  - GDP, unemployment, inflation, yields, PMI, etc.
  - Table: `economic_data`, `economic_calendar`
  - Source: FRED (Federal Reserve Economic Data)
  - Status: ✅ WORKING
  
- **loadecondata_calendar.py** - Economic event calendar
- **loadecondata_local.py** - Local/cached version
- **loadcalendar.py** - Trading calendar (earnings, dividends, splits)

- **Status**: ✅ WORKING

---

### I. Company Profile & Market Data (6 loaders)

- **loadcompanyprofile.py** - Company info, sector, industry
- **loadcompanyprofile-simple.py** / **-fixed.py** - Alternative versions
- **loadmarket.py** - Market data, technical levels
- **loaddailycompanydata.py** - Company snapshot updates
- **loadstocksymbols_optimized.py** - Stock symbol list with metadata
- **Tables**: `company_profile`, `market_data`, `stock_symbols`, `stock_symbols_enhanced`
- **Status**: ✅ WORKING

---

### J. Momentum Loaders (2 loaders)

#### Price Momentum
- **loadmomentum.py** - Academic momentum calculation
- **fill_momentum_metrics.py** - Backfill missing momentum data
- **Tables**: `momentum_metrics`
- **Calculations**:
  - Jegadeesh-Titman 12-1 month momentum (academic standard)
  - Alternative horizons (6-1, 9-1, 3-1, 12-3)
  - Risk-adjusted momentum (Sharpe, Sortino)
  - Volume-weighted momentum
  - On-Balance Volume (OBV) momentum
  - Fundamental momentum (earnings revisions)
- **Source**: yfinance + calculated
- **Status**: ✅ WORKING

---

### K. Quality & Growth Metrics Loaders (3 loaders)

- **loadqualitymetrics.py** - Quality score components
  - Earnings quality
  - Profitability
  - Balance sheet strength
  - Management effectiveness
  - Table: `quality_metrics`
  
- **loadgrowthmetrics.py** - Growth components
  - Revenue growth
  - Earnings growth
  - Market expansion
  - Fundamental growth
  - Table: `growth_metrics`
  
- **loadvaluemetrics.py** - Value score components
  - P/E ratio analysis
  - DCF valuation
  - Relative value
  - Table: `value_metrics`

- **Status**: ✅ WORKING

---

### L. Key Metrics Loaders (3 loaders)

- **loadkeymetrics.py** - Comprehensive metrics from yfinance
- **loadkeymetrics_simple.py** - Simplified version
- **webapp/lambda/load_key_metrics_data.py** - Lambda version
- **Tables**: `key_metrics`
- **Data**: Market cap, debt, equity, margins, ratios
- **Status**: ✅ WORKING

---

### M. Market Sentiment Loaders (4 loaders)

- **loadnaaim.py** - NAAIM exposure index (advisor sentiment)
- **loadfeargreed.py** - CNN Fear & Greed index
- **loadcrypto.py** - Cryptocurrency market indicators
- **loadcommodities.py** - Commodity prices and trends
- **Tables**: `naaim`, `fear_greed`, `crypto_data`, `commodities`
- **Status**: ✅ WORKING - API sources available

---

### N. News & Analyst Loaders (3 loaders)

- **loadnews.py** - Stock-specific news articles
- **loadanalystupgradedowngrade.py** - Rating changes
- **webapp/lambda/utils/newsAnalyzer.js** - News sentiment analysis
- **Tables**: `stock_news`, `analyst_ratings`
- **Status**: ✅ WORKING

---

### O. Scoring & Aggregation Loaders (4 loaders)

#### **PRIMARY: loadscores.py** ⭐
The master scoring engine that creates **6 score categories**:

1. **Quality Scores** (`quality_scores` table)
   - Components:
     - `earnings_quality` (from fundamental analysis)
     - `balance_strength` (from balance sheet metrics)
     - `profitability` (margins, ROA, ROE)
     - `management` (execution, estimate accuracy)
     - `composite` (weighted average)
   - Output: 0-100 score + trend (improving/stable/declining)
   - Confidence: Currently hardcoded 90%

2. **Growth Scores** (`growth_scores` table)
   - Components:
     - `revenue_growth` (YoY revenue growth)
     - `earnings_growth` (YoY EPS growth)
     - `fundamental_growth` (fundamental expansion)
     - `market_expansion` (TAM growth)
     - `composite`
   - Output: 0-100 score + trend
   - Confidence: Hardcoded 90%

3. **Value Scores** (`value_scores` table)
   - Components:
     - `pe_score` (relative to market/sector)
     - `dcf_score` (DCF-based valuation)
     - `relative_value` (vs peers)
     - `composite`
   - Output: 0-100 score + trend
   - Confidence: Hardcoded 90%

4. **Momentum Scores** (`momentum_scores` table)
   - Components:
     - `price_momentum` (12-month returns)
     - `fundamental_momentum` (earnings revisions)
     - `technical` (technical indicator strength)
     - `volume_analysis` (volume trends)
     - `composite`
   - Output: 0-100 score + trend
   - Confidence: Hardcoded 90%

5. **Sentiment Scores** (`sentiment_scores` table)
   - Components:
     - `analyst_sentiment` (analyst ratings)
     - `social_sentiment` (Reddit, Google Trends - EMPTY)
     - `market_sentiment` (put/call ratios, options flow)
     - `news_sentiment` (news article sentiment - ZERO)
     - `composite`
   - Output: 0-100 score + trend
   - Confidence: Hardcoded 90%

6. **Positioning Scores** (`positioning_scores` table)
   - Components:
     - `institutional` (institutional ownership strength)
     - `insider` (insider buying/selling)
     - `short_interest` (short interest levels)
     - `options_flow` (options positioning)
     - `composite`
   - Output: 0-100 score + trend
   - Confidence: Hardcoded 90%

#### **MASTER SCORES** (`master_scores` table)
- Combines all 6 categories
- Fields:
  - `quality`, `growth`, `value`, `momentum`, `sentiment`, `positioning`
  - `composite` (weighted average of all 6)
  - `market_regime` (bull/neutral/bear)
  - `confidence_level` (hardcoded 90)
  - `recommendation` (BUY/HOLD/SELL based on composite)
- Period types: daily, weekly, monthly (multi-timeframe scoring)
- Status: ✅ Structure in place, but MISSING DATA SOURCES

---

#### Other Scoring Loaders
- **loadstockscores.py** - Alternative implementation
- **webapp/lambda/loadstockscores.py** - Lambda version
- **load_historical_rankings.py** - Rankings from historical scores

---

## PART 2: SCORE CALCULATION DATA DEPENDENCIES

### Quality Score Dependencies
```
Quality Score ← {
  earnings_quality ← [loadearningsmetrics.py, loadannualincomestatement.py]
  balance_strength ← [loadannualbalancesheet.py, loadfinancials.py → profitability_metrics]
  profitability ← [loadfinancials.py → profitability_metrics]
  management ← [loadsanalystsentiment.py, loadanalystupgradedowngrade.py]
  composite ← weighted average
}
```

**Status**: ✅ Data sources available

---

### Growth Score Dependencies
```
Growth Score ← {
  revenue_growth ← [loadrevenueestimate.py, loadannualincomestatement.py]
  earnings_growth ← [loadearningsmetrics.py, loadannualincomestatement.py]
  fundamental_growth ← [loadfinancials.py, loadearningshistory.py]
  market_expansion ← [loadkeymetrics.py, loadcompanyprofile.py]
  composite ← weighted average
}
```

**Status**: ✅ Data sources available

---

### Value Score Dependencies
```
Value Score ← {
  pe_score ← [loadfinancials.py → valuation_multiples, loadkeymetrics.py]
  dcf_score ← [loadfinancials.py → growth_metrics, loadannualcashflow.py]
  relative_value ← [Compared to sector/industry from loadsectors.py]
  composite ← weighted average
}
```

**Status**: ✅ Data sources available

---

### Momentum Score Dependencies
```
Momentum Score ← {
  price_momentum ← [loadmomentum.py → jt_momentum_12_1]
  fundamental_momentum ← [loadearningsmetrics.py, loadmomentum.py → expected_eps_growth]
  technical ← [loadtechnicalsdaily.py, loadbuysellly.py]
  volume_analysis ← [loadpricedaily.py (volume), loadmomentum.py → volume_momentum]
  composite ← weighted average
}
```

**Status**: ✅ Data sources available

---

### Sentiment Score Dependencies (PROBLEMATIC)
```
Sentiment Score ← {
  analyst_sentiment ← [loadsanalystsentiment.py ✅]
  social_sentiment ← [
    reddit ← [loadsentiment.py - BROKEN - needs PRAW API setup]
    google_trends ← [loadsentiment.py/loadsentiment_real_data.py - PARTIAL - needs pytrends]
    twitter ← [NOT IMPLEMENTED]
  ]
  market_sentiment ← [loadfeargre.py, loadnaaim.py, loadpositioning.py ✅]
  news_sentiment ← [loadnews.py, newsAnalyzer.js - BROKEN - always returns 0.0]
  composite ← weighted average
}
```

**Status**: ❌ CRITICAL GAPS
- Reddit sentiment: Returns NULL
- Google Trends: Returns NULL in loadsentiment.py (pytrends not installed/configured)
- News sentiment: Always 0.0
- Result: Sentiment scores are mostly empty/NULL

---

### Positioning Score Dependencies
```
Positioning Score ← {
  institutional ← [loadpositioning.py - fund ownership analysis]
  insider ← [loadpositioning.py, webapp/insider routes]
  short_interest ← [loadpositioning.py - short ratio]
  options_flow ← [loadriskmetrics.py, put/call ratio data]
  composite ← weighted average
}
```

**Status**: ⚠️ PARTIAL
- Institutional data available but quality defaults to 0.5
- Insider trading data available
- Short interest available
- Options flow limited

---

## PART 3: DATABASE SCHEMA OVERVIEW

### Score Tables (7 main tables)
```sql
-- Core score tables
quality_scores (symbol, date, period_type, earnings_quality, balance_strength, profitability, management, composite, trend, confidence)
growth_scores (symbol, date, period_type, revenue_growth, earnings_growth, fundamental_growth, market_expansion, composite, trend, confidence)
value_scores (symbol, date, period_type, pe_score, dcf_score, relative_value, composite, trend, confidence)
momentum_scores (symbol, date, period_type, price_momentum, fundamental_momentum, technical, volume_analysis, composite, trend, confidence)
sentiment_scores (symbol, date, period_type, analyst_sentiment, social_sentiment, market_sentiment, news_sentiment, composite, trend, confidence)
positioning_scores (symbol, date, period_type, institutional, insider, short_interest, options_flow, composite, trend, confidence)

-- Aggregate table
master_scores (symbol, date, period_type, quality, growth, value, momentum, sentiment, positioning, composite, market_regime, confidence_level, recommendation)
```

### Supporting Tables (40+ tables)
```
Price Data:          price_daily, price_weekly, price_monthly
Technical:          technical_data_daily/weekly/monthly, detected_patterns
Fundamentals:       annual/quarterly income statements, balance sheets, cash flows
Key Metrics:        key_metrics, quality_metrics, growth_metrics, value_metrics, momentum_metrics
Sentiment:          analyst_sentiment_analysis, social_sentiment_analysis, sentiment_data
Positioning:        positioning_data, insider_trading
Earnings:           earnings_estimates, earnings_history, earnings_metrics
Sector/Industry:    sector_ranking, industry_ranking
Economic:           economic_data, economic_calendar
Market:             market_data, buy_sell_daily/weekly/monthly
Risk:               portfolio_risk_metrics, market_risk_indicators
```

---

## PART 4: DATA SOURCES & AVAILABILITY

### Real Working Data Sources

| Data Type | Source | API | Status | Notes |
|-----------|--------|-----|--------|-------|
| Stock Prices | yfinance | No (free) | ✅ | All price data working |
| Technical Indicators | Calculated | N/A | ✅ | From price data |
| Analyst Ratings | yfinance | No (free) | ✅ | From yfinance info |
| Earnings Data | yfinance | No (free) | ✅ | Annual & quarterly |
| Economic Data | FRED | Yes (have key) | ✅ | GDP, unemployment, rates, PMI |
| Fear & Greed | CNN | Free scrape | ✅ | Market sentiment index |
| NAAIM | External API | Yes | ✅ | Advisor positioning |
| Commodities | yfinance/IEX | Yes | ✅ | Oil, gold, natural gas |
| Crypto | yfinance/public API | No (free) | ✅ | Bitcoin, Ethereum data |

### Broken/Missing Data Sources

| Data Type | Source | Status | Issue |
|-----------|--------|--------|-------|
| Reddit Sentiment | Reddit PRAW API | ❌ | PRAW not installed, no API credentials |
| Google Trends | pytrends | ❌ | pytrends not installed, returns NULL |
| News Sentiment | NewsAPI/finBERT | ❌ | Returns hardcoded 0.0 |
| Twitter Sentiment | Twitter API | ❌ | Not implemented |
| Holdings Quality | Various databases | ⚠️ | Defaults to 0.5 |

---

## PART 5: HARDCODED/MOCK DATA ISSUES

### CRITICAL - Must Fix Immediately

1. **Sentiment Data Generation** (loadsentiment.py)
   - Issue: Generates random fake data with `np.random.randint()` and `np.random.normal()`
   - Impact: Database filled with fake sentiment values
   - Lines: 240-331 in loadsentiment.py
   - Solution: Remove or implement real APIs

2. **Economic Correlation Matrix** (webapp/lambda/routes/economic.js)
   - Issue: Hardcoded 0.5 for all non-diagonal values
   - Impact: Users see fake correlation relationships
   - Lines: 808-820
   - Solution: Calculate real Pearson correlation from economic_data table

3. **Market Correlation Matrix** (webapp/lambda/routes/market.js)
   - Issue: Hardcoded correlation (0.6 tech, 0.7 ETF, 0.4 mixed, 0.1 other)
   - Impact: Portfolio risk analysis shows fake diversification
   - Lines: 5000-5043
   - Solution: Calculate real correlation from price_daily returns

### HIGH - Should Fix

4. **News Sentiment Fallback** (newsAnalyzer.js, sentimentEngine.js)
   - Issue: Returns hardcoded 0.5 instead of NULL when no data
   - Impact: Missing data masked as neutral
   - Solution: Return NULL/undefined

5. **Positioning Quality Default** (loadpositioning.py)
   - Issue: All holders assigned quality = 0.5
   - Impact: Can't distinguish between good/bad institutional investors
   - Solution: Calculate real quality scores

### MEDIUM - Lower Priority

6. **Score Confidence Values** (loadscores.py)
   - Issue: All scores have hardcoded 90% confidence
   - Impact: Confidence doesn't reflect actual data completeness
   - Solution: Calculate based on non-null fields ratio

---

## PART 6: DATA PIPELINE FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA COLLECTION LAYER                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  yfinance ──→ [Price, Financials, Earnings, Analyst ratings]  │
│  FRED API ──→ [Economic indicators: GDP, unemployment, rates]  │
│  NAAIM API ──→ [Advisor positioning sentiment]                 │
│  Fear & Greed ──→ [Market sentiment index]                      │
│  Cryptocurrencies ──→ [BTC, ETH prices]                         │
│  Commodities ──→ [Oil, gold, natural gas]                       │
│                                                                   │
│  BROKEN: Reddit (needs PRAW setup)                             │
│  BROKEN: Google Trends (pytrends not installed)                │
│  BROKEN: News Sentiment (always returns 0.0)                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LOAD*.PY SCRIPTS LAYER                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Price Loaders (3)    → price_daily/weekly/monthly             │
│  Technical Loaders    → technical_data_* + patterns             │
│  Financial Loaders    → income/balance/cash flow statements     │
│  Fundamental Loaders  → quality/growth/value metrics            │
│  Momentum Loaders     → momentum_metrics                         │
│  Sentiment Loaders    → analyst/social/market sentiment [BROKEN]│
│  Economic Loaders     → economic_data                           │
│  Position Loaders     → positioning_data                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL DATABASE                           │
├─────────────────────────────────────────────────────────────────┤
│  price_daily → technical_data → buy_sell signals               │
│  income_stmt → balance_sheet → cash_flow → key metrics         │
│  earnings_history → earnings_metrics → growth_metrics           │
│  momentum_metrics                                                │
│  analyst_sentiment_analysis (✅)                                │
│  social_sentiment_analysis (❌ NULL/empty)                      │
│  positioning_data (⚠️ quality defaults to 0.5)                  │
│  economic_data                                                   │
│  sector_ranking, industry_ranking                               │
│  fear_greed, naaim, crypto, commodities                        │
│                                                                   │
│  [SCORING ENGINE - loadscores.py]                              │
│  quality_scores ← [earnings_quality, balance_strength, ...]    │
│  growth_scores ← [revenue_growth, earnings_growth, ...]        │
│  value_scores ← [pe_score, dcf_score, ...]                    │
│  momentum_scores ← [price_momentum, technical, volume, ...]    │
│  sentiment_scores ← [analyst✅, social❌, market, news❌]       │
│  positioning_scores ← [institutional, insider, short, options]│
│  master_scores ← [composite of all 6]                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                 LAMBDA ROUTES API LAYER                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  /api/stock/{symbol} → stock details + scores                  │
│  /api/scores → master scores                                    │
│  /api/technical → technical analysis                            │
│  /api/fundamentals → P/E, margins, growth metrics              │
│  /api/sentiment → analyst + market sentiment                    │
│  /api/economic → economic indicators + [FAKE] correlations    │
│  /api/market → market data + [FAKE] correlations              │
│  /api/portfolio → portfolio analysis                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    REACT FRONTEND UI                             │
├─────────────────────────────────────────────────────────────────┤
│  Market Overview Dashboard                                       │
│  Stock Scores Dashboard (Quality/Growth/Value/Momentum/Sentiment)│
│  Sector Analysis & Rankings                                     │
│  Technical Analysis Charts                                      │
│  Economic Indicators                                            │
│  Portfolio Analyzer                                             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## PART 7: MISSING DATA MAPPING

### What's Missing or Broken

| Score Component | Required Data | Current Status | Issue |
|---|---|---|---|
| **Quality** | | | |
| earnings_quality | EPS growth, estimate accuracy | ✅ | Available from yfinance |
| balance_strength | Debt ratios, current ratio, quick ratio | ✅ | Available from financials |
| profitability | ROE, ROA, margins | ✅ | Available from yfinance |
| management | Estimate revisions, execution | ⚠️ | Partial from yfinance |
| | | | |
| **Growth** | | | |
| revenue_growth | Revenue history, YoY growth | ✅ | Available |
| earnings_growth | EPS history, growth rate | ✅ | Available |
| fundamental_growth | Revenue/earnings momentum | ✅ | Available |
| market_expansion | TAM, addressable market | ❌ | Not available in APIs |
| | | | |
| **Value** | | | |
| pe_score | P/E, industry P/E | ✅ | Available |
| dcf_score | DCF calculation | ✅ | Can calculate from data |
| relative_value | Vs peers/industry | ⚠️ | Requires peer comparison |
| | | | |
| **Momentum** | | | |
| price_momentum | 12-month returns | ✅ | Calculated in loadmomentum.py |
| fundamental_momentum | EPS estimate revisions | ✅ | Available |
| technical | RSI, MACD, trend | ✅ | Available |
| volume_analysis | Volume trends, OBV | ✅ | Available |
| | | | |
| **Sentiment** | | | |
| analyst_sentiment | Ratings, price targets | ✅ | yfinance |
| social_sentiment | Reddit mentions, sentiment | ❌ | PRAW not setup - RETURNS NULL |
| | | | | Google Trends mentions | ❌ | pytrends not installed - RETURNS NULL |
| market_sentiment | Put/call ratio, NAAIM | ✅ | Available |
| news_sentiment | Article sentiment analysis | ❌ | Always returns 0.0 |
| | | | |
| **Positioning** | | | |
| institutional | Fund ownership | ✅ | Available but quality=0.5 default |
| insider | Insider transactions | ✅ | Available |
| short_interest | Short ratio, % floatshort | ✅ | Available |
| options_flow | Put/call, open interest | ⚠️ | Limited data |

---

## PART 8: RECOMMENDATIONS BY PRIORITY

### PHASE 1: CRITICAL FIXES (Week 1)
1. **Remove fake sentiment generation** in `loadsentiment.py`
   - Delete random data generation
   - Keep NULL returns or implement real API
   - Don't ship random numbers to production

2. **Fix correlation endpoints**
   - Implement Pearson correlation calculation
   - Query `economic_data` table for correlations
   - Query `price_daily` table and calculate returns correlation
   - Remove hardcoded 0.5 and 0.6 values

3. **Fix sentiment fallbacks**
   - Return NULL instead of hardcoded 0.5
   - Let frontend handle missing data display

### PHASE 2: HIGH PRIORITY (Week 2)
1. **Setup Google Trends** (easy - no API key)
   - Install `pytrends` package
   - Test with sample stocks
   - Fallback to NULL if fails

2. **Setup Reddit API** (medium - requires setup)
   - Register app on reddit.com
   - Get credentials
   - Store in Secrets Manager
   - Implement PRAW integration

3. **Implement real news sentiment**
   - Use NewsAPI (free tier available)
   - Or use existing news articles from `stock_news` table
   - Analyze with TextBlob/VADER

4. **Calculate real confidence scores**
   - Replace hardcoded 90% with actual calculation
   - Base on data completeness ratio

### PHASE 3: MEDIUM PRIORITY (Week 3-4)
1. **Enhance positioning quality**
   - Implement holder quality scoring
   - Research fund track records
   - Weight by AUM and performance

2. **Add missing data components**
   - Market expansion (TAM) data
   - More detailed peer comparison
   - More earnings estimate sources

3. **Performance optimization**
   - Index key query columns
   - Cache common calculations
   - Batch load operations

---

## PART 9: KEY FILES TO MODIFY

### Critical Files
1. `/home/stocks/algo/loadsentiment.py` - Remove fake data generation
2. `/home/stocks/algo/loadsentiment_real_data.py` - Complete implementation
3. `/home/stocks/algo/webapp/lambda/routes/economic.js` - Fix correlation calc
4. `/home/stocks/algo/webapp/lambda/routes/market.js` - Fix correlation calc
5. `/home/stocks/algo/webapp/lambda/utils/newsAnalyzer.js` - Fix fallback
6. `/home/stocks/algo/webapp/lambda/utils/sentimentEngine.js` - Fix fallback

### Important Supporting Files
7. `/home/stocks/algo/loadscores.py` - Scoring engine (improve confidence calculation)
8. `/home/stocks/algo/loadpositioning.py` - Positioning data (implement quality scoring)
9. `/home/stocks/algo/loadmomentum.py` - Momentum calculation (working, reference)
10. `/home/stocks/algo/loadsanalystsentiment.py` - Analyst sentiment (working, reference)

---

## PART 10: DATA COMPLETENESS MATRIX

### By Database Table
```
✅ = Has real data
❌ = Missing/broken
⚠️ = Partial/limited

price_daily                          ✅ Real prices
technical_data_daily                 ✅ Real indicators
buy_sell_daily                        ✅ Real signals
annual_income_statement               ✅ Real financials
quarterly_income_statement            ✅ Real financials
key_metrics                           ✅ Real metrics
analyst_sentiment_analysis            ✅ Real analyst data
social_sentiment_analysis             ❌ NULL/empty
sentiment_data                        ❌ Random fake data
economic_data                         ✅ Real FRED data
momentum_metrics                      ✅ Real calculations
positioning_data                      ⚠️ Real data, bad quality scoring
quality_scores                        ✅ Can calculate from components
growth_scores                         ✅ Can calculate from components
value_scores                          ✅ Can calculate from components
momentum_scores                       ✅ Can calculate from components
sentiment_scores                      ❌ Missing social + news components
positioning_scores                    ⚠️ Missing quality scoring
master_scores                         ⚠️ Incomplete (missing sentiment)
```

---

## CONCLUSION

The data pipeline has **excellent price/technical/fundamental data collection** (40+ working loaders), but **critical gaps in sentiment data** and **systematic use of hardcoded values** in correlation calculations.

**Immediate Action Items**:
1. Stop generating random sentiment data
2. Fix correlation calculations (economic + market)
3. Setup real sentiment data sources (Google Trends, Reddit optional)
4. Replace hardcoded fallback values with NULL

**Timeline**: 1-2 weeks to fix critical issues
**Impact**: Users currently see fake sentiment scores and fake correlation relationships

