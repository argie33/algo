# Database Schema Visual Guide

## Table Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REFERENCE TABLES                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐   │
│  │ stock_symbols    │    │ etf_symbols      │    │ company_profile │   │
│  ├──────────────────┤    ├──────────────────┤    ├─────────────────┤   │
│  │ symbol (PK)      │    │ symbol (PK)      │    │ ticker (PK)     │   │
│  │ exchange         │    │ exchange         │    │ short_name      │   │
│  │ security_name    │    │ security_name    │    │ sector          │   │
│  │ etf              │    │                  │    │ industry        │   │
│  └──────────────────┘    └──────────────────┘    └─────────────────┘   │
│           ▲                       ▲                      ▲                │
│           │                       │                      │                │
└───────────┼───────────────────────┼──────────────────────┼────────────────┘
            │                       │                      │
┌───────────┴───────────────────────┴──────────────────────┴────────────────┐
│                    PRIMARY DATA TABLES (Daily Updates)                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────┐      ┌──────────────────┐                       │
│  │ price_daily         │      │ etf_price_daily  │                       │
│  ├─────────────────────┤      ├──────────────────┤                       │
│  │ symbol (FK)         │      │ symbol (FK)      │                       │
│  │ date                │      │ date             │                       │
│  │ open, high, low     │      │ open, high, low  │                       │
│  │ close, adj_close    │      │ close, adj_close │                       │
│  │ volume              │      │ volume           │                       │
│  │ dividends           │      └──────────────────┘                       │
│  │ stock_splits        │                                                 │
│  └─────────────────────┘       Indexed: (symbol, date)                  │
│                                                                           │
│  ┌────────────────────────┐    ┌──────────────────────┐                  │
│  │ technical_data_daily   │    │ market_data          │                  │
│  ├────────────────────────┤    ├──────────────────────┤                  │
│  │ symbol                 │    │ ticker (PK)          │                  │
│  │ date                   │    │ market_cap           │                  │
│  │ rsi, macd              │    │ current_price        │                  │
│  │ sma_20, sma_50, sma_200│    │ previous_close       │                  │
│  │ ema_21, adx, atr       │    │ volume               │                  │
│  │ pivot_high, pivot_low  │    │ 52_week_high/low     │                  │
│  └────────────────────────┘    └──────────────────────┘                  │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│              CORE METRIC TABLES (symbol, date composite PK)              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐ │
│  │ quality_metrics    │    │ growth_metrics     │    │ momentum_metrics│ │
│  ├────────────────────┤    ├────────────────────┤    ├─────────────────┤ │
│  │ ROE, ROA           │    │ Revenue CAGR       │    │ 12m, 6m, 3m     │ │
│  │ Margins (3 types)  │    │ EPS CAGR           │    │ Price vs SMA    │ │
│  │ FCF ratios         │    │ Income growth      │    │ Price vs 52w    │ │
│  │ Debt/equity        │    │ FCF growth         │    │ Risk-adjusted   │ │
│  │ Current/quick ratio│    │ Margin trends      │    │ Volatility      │ │
│  │ Earnings quality   │    └────────────────────┘    └─────────────────┘ │
│  └────────────────────┘                                                   │
│                                                                           │
│  ┌────────────────────┐    ┌────────────────────┐    ┌─────────────────┐ │
│  │ risk_metrics       │    │ positioning_metrics│    │ earnings_history│ │
│  ├────────────────────┤    ├────────────────────┤    ├─────────────────┤ │
│  │ Volatility 12m     │    │ Institutional own  │    │ symbol          │ │
│  │ Volatility risk    │    │ Insider ownership  │    │ quarter (PK)    │ │
│  │ Max drawdown       │    │ Short % float      │    │ eps_actual      │ │
│  │ Beta               │    │ Short ratio        │    │ eps_estimate    │ │
│  │                    │    │ Acc/dist rating    │    │ eps_surprise    │ │
│  └────────────────────┘    └────────────────────┘    └─────────────────┘ │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
              ▲                        ▲                        ▲
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
              All feed into:           │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
              ▼                                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         COMPOSITE SCORING TABLE                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  stock_scores (Daily calculated from all metric tables)                  │
