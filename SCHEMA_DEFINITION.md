# Authoritative Schema Definition - Single Source of Truth

**Status**: ✅ AUTHORITATIVE - All loaders and setup scripts must reference this

Generated from actual database: 2026-04-25

---

## earnings_estimates

**Source**: Historical and forward-looking earnings data

```sql
CREATE TABLE earnings_estimates (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quarter DATE,                          -- Earnings quarter
    fiscal_quarter INTEGER,                -- Q1, Q2, Q3, Q4
    fiscal_year INTEGER,                   -- Fiscal year
    earnings_date DATE,                    -- When earnings reported/will be reported
    estimated BOOLEAN,                     -- true=forecast, false=actual
    
    -- Actual reported values (only if estimated=false)
    eps_actual DECIMAL(12, 4),            
    revenue_actual DECIMAL(16, 2),        
    
    -- Estimated values (analyst forecasts)
    eps_estimate DECIMAL(12, 4),          
    revenue_estimate DECIMAL(16, 2),      
    
    -- Surprise metrics
    eps_surprise_pct DECIMAL(8, 2),       -- % difference from estimate
    revenue_surprise_pct DECIMAL(8, 2),   
    eps_difference DECIMAL(12, 4),        -- Absolute difference
    revenue_difference DECIMAL(16, 2),    
    beat_miss_flag VARCHAR(20),           -- 'beat', 'miss', null
    surprise_percent DECIMAL(8, 2),       
    
    -- Tracking fields
    estimate_revision_days INTEGER,       -- Days since estimate revised
    estimate_revision_count INTEGER,      -- Number of revisions
    fetched_at TIMESTAMP,                 -- When data was fetched from API
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, quarter)
);
```

**Loader**: `loadearningshistory.py`

**Data Source**: yfinance (ticker.quarterly_financials, ticker.quarterly_income_stmt)

---

## analyst_upgrade_downgrade

**Source**: Analyst ratings changes

```sql
CREATE TABLE analyst_upgrade_downgrade (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    action_date DATE,                     -- When rating changed
    firm VARCHAR(100),                    -- Analyst firm name
    old_rating VARCHAR(50),               -- Previous rating (Hold, Buy, Sell, etc)
    new_rating VARCHAR(50),               -- New rating
    action VARCHAR(20),                   -- Type of change (Upgrade, Downgrade, etc)
    company_name VARCHAR(255),            -- Company name (joined from company_profile)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadanalystupgradedowngrade.py`

**Data Source**: yfinance (ticker.upgrades_downgrades, ticker.info)

---

## analyst_sentiment_analysis

**Source**: Aggregate analyst sentiment

```sql
CREATE TABLE analyst_sentiment_analysis (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE,                            -- Sentiment date
    analyst_count INTEGER,                -- Total analysts covering
    bullish_count INTEGER,                -- Buy recommendations
    bearish_count INTEGER,                -- Sell recommendations
    neutral_count INTEGER,                -- Hold recommendations
    
    target_price DECIMAL(12, 4),          -- Average price target
    current_price DECIMAL(12, 4),         -- Current market price
    upside_downside_percent DECIMAL(8, 2), -- % upside/downside
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
```

**Loader**: `loadanalystsentiment.py`

**Data Source**: yfinance (ticker.info)

---

## price_daily

**Source**: Daily OHLCV data

```sql
CREATE TABLE price_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(12, 4),
    high DECIMAL(12, 4),
    low DECIMAL(12, 4),
    close DECIMAL(12, 4),
    volume BIGINT,
    adj_close DECIMAL(12, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, date),
    INDEX idx_symbol_date (symbol, date)
);
```

**Loader**: `loadpricedaily.py`

**Data Source**: yfinance (ticker.history)

---

## technical_data_daily

**Source**: Calculated technical indicators

```sql
CREATE TABLE technical_data_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    
    -- Momentum indicators
    rsi DECIMAL(8, 4),                   -- Relative Strength Index (0-100)
    macd DECIMAL(12, 4),                 -- MACD line
    macd_signal DECIMAL(12, 4),          -- Signal line
    macd_hist DECIMAL(12, 4),            -- Histogram
    mom DECIMAL(12, 4),                  -- Momentum
    roc DECIMAL(8, 4),                   -- Rate of Change
    roc_10d DECIMAL(8, 4),               -- 10-day ROC
    roc_20d DECIMAL(8, 4),               -- 20-day ROC
    roc_60d DECIMAL(8, 4),               -- 60-day ROC
    roc_120d DECIMAL(8, 4),              -- 120-day ROC
    roc_252d DECIMAL(8, 4),              -- 252-day ROC (1 year)
    
    -- Moving averages
    sma_20 DECIMAL(12, 4),               -- 20-day simple moving average
    sma_50 DECIMAL(12, 4),               -- 50-day SMA
    sma_200 DECIMAL(12, 4),              -- 200-day SMA
    ema_12 DECIMAL(12, 4),               -- 12-day exponential moving average
    ema_26 DECIMAL(12, 4),               -- 26-day EMA
    
    -- Volatility indicators
    atr DECIMAL(12, 4),                  -- Average True Range
    adx DECIMAL(8, 4),                   -- Average Directional Index
    plus_di DECIMAL(8, 4),               -- +DI component
    minus_di DECIMAL(8, 4),              -- -DI component
    
    -- Other
    mansfield_rs DECIMAL(8, 4),          -- Mansfield Relative Strength
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, date),
    INDEX idx_symbol_date (symbol, date)
);
```

