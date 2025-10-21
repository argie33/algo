# Database Inventory - Stocks Algorithm Database

## Database Connection
- **Type**: PostgreSQL 
- **Support Methods**: 
  - Local env vars (dev/local testing): `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
  - AWS Secrets Manager (production): `DB_SECRET_ARN` environment variable
- **Default Config** (local): `localhost:5432`, user `postgres`, password `password`, database `stocks`

## Core Tables Structure

### 1. Foundation Tables (Symbol/Entity Reference)
```sql
-- Stock Symbols Registry
stock_symbols
  - symbol VARCHAR(50) PRIMARY KEY
  - exchange VARCHAR(100)
  - security_name TEXT
  - cqs_symbol VARCHAR(50)
  - market_category VARCHAR(50)
  - test_issue CHAR(1)
  - financial_status VARCHAR(50)
  - round_lot_size INT
  - etf CHAR(1)
  - secondary_symbol VARCHAR(50)

-- ETF Symbols (if separate)
etf_symbols (similar structure to stock_symbols)
```

---

## 2. Price & Market Data Tables

### price_daily
**Purpose**: Daily OHLCV data for stocks (from `loadpricedaily.py`)
```sql
Columns:
  id SERIAL PRIMARY KEY
  symbol VARCHAR(10) NOT NULL
  date DATE NOT NULL
  open DOUBLE PRECISION
  high DOUBLE PRECISION
  low DOUBLE PRECISION
  close DOUBLE PRECISION
  adj_close DOUBLE PRECISION
  volume BIGINT
  dividends DOUBLE PRECISION
  stock_splits DOUBLE PRECISION
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

Indexes:
  - (symbol, date) UNIQUE constraint
  - idx_price_daily_symbol_date

Date Range: Full historical data (loaded via yfinance)
Sample Data: Last 90 days typically available per stock
```

### etf_price_daily
**Purpose**: Daily OHLCV data for ETFs (from `loadpricedaily.py`)
```sql
Same structure as price_daily but for ETF symbols
```

### price_monthly
**Purpose**: Monthly aggregated price data
```sql
Similar structure to price_daily but with monthly intervals
```

### etf_price_monthly
**Purpose**: Monthly aggregated price data for ETFs

### market_data
**Purpose**: Market-level snapshot data (from `loadmarket.py`)
```sql
Columns:
  ticker VARCHAR(50) PRIMARY KEY
  market_cap BIGINT
  current_price DECIMAL(10,2) [optional]
  previous_close DECIMAL(10,2) [optional]
  volume BIGINT [optional]
  fifty_two_week_low DOUBLE PRECISION [optional]
  fifty_two_week_high DOUBLE PRECISION [optional]
  
Contains: Latest market capitalization for stocks
```

---

## 3. Company Information Tables

### company_profile
**Purpose**: Static company information (from `loadinfo.py` & `loaddailycompanydata.py`)
```sql
Columns:
  ticker VARCHAR(50) PRIMARY KEY
  short_name VARCHAR(255)
  long_name VARCHAR(255)
  display_name TEXT
  website_url VARCHAR(255)
  employee_count INT
  country VARCHAR(100)
  business_summary TEXT
  sector VARCHAR(100)
  industry VARCHAR(100)
  exchange VARCHAR(50)
  full_exchange_name VARCHAR(100)
  description TEXT [optional]
  
Indexes: PRIMARY on ticker
```

### key_metrics
**Purpose**: Financial metrics snapshot (from various loaders)
```sql
Columns:
  ticker VARCHAR(50) PRIMARY KEY
  trailing_pe DOUBLE PRECISION
  forward_pe DOUBLE PRECISION
  price_to_book DOUBLE PRECISION
  price_to_sales_ttm DOUBLE PRECISION
  ev_to_ebitda DOUBLE PRECISION
  dividend_yield DOUBLE PRECISION
  earnings_growth_pct DOUBLE PRECISION
  revenue_growth_pct DOUBLE PRECISION
  free_cashflow BIGINT
  enterprise_value BIGINT
  total_debt BIGINT
  total_cash BIGINT
  eps_trailing DOUBLE PRECISION
  total_revenue BIGINT
  profit_margin_pct DOUBLE PRECISION
  debt_to_equity DOUBLE PRECISION