│  ┌──────────────────────────────────────────────────────────┐            │
│  │ symbol (PK) → Score Components (0-100):                  │            │
│  │  ├─ composite_score (weighted average)                   │            │
│  │  ├─ momentum_score (RSI-based)                           │            │
│  │  ├─ value_score (PE/PB-based)                            │            │
│  │  ├─ quality_score (margins/volatility)                   │            │
│  │  ├─ growth_score (earnings growth)                       │            │
│  │  ├─ positioning_score (ownership data)                   │            │
│  │  ├─ sentiment_score (analyst/social)                     │            │
│  │  └─ stability_score (risk metrics)                       │            │
│  │                                                           │            │
│  │ Technical Indicators:                                     │            │
│  │  ├─ rsi, macd                                            │            │
│  │  ├─ sma_20, sma_50                                       │            │
│  │  └─ volatility_30d                                       │            │
│  │                                                           │            │
│  │ Price Data:                                               │            │
│  │  ├─ current_price                                        │            │
│  │  ├─ price_change_1d, 5d, 30d                             │            │
│  │  └─ volume_avg_30d                                       │            │
│  │                                                           │            │
│  │ Financial Data:                                           │            │
│  │  ├─ pe_ratio                                             │            │
│  │  ├─ market_cap                                           │            │
│  │  └─ volatility_30d                                       │            │
│  │                                                           │            │
│  │ Detailed Inputs (JSONB):                                 │            │
│  │  ├─ value_inputs (all valuation metrics)                 │            │
│  │  └─ stability_inputs (all risk metrics)                  │            │
│  └──────────────────────────────────────────────────────────┘            │
│                                                                           │
│  Used By: /api/scores endpoint (primary data source)                    │
│  Updated Daily: Via loadstockscores.py from metric tables              │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    MARKET SENTIMENT TABLES (Date PK)                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────────┐    ┌──────────────┐    ┌─────────────────────────┐│
│  │ fear_greed_index │    │ aaii_sentiment │   │ naaim                   ││
│  ├──────────────────┤    ├──────────────┤    ├─────────────────────────┤│
│  │ date (PK)        │    │ date (PK)    │    │ date (PK)               ││
│  │ index_value      │    │ bullish_pct  │    │ naaim_exposure (0-100)  ││
│  │ rating           │    │ neutral_pct  │    │ [0=short, 50=neutral,   ││
│  │                  │    │ bearish_pct  │    │  100=long]              ││
│  │ Daily via CNN    │    │ Weekly AAII  │    │ Daily from NAAIM API    ││
│  └──────────────────┘    └──────────────┘    └─────────────────────────┘│
│                                                                           │
│  Analyst & Social Sentiment:                                             │
│  ┌─────────────────────────────┐    ┌──────────────────────────────────┐│
│  │ analyst_sentiment_analysis  │    │ social_sentiment_analysis        ││
│  ├─────────────────────────────┤    ├──────────────────────────────────┤│
│  │ symbol, date                │    │ symbol, date                     ││
│  │ buy_count, hold_count       │    │ bullish_posts, bearish_posts    ││
│  │ sell_count                  │    │ sentiment_score                  ││
│  │ target_price                │    │ realtime_sentiment_analysis (more││
│  │ sentiment_score             │    │ frequent updates)               ││
│  └─────────────────────────────┘    └──────────────────────────────────┘│
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                    SUPPORTING DATA TABLES                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Other tables:                                                           │
│  ├─ key_metrics         ← Financial snapshot (PE, PB, EV/EBITDA, etc)   │
│  ├─ sector_benchmarks   ← Sector avg PE, PB, EV/EBITDA, D/E ratio      │
│  ├─ price_monthly       ← Monthly aggregated prices                     │
│  ├─ etf_price_monthly   ← Monthly ETF prices                            │
│  ├─ analyst_upgrade_downgrade ← Rating change events                   │
│  ├─ stock_news          ← News headlines and articles                   │
│  ├─ buy_sell_daily      ← Daily signal strength                         │
│  ├─ buy_sell_monthly    ← Monthly aggregated signals                    │
│  ├─ insider_transactions ← Insider buys/sells                           │
│  ├─ institutional_positioning ← Institutional holdings                  │
│  └─ last_updated        ← Track when each loader last ran              │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Architecture

```
Data Sources
    ↓
┌─────────────────────────────────────────┐
│        Python Data Loaders              │
├─────────────────────────────────────────┤
│ • loadpricedaily.py   (yfinance)        │
│ • loadfeargreed.py    (CNN web scrape)  │
│ • loadaaiidata.py     (AAII API)        │
│ • loadnaaim.py        (NAAIM API)       │
│ • loadqualitymetrics.py (Financial API) │
│ • loadgrowthmetrics.py (Financial API)  │
│ • loadstockscores.py  (Calculated)      │
│ • loadsentiment.py    (Sentiment API)   │
│ • loadtechnicalsdaily.py (Calculated)   │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│      PostgreSQL Database                │
├─────────────────────────────────────────┤
│ • Raw data tables (price_daily, etc)    │
│ • Metric tables (quality, growth, etc)  │
│ • Scoring table (stock_scores)          │
│ • Sentiment tables (fear_greed, etc)    │
│ • Reference tables (company_profile)    │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│      Node.js Lambda Routes              │
├─────────────────────────────────────────┤
│ • /api/scores            (stock_scores) │
│ • /api/market/data       (price_daily)  │
│ • /api/market/sentiment  (all sentiment)│
│ • /api/market/breadth    (calculated)   │
│ • /api/sectors           (company data) │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│      Frontend React UI                  │
├─────────────────────────────────────────┤
│ • Stock Screener        (scores, filter)│
│ • Market Overview       (sentiment)     │
│ • Sector Analysis       (performance)   │
│ • Dashboard             (metrics)       │
└─────────────────────────────────────────┘
```