**Loader**: `loadtechnicalindicators.py`

**Calculation**: Derived from price_daily using TA-Lib or similar

---

## buy_sell_daily

**Source**: Trading signals (Buy/Sell recommendations)

```sql
CREATE TABLE buy_sell_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    
    signal VARCHAR(20),                  -- 'BUY', 'SELL', 'HOLD'
    strength DECIMAL(8, 4),              -- Signal strength (0-1)
    reason VARCHAR(255),                 -- Why signal generated
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, date),
    INDEX idx_symbol_date (symbol, date)
);
```

**Loader**: `loadbuyselldaily.py`

**Calculation**: Based on technical indicators and price action

---

## buy_sell_weekly

**Source**: Weekly trading signals

```sql
CREATE TABLE buy_sell_weekly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    week_ending DATE NOT NULL,
    
    signal VARCHAR(20),                  -- 'BUY', 'SELL', 'HOLD'
    strength DECIMAL(8, 4),              -- Signal strength (0-1)
    reason VARCHAR(255),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, week_ending)
);
```

**Loader**: `loadbuysellweekly.py`

---

## buy_sell_monthly

**Source**: Monthly trading signals

```sql
CREATE TABLE buy_sell_monthly (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    month_ending DATE NOT NULL,
    
    signal VARCHAR(20),
    strength DECIMAL(8, 4),
    reason VARCHAR(255),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, month_ending)
);
```

**Loader**: `loadbuysellmonthly.py`

---

## stock_scores

**Source**: Composite stock quality score

```sql
CREATE TABLE stock_scores (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    
    composite_score DECIMAL(8, 2),       -- 0-100 overall score
    quality_score DECIMAL(8, 2),         -- Profitability, margins
    growth_score DECIMAL(8, 2),          -- Revenue/earnings growth
    stability_score DECIMAL(8, 2),       -- Debt, volatility
    value_score DECIMAL(8, 2),           -- P/E, P/B ratios
    momentum_score DECIMAL(8, 2),        -- Price trend
    positioning_score DECIMAL(8, 2),     -- Insider/institutional ownership
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadstockscores.py` (depends on quality/growth/stability/value/positioning metrics)

---

## quality_metrics

```sql
CREATE TABLE quality_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    
    operating_margin DECIMAL(8, 4),
    net_margin DECIMAL(8, 4),
    roe DECIMAL(8, 4),                  -- Return on Equity
    roa DECIMAL(8, 4),                  -- Return on Assets
    debt_to_equity DECIMAL(8, 4),
    current_ratio DECIMAL(8, 4),
    quick_ratio DECIMAL(8, 4),
    interest_coverage DECIMAL(8, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadfactormetrics.py`

---

## growth_metrics

```sql
CREATE TABLE growth_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    
    revenue_growth_5y DECIMAL(8, 4),
    revenue_growth_3y DECIMAL(8, 4),
    revenue_growth_1y DECIMAL(8, 4),
    eps_growth_5y DECIMAL(8, 4),
    eps_growth_3y DECIMAL(8, 4),
    eps_growth_1y DECIMAL(8, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadfactormetrics.py`

---

## stability_metrics

```sql
CREATE TABLE stability_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    
    volatility_30d DECIMAL(8, 4),
    volatility_60d DECIMAL(8, 4),
    volatility_252d DECIMAL(8, 4),
    beta DECIMAL(8, 4),
    debt_to_assets DECIMAL(8, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadfactormetrics.py`

---

## value_metrics

```sql
CREATE TABLE value_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    
    pe_ratio DECIMAL(8, 4),
    pb_ratio DECIMAL(8, 4),
    ps_ratio DECIMAL(8, 4),
    peg_ratio DECIMAL(8, 4),
    dividend_yield DECIMAL(8, 4),
    fcf_yield DECIMAL(8, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadfactormetrics.py`

---

## positioning_metrics

```sql
CREATE TABLE positioning_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    
    institutional_ownership DECIMAL(8, 4),
    insider_ownership DECIMAL(8, 4),
    short_interest_percent DECIMAL(8, 4),
    shares_short_prior_month BIGINT,
    short_interest_trend VARCHAR(20),    -- 'up', 'down', 'neutral'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Loader**: `loadfactormetrics.py`

---

## Key Points

1. **This is authoritative** - all loaders must insert into these EXACT columns
2. **No duplication** - each table defined once and only once
3. **Clear ownership** - each table has designated loader(s)
4. **Type consistency** - all DECIMAL types specified with precision
5. **Indexes** - common query patterns indexed for performance
6. **Uniqueness** - prevents duplicate data
7. **Timestamps** - track when data was loaded and last updated

---

## Files to Update/Remove

**Keep**:
- `init_database.py` - Will be updated to match this schema

**Remove**:
- `initialize-schema.py` - Obsolete, conflicting
- `init_schema.py` - Duplicate
- All `CREATE TABLE` statements from individual loaders

**Update**:
- All loaders - remove CREATE TABLE, verify column names match exactly