```

---

## 4. Technical Analysis Tables

### technical_data_daily
**Purpose**: Daily technical indicators (from `loadtechnicalsdaily.py`)
```sql
Columns:
  symbol VARCHAR(50) PRIMARY KEY (or symbol + date)
  date DATE [if not primary key]
  rsi DECIMAL(5,2) [Relative Strength Index 0-100]
  macd DECIMAL(10,4) [MACD value]
  macd_signal DECIMAL(10,4)
  sma_20 DECIMAL(10,2) [20-day Simple Moving Average]
  sma_50 DECIMAL(10,2) [50-day Simple Moving Average]
  sma_200 DECIMAL(10,2) [200-day Simple Moving Average]
  ema_21 DECIMAL(10,2) [21-day Exponential Moving Average]
  adx DECIMAL(5,2) [Average Directional Index]
  atr DECIMAL(10,2) [Average True Range]
  pivot_high DECIMAL(10,2)
  pivot_low DECIMAL(10,2)
  
Indexes:
  - idx_technical_symbol or (symbol, date)
```

### technical_indicators
**Purpose**: Alternative technical indicators storage
```sql
Similar structure to technical_data_daily with additional indicators
```

---

## 5. Scoring & Analysis Tables

### stock_scores
**Purpose**: Comprehensive stock scoring system (from `loadstockscores.py`)
```sql
Columns - Composite Scores (0-100):
  symbol VARCHAR(50) PRIMARY KEY
  composite_score DECIMAL(5,2)
  momentum_score DECIMAL(5,2)
  value_score DECIMAL(5,2)
  quality_score DECIMAL(5,2)
  growth_score DECIMAL(5,2)
  positioning_score DECIMAL(5,2)
  sentiment_score DECIMAL(5,2)
  stability_score DECIMAL(5,2)
  
Columns - Technical Data:
  rsi DECIMAL(5,2)
  macd DECIMAL(10,4)
  sma_20 DECIMAL(10,2)
  sma_50 DECIMAL(10,2)
  
Columns - Price & Volume:
  volume_avg_30d BIGINT
  current_price DECIMAL(10,2)
  price_change_1d DECIMAL(5,2)
  price_change_5d DECIMAL(5,2)
  price_change_30d DECIMAL(5,2)
  volatility_30d DECIMAL(5,2)
  
Columns - Financial:
  market_cap BIGINT
  pe_ratio DECIMAL(8,2)
  
Columns - Momentum Components (5-part breakdown):
  momentum_short_term DECIMAL(5,2)
  momentum_medium_term DECIMAL(5,2)
  momentum_long_term DECIMAL(5,2)
  momentum_consistency DECIMAL(5,2)
  roc_10d DECIMAL(8,2)
  roc_20d DECIMAL(8,2)
  roc_60d DECIMAL(8,2)
  roc_120d DECIMAL(8,2)
  roc_252d DECIMAL(8,2)
  mom DECIMAL(10,2)
  mansfield_rs DECIMAL(8,2)
  
Columns - Positioning:
  acc_dist_rating DECIMAL(5,2)
  
Columns - JSON Storage:
  value_inputs JSONB [Contains all input metrics for value score]
  stability_inputs JSONB [Contains all input metrics for stability score]
  
Columns - Metadata:
  score_date DATE DEFAULT CURRENT_DATE
  last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  
Indexes:
  - PRIMARY on symbol
  - idx_stock_scores_composite (composite_score DESC)
  - idx_stock_scores_updated (last_updated)
  - idx_stock_scores_date (score_date)
  
Data Update Frequency: Daily (calculated from price_daily & other metric tables)
```

---

## 6. Fundamental Analysis Tables

### quality_metrics
**Purpose**: Company quality metrics (from `loadqualitymetrics.py`)
```sql
Columns - Profitability:
  return_on_equity_pct DOUBLE PRECISION
  return_on_assets_pct DOUBLE PRECISION
  gross_margin_pct DOUBLE PRECISION
  operating_margin_pct DOUBLE PRECISION
  profit_margin_pct DOUBLE PRECISION

Columns - Cash Quality:
  fcf_to_net_income DOUBLE PRECISION
  operating_cf_to_net_income DOUBLE PRECISION

Columns - Balance Sheet:
  debt_to_equity DOUBLE PRECISION
  current_ratio DOUBLE PRECISION
  quick_ratio DOUBLE PRECISION