---

## Key Column Relationships

### Symbol Field Names Across Tables
- `stock_scores` → `symbol`
- `price_daily` → `symbol`
- `technical_data_daily` → `symbol`
- `company_profile` → `ticker`
- `key_metrics` → `ticker`
- `market_data` → `ticker`
- **Note**: Quality/growth/momentum/risk/positioning metrics → `symbol`

**Join Pattern**: `symbol` field is not always consistent. Use:
```sql
-- For joining company_profile (uses ticker):
JOIN company_profile ON stock_scores.symbol = company_profile.ticker

-- For joining price data (uses symbol):
JOIN price_daily ON stock_scores.symbol = price_daily.symbol
```

---

## Score Calculation Hierarchy

```
Individual Metric Tables
├─ quality_metrics
│  └─ Produces: quality_score (0-100)
├─ growth_metrics
│  └─ Produces: growth_score (0-100)
├─ momentum_metrics
│  └─ Produces: momentum_score (0-100)
├─ positioning_metrics
│  └─ Produces: positioning_score (0-100)
├─ risk_metrics
│  └─ Produces: stability_score (0-100)
├─ technical_data_daily
│  ├─ Produces: rsi, macd, sma values
│  └─ Influences: momentum_score
└─ price_daily
   ├─ Produces: price_change %, volatility
   └─ Influences: multiple scores

        ↓
        
stock_scores Table
├─ Composite Score = Weighted average of:
│  ├─ momentum_score (25%)
│  ├─ value_score (20%)
│  ├─ quality_score (20%)
│  ├─ growth_score (20%)
│  ├─ positioning_score (10%)
│  └─ sentiment_score (5%)
│
├─ Also stores:
│  ├─ Individual scores (already normalized 0-100)
│  ├─ Technical indicators (RSI, MACD, SMA)
│  ├─ Price metrics (current, changes, volatility)
│  ├─ Financial metrics (PE, market_cap)
│  └─ JSONB inputs (detailed components)
│
└─ Updated daily via loadstockscores.py
```

---

## Index Strategy

### Performance-Critical Indexes
```
price_daily:
  PRIMARY KEY: (id)
  UNIQUE: (symbol, date)
  INDEX: idx_price_daily_symbol_date

stock_scores:
  PRIMARY KEY: (symbol)
  INDEX: idx_stock_scores_composite (composite_score DESC)
  INDEX: idx_stock_scores_updated (last_updated)
  INDEX: idx_stock_scores_date (score_date)

quality_metrics, growth_metrics, momentum_metrics, risk_metrics, positioning_metrics:
  PRIMARY KEY: (symbol, date)
  INDEX: idx_*_symbol
  INDEX: idx_*_date (DESC)
```

### Query Pattern → Best Index
```
Pattern: WHERE symbol = X AND date >= Y
  Use: (symbol, date) index
  
Pattern: ORDER BY date DESC LIMIT N
  Use: idx_*_date (DESC)
  
Pattern: WHERE composite_score > X ORDER BY composite_score DESC
  Use: idx_stock_scores_composite
```

---

## Data Update Lifecycle

```
Daily (Business Days):
  ├─ 00:00  → loadpricedaily.py (downloads until market close)
  ├─ 16:30  → loadmarket.py (after market close)
  ├─ 17:00  → loadtechnicalsdaily.py (calculated from prices)
  ├─ 17:15  → loadfeargreed.py (web scrape)
  ├─ 17:30  → loadnaaim.py (API call)
  ├─ 18:00  → loadstockscores.py (calculated from all metrics)
  └─ 18:30  → Report sent to frontend

Weekly (Fridays):
  ├─ loadaaiidata.py (releases weekly)
  ├─ loadqualitymetrics.py
  ├─ loadgrowthmetrics.py
  └─ loadpositioningmetrics.py

Verification:
  └─ SELECT script_name, last_run FROM last_updated ORDER BY last_run DESC
```

---

## Query Performance Expectations

### Fast Queries (< 100ms)
- Single symbol from stock_scores
- Latest price by symbol
- Recent sentiment data

### Medium Queries (100ms - 1s)
- Top 50 stocks by score
- Symbol price history (30 days)
- Sector aggregations

### Slow Queries (> 1s)
- Full historical backtest (all prices)
- Multi-symbol JOINs across many metric tables
- Complex window functions over large datasets

### Optimization Rule
```
Query too slow? Add:
  1. WHERE date >= CURRENT_DATE - INTERVAL '90 days'
  2. WHERE symbol IN ('AAPL', 'MSFT', ...)
  3. LIMIT 100
  4. Use specific columns, not SELECT *
```