Columns - Earnings Quality:
  earnings_surprise_avg DOUBLE PRECISION
  eps_growth_stability DOUBLE PRECISION

Columns - Capital Allocation:
  payout_ratio DOUBLE PRECISION
  
Primary Key: (symbol, date)
Indexes:
  - idx_quality_metrics_symbol
  - idx_quality_metrics_date (DESC)
```

### growth_metrics
**Purpose**: Growth metrics (from `loadgrowthmetrics.py`)
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  revenue_growth_3y_cagr DOUBLE PRECISION
  eps_growth_3y_cagr DOUBLE PRECISION
  operating_income_growth_yoy DOUBLE PRECISION
  roe_trend DOUBLE PRECISION
  sustainable_growth_rate DOUBLE PRECISION
  fcf_growth_yoy DOUBLE PRECISION
  net_income_growth_yoy DOUBLE PRECISION
  gross_margin_trend DOUBLE PRECISION
  operating_margin_trend DOUBLE PRECISION
  net_margin_trend DOUBLE PRECISION
  quarterly_growth_momentum DOUBLE PRECISION
  asset_growth_yoy DOUBLE PRECISION
  
Primary Key: (symbol, date)
Indexes:
  - idx_growth_metrics_symbol
  - idx_growth_metrics_date (DESC)
```

### momentum_metrics
**Purpose**: Momentum analysis metrics
```sql
Columns - Relative Momentum:
  momentum_12m_1 DOUBLE PRECISION
  momentum_6m DOUBLE PRECISION
  momentum_3m DOUBLE PRECISION
  risk_adjusted_momentum DOUBLE PRECISION

Columns - Absolute Momentum:
  price_vs_sma_50 DOUBLE PRECISION
  price_vs_sma_200 DOUBLE PRECISION
  price_vs_52w_high DOUBLE PRECISION

Columns - Supporting Data:
  current_price DOUBLE PRECISION
  sma_50 DOUBLE PRECISION
  sma_200 DOUBLE PRECISION
  high_52w DOUBLE PRECISION
  volatility_12m DOUBLE PRECISION
  
Primary Key: (symbol, date)
Indexes:
  - idx_momentum_metrics_symbol
  - idx_momentum_metrics_date (DESC)
```

### risk_metrics
**Purpose**: Risk measurements
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  volatility_12m_pct DOUBLE PRECISION
  volatility_risk_component DOUBLE PRECISION
  max_drawdown_52w_pct DOUBLE PRECISION
  beta DOUBLE PRECISION
  
Primary Key: (symbol, date)
Indexes:
  - idx_risk_metrics_symbol
  - idx_risk_metrics_date (DESC)
```

### positioning_metrics
**Purpose**: Institutional & insider positioning data
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  institutional_ownership DOUBLE PRECISION
  insider_ownership DOUBLE PRECISION
  short_percent_of_float DOUBLE PRECISION
  short_ratio DOUBLE PRECISION
  short_interest_change DOUBLE PRECISION
  institution_count INTEGER
  acc_dist_rating DOUBLE PRECISION
  days_to_cover DOUBLE PRECISION
  
Primary Key: (symbol, date)
Indexes:
  - idx_positioning_metrics_symbol
  - idx_positioning_metrics_date (DESC)
```

---

## 7. Earnings & Financial Statement Tables

### earnings_history
**Purpose**: Historical earnings data (4000+ records from loaders)
```sql
Columns:
  symbol VARCHAR(50)
  quarter DATE
  eps_actual DOUBLE PRECISION
  eps_estimate DOUBLE PRECISION
  eps_surprise DOUBLE PRECISION
  earnings_date DATE
  
Primary Key: (symbol, quarter)
Date Range: Last 24+ months of quarterly earnings
Sample Query: SELECT eps_actual FROM earnings_history WHERE symbol = 'AAPL' AND quarter >= CURRENT_DATE - INTERVAL '24 months' ORDER BY quarter DESC LIMIT 8;
```

### earnings
**Purpose**: Earnings data
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  actual DOUBLE PRECISION
  estimate DOUBLE PRECISION
  surprise_pct DOUBLE PRECISION
  
Primary Key: (symbol, date)
```

### annual_balance_sheet
**Purpose**: Annual balance sheet data
```sql
Similar structure to financial statements with annual frequency
```

### quarterly_income_statement
**Purpose**: Quarterly income statement data
```sql
Similar structure with quarterly frequency
```

### revenue_estimates
**Purpose**: Revenue projection data
```sql
Columns:
  symbol VARCHAR(50)
  period DATE
  estimate DOUBLE PRECISION
  previous DOUBLE PRECISION
  etc.
```

### buy_sell_daily
**Purpose**: Daily buy/sell signals
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  buy_signal INT
  sell_signal INT
  signal_strength DECIMAL
  etc.
```

### buy_sell_monthly
**Purpose**: Monthly aggregated buy/sell data
```sql
Similar structure to buy_sell_daily with monthly interval
```

---

## 8. Sentiment & Market Indicators Tables

### fear_greed_index
**Purpose**: CNN Fear & Greed Index data (from `loadfeargreed.py`)
```sql
Columns:
  date DATE PRIMARY KEY
  index_value INT [0-100 scale]
  rating VARCHAR(50) [e.g., "Extreme Greed", "Greed", "Neutral", "Fear", "Extreme Fear"]
  
Update Frequency: Daily (via Puppeteer scraping of CNN API)
Data Range: Historical data available
Sample Data: Date-based lookup for market sentiment
```

### aaii_sentiment
**Purpose**: AAII (American Association of Individual Investors) sentiment data (from `loadaaiidata.py`)
```sql
Columns:
  date DATE PRIMARY KEY
  bullish_pct DOUBLE PRECISION
  neutral_pct DOUBLE PRECISION
  bearish_pct DOUBLE PRECISION
  bullish_count INT
  neutral_count INT
  bearish_count INT
  total_investors INT
  
Update Frequency: Weekly
Historical Data: Available
```

### naaim
**Purpose**: NAAIM (National Association of Active Investment Managers) exposure index (from `loadnaaim.py`)
```sql
Columns:
  date DATE PRIMARY KEY
  naaim_exposure INT [0-100 scale, 0=net short, 50=neutral, 100=net long]
  
Update Frequency: Daily
Interpretation: High values = bullish positioning, Low values = bearish
```

### analyst_sentiment_analysis
**Purpose**: Analyst sentiment data (from `loadsentiment.py`)
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  buy_count INT
  hold_count INT
  sell_count INT
  target_price DOUBLE PRECISION
  sentiment_score DOUBLE PRECISION
  
Primary Key: (symbol, date)
```

### social_sentiment_analysis
**Purpose**: Social media sentiment (from `loadsentiment.py`)
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  bullish_posts INT
  bearish_posts INT
  sentiment_score DOUBLE PRECISION
  
Primary Key: (symbol, date)
```

### realtime_sentiment_analysis
**Purpose**: Real-time sentiment updates (from `loadsentiment_realtime.py`)
```sql
Similar to social_sentiment_analysis with more frequent updates
```

### sentiment
**Purpose**: General sentiment score aggregation
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  sentiment_score DOUBLE PRECISION [Composite sentiment]
  
Primary Key: (symbol, date)
```

### sentiment_scores
**Purpose**: Calculated sentiment scores
```sql
Similar structure to sentiment with additional components
```

### crypto_fear_greed
**Purpose**: Cryptocurrency-specific fear/greed index (from `loadcrypto.py`)
```sql
Similar structure to fear_greed_index but for crypto assets
```

---

## 9. Analyst & News Tables

### analyst_upgrade_downgrade
**Purpose**: Analyst rating changes
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  analyst_name VARCHAR(255)
  rating_from VARCHAR(50)
  rating_to VARCHAR(50)
  target_price DOUBLE PRECISION
  
Primary Key: (symbol, date, analyst_name)
```

### stock_news
**Purpose**: News articles/headlines
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  title VARCHAR(500)
  description TEXT
  url VARCHAR(500)
  source VARCHAR(100)
  
Primary Key: (symbol, date, title)
```

### news_articles
**Purpose**: Detailed news articles
```sql
Similar to stock_news with extended content
```

---

## 10. Crypto Tables (if applicable)

### crypto_assets
**Purpose**: Cryptocurrency asset registry
```sql
Columns:
  symbol VARCHAR(50) PRIMARY KEY
  name VARCHAR(255)
  category VARCHAR(100)
```

### crypto_prices
**Purpose**: Cryptocurrency price data
```sql
Similar structure to price_daily but for crypto assets
```

### crypto_market_metrics
**Purpose**: Market-level crypto metrics
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  market_cap BIGINT
  volume_24h BIGINT
  change_24h DOUBLE PRECISION
  dominance_pct DOUBLE PRECISION
  
Primary Key: (symbol, date)
```

### crypto_exchanges
**Purpose**: Exchange data
```sql
Crypto exchange information and metrics
```

### defi_tvl
**Purpose**: DeFi Total Value Locked
```sql
Columns:
  protocol VARCHAR(255)
  date DATE
  tvl BIGINT
  
Primary Key: (protocol, date)
```

### crypto_movers
**Purpose**: Top movers in crypto
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  change_pct DOUBLE PRECISION
  rank INT
```

### crypto_trending
**Purpose**: Trending crypto assets
```sql
Similar structure to crypto_movers with trend data
```

---

## 11. Administrative Tables

### last_updated
**Purpose**: Track when each data loader last ran successfully
```sql
Columns:
  script_name VARCHAR(255) PRIMARY KEY [e.g., "loadpricedaily.py", "loadstockscores.py"]
  last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  
Used By: Loaders to check if data needs updating and monitor pipeline health
```

### sector_benchmarks
**Purpose**: Sector-level financial benchmarks
```sql
Columns:
  sector VARCHAR(100) PRIMARY KEY
  pe_ratio DOUBLE PRECISION
  price_to_book DOUBLE PRECISION
  ev_to_ebitda DOUBLE PRECISION
  debt_to_equity DOUBLE PRECISION
  
Used For: Relative valuation comparisons
```

### insider_roster
**Purpose**: Insider information registry
```sql
Columns:
  symbol VARCHAR(50)
  insider_name VARCHAR(255)
  relationship VARCHAR(100)
  position VARCHAR(255)
```

### insider_transactions
**Purpose**: Insider transaction history
```sql
Columns:
  symbol VARCHAR(50)
  insider_name VARCHAR(255)
  date DATE
  transaction_type VARCHAR(50) [Buy/Sell]
  quantity INT
  price DOUBLE PRECISION
  value BIGINT
```

### institutional_positioning
**Purpose**: Institutional ownership changes
```sql
Columns:
  symbol VARCHAR(50)
  date DATE
  institution_name VARCHAR(255)
  shares_held BIGINT
  value BIGINT
  change_pct DOUBLE PRECISION
```

---

## Critical Queries & Examples

### 1. Get Latest Stock Scores
```sql
SELECT 
  symbol, composite_score, momentum_score, value_score, 
  quality_score, growth_score, current_price, last_updated
FROM stock_scores
ORDER BY composite_score DESC
LIMIT 50;
```

### 2. Get Recent Price Data (Last 5 Days)
```sql
SELECT DISTINCT ON (symbol)
  symbol, date, close, volume, adj_close
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '5 days'
ORDER BY symbol, date DESC;
```

### 3. Get Company Fundamentals
```sql
SELECT 
  cp.ticker, cp.short_name, cp.sector, cp.industry,
  km.trailing_pe, km.forward_pe, km.dividend_yield,
  md.market_cap
FROM company_profile cp
LEFT JOIN key_metrics km ON cp.ticker = km.ticker
LEFT JOIN market_data md ON cp.ticker = md.ticker;
```

### 4. Get Market Sentiment
```sql
SELECT 
  date, index_value, rating
FROM fear_greed_index
ORDER BY date DESC
LIMIT 30;
```

### 5. Get Technical Analysis
```sql
SELECT 
  symbol, date, rsi, macd, sma_20, sma_50, sma_200
FROM technical_data_daily
WHERE symbol = 'AAPL'
ORDER BY date DESC
LIMIT 20;
```

### 6. Get Earnings History
```sql
SELECT 
  symbol, quarter, eps_actual, eps_estimate, eps_surprise
FROM earnings_history
WHERE symbol = 'AAPL'
AND quarter >= CURRENT_DATE - INTERVAL '24 months'
ORDER BY quarter DESC;
```

### 7. Get Growth & Quality Metrics
```sql
SELECT 
  gm.symbol, gm.date,
  gm.revenue_growth_3y_cagr, gm.eps_growth_3y_cagr,
  qm.return_on_equity_pct, qm.profit_margin_pct,
  qm.debt_to_equity, qm.current_ratio
FROM growth_metrics gm
LEFT JOIN quality_metrics qm 
  ON gm.symbol = qm.symbol AND gm.date = qm.date
WHERE gm.date >= CURRENT_DATE - INTERVAL '1 day'
ORDER BY gm.symbol;
```

### 8. Get Positioning Metrics
```sql
SELECT 
  symbol, date, institutional_ownership, insider_ownership,
  short_percent_of_float, short_interest_change
FROM positioning_metrics
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY symbol, date DESC;
```

---

## Data Loading Pipeline

| Script Name | Tables Modified | Frequency | Data Source | Update Method |
|-------------|-----------------|-----------|-------------|----------------|
| `loadpricedaily.py` | price_daily, etf_price_daily | Daily | yfinance | Full history + incremental |
| `loadmarket.py` | market_data, indices | Daily | yfinance, FRED | Snapshot |
| `loadstockscores.py` | stock_scores | Daily | Calculated from other tables | Calculate & upsert |
| `loadinfo.py` | company_profile, key_metrics | Weekly/Monthly | yfinance + APIs | Upsert |
| `loaddailycompanydata.py` | key_metrics, company_profile | Daily | APIs | Update |
| `loadqualitymetrics.py` | quality_metrics | Daily/Weekly | Financial APIs | Insert |
| `loadgrowthmetrics.py` | growth_metrics | Daily/Weekly | Financial APIs | Insert |
| `loadmomentummetrics.py` | momentum_metrics | Daily | Calculated | Calculate & insert |
| `loadriskmetrics.py` | risk_metrics | Daily | Calculated | Calculate & insert |
| `loadfeargreed.py` | fear_greed_index | Daily | CNN (web scrape) | Upsert |
| `loadaaiidata.py` | aaii_sentiment | Weekly | AAII API | Insert |
| `loadnaaim.py` | naaim | Daily | NAAIM API | Insert |
| `loadsentiment.py` | analyst_sentiment, social_sentiment | Daily | News/Social APIs | Insert |
| `loadpositioningmetrics.py` | positioning_metrics | Weekly | Financial data APIs | Insert |
| `loadearningshistory.py` | earnings_history | Daily/Weekly | Financial APIs | Update/Insert |
| `loadtechnicalsdaily.py` | technical_data_daily | Daily | Calculated | Calculate & upsert |

---

## Key Performance Considerations

### Indexes Present
- `stock_scores`: (symbol), (composite_score DESC), (last_updated), (score_date)
- `price_daily`: (symbol, date) UNIQUE
- `quality_metrics`: (symbol), (date DESC)
- `growth_metrics`: (symbol), (date DESC)
- `momentum_metrics`: (symbol), (date DESC)
- `risk_metrics`: (symbol), (date DESC)
- `positioning_metrics`: (symbol), (date DESC)

### Common Slow Queries Identified
- JOINing multiple metric tables across date ranges
- Aggregations over large price_daily datasets
- Multi-symbol JOINs without proper indexes
- SELECT DISTINCT ON with large datasets

### Optimization Tips
- Always filter by recent dates when possible (last 30-90 days)
- Use LIMIT when not needing full dataset
- Pre-calculate aggregations in `stock_scores` table
- Avoid JOINing >2-3 large tables per query
- Use partial indexes for active data (date > 1 year ago)

---

## Notes

1. **Date-based Data**: Most tables use DATE or TIMESTAMP fields. Use ISO format (YYYY-MM-DD) for queries.

2. **NULL Handling**: Many optional columns can be NULL. Always use COALESCE() for default values.

3. **Stock Scores JSON**: `value_inputs` and `stability_inputs` JSONB columns contain detailed component metrics extracted from individual metric tables.

4. **Decimal vs DOUBLE PRECISION**: 
   - DECIMAL used for scores, prices (exact values)
   - DOUBLE PRECISION used for percentages, ratios (calculated values)

5. **Primary Keys**: Most metric tables use composite (symbol, date) primary keys for time-series data.

6. **Data Gaps**: Not all symbols have data in all tables. Check for existence before complex operations.

7. **AWS Secrets Manager**: In production, all DB credentials come from AWS Secrets Manager, never hardcoded.

8. **Update Tracking**: `last_updated` table helps orchestrate loader dependencies and failure recovery.

