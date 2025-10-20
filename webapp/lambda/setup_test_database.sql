-- Test Database Setup - Exact Match to Python Loader Schemas
-- This ensures tests use the exact same table structures as production loaders

-- Stock Symbols (foundational)
CREATE TABLE IF NOT EXISTS stock_symbols (
  symbol VARCHAR(50) PRIMARY KEY,
  exchange VARCHAR(100),
  security_name TEXT,
  cqs_symbol VARCHAR(50),
  market_category VARCHAR(50),
  test_issue CHAR(1),
  financial_status VARCHAR(50),
  round_lot_size INT,
  etf CHAR(1),
  secondary_symbol VARCHAR(50)
);

-- Company Profile
CREATE TABLE IF NOT EXISTS company_profile (
  ticker VARCHAR(50) PRIMARY KEY,
  short_name VARCHAR(255),
  long_name VARCHAR(255),
  sector VARCHAR(100),
  industry VARCHAR(100),
  website VARCHAR(255),
  description TEXT
);

-- Price Daily (from loadpricedaily.py)
CREATE TABLE IF NOT EXISTS price_daily (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION,
  adj_close DOUBLE PRECISION,
  volume BIGINT,
  dividends DOUBLE PRECISION,
  stock_splits DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol, date)
);

-- Stock Scores (from loadstockscores.py - lines 99-140)
CREATE TABLE IF NOT EXISTS stock_scores (
  symbol VARCHAR(50) PRIMARY KEY,
  composite_score DECIMAL(5,2),
  momentum_score DECIMAL(5,2),
  value_score DECIMAL(5,2),
  quality_score DECIMAL(5,2),
  growth_score DECIMAL(5,2),
  positioning_score DECIMAL(5,2),
  sentiment_score DECIMAL(5,2),
  rsi DECIMAL(5,2),
  macd DECIMAL(10,4),
  sma_20 DECIMAL(10,2),
  sma_50 DECIMAL(10,2),
  volume_avg_30d BIGINT,
  current_price DECIMAL(10,2),
  price_change_1d DECIMAL(5,2),
  price_change_5d DECIMAL(5,2),
  price_change_30d DECIMAL(5,2),
  volatility_30d DECIMAL(5,2),
  market_cap BIGINT,
  pe_ratio DECIMAL(8,2),
  -- Momentum components
  momentum_intraweek DECIMAL(5,2),
  momentum_short_term DECIMAL(5,2),
  momentum_medium_term DECIMAL(5,2),
  momentum_long_term DECIMAL(5,2),
  momentum_consistency DECIMAL(5,2),
  roc_10d DECIMAL(8,2),
  roc_20d DECIMAL(8,2),
  roc_60d DECIMAL(8,2),
  roc_120d DECIMAL(8,2),
  roc_252d DECIMAL(8,2),
  mom DECIMAL(10,2),
  mansfield_rs DECIMAL(8,2),
  -- Positioning
  acc_dist_rating DECIMAL(5,2),
  -- Value metrics stored as JSONB
  value_inputs JSONB,
  score_date DATE DEFAULT CURRENT_DATE,
  last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key Metrics
CREATE TABLE IF NOT EXISTS key_metrics (
  ticker VARCHAR(50) PRIMARY KEY,
  trailing_pe DOUBLE PRECISION,
  forward_pe DOUBLE PRECISION,
  price_to_book DOUBLE PRECISION,
  price_to_sales_ttm DOUBLE PRECISION,
  ev_to_ebitda DOUBLE PRECISION,
  dividend_yield DOUBLE PRECISION,
  earnings_growth_pct DOUBLE PRECISION,
  revenue_growth_pct DOUBLE PRECISION,
  free_cashflow BIGINT,
  enterprise_value BIGINT,
  total_debt BIGINT,
  total_cash BIGINT
);

-- Market Data
CREATE TABLE IF NOT EXISTS market_data (
  ticker VARCHAR(50) PRIMARY KEY,
  market_cap BIGINT
);

-- Sector Benchmarks
CREATE TABLE IF NOT EXISTS sector_benchmarks (
  sector VARCHAR(100) PRIMARY KEY,
  pe_ratio DOUBLE PRECISION,
  price_to_book DOUBLE PRECISION,
  ev_to_ebitda DOUBLE PRECISION,
  debt_to_equity DOUBLE PRECISION
);

-- Quality Metrics (from loadqualitymetrics.py lines 130-162)
CREATE TABLE IF NOT EXISTS quality_metrics (
  symbol VARCHAR(50),
  date DATE,
  -- PROFITABILITY (5 metrics)
  return_on_equity_pct DOUBLE PRECISION,
  return_on_assets_pct DOUBLE PRECISION,
  gross_margin_pct DOUBLE PRECISION,
  operating_margin_pct DOUBLE PRECISION,
  profit_margin_pct DOUBLE PRECISION,
  -- CASH QUALITY (2 metrics)
  fcf_to_net_income DOUBLE PRECISION,
  operating_cf_to_net_income DOUBLE PRECISION,
  -- BALANCE SHEET STRENGTH (3 metrics)
  debt_to_equity DOUBLE PRECISION,
  current_ratio DOUBLE PRECISION,
  quick_ratio DOUBLE PRECISION,
  -- EARNINGS QUALITY (2 metrics)
  earnings_surprise_avg DOUBLE PRECISION,
  eps_growth_stability DOUBLE PRECISION,
  -- CAPITAL ALLOCATION (1 metric)
  payout_ratio DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, date)
);

-- Growth Metrics (from loadgrowthmetrics.py)
CREATE TABLE IF NOT EXISTS growth_metrics (
  symbol VARCHAR(50),
  date DATE,
  revenue_growth_3y_cagr DOUBLE PRECISION,
  eps_growth_3y_cagr DOUBLE PRECISION,
  operating_income_growth_yoy DOUBLE PRECISION,
  roe_trend DOUBLE PRECISION,
  sustainable_growth_rate DOUBLE PRECISION,
  fcf_growth_yoy DOUBLE PRECISION,
  net_income_growth_yoy DOUBLE PRECISION,
  gross_margin_trend DOUBLE PRECISION,
  operating_margin_trend DOUBLE PRECISION,
  net_margin_trend DOUBLE PRECISION,
  quarterly_growth_momentum DOUBLE PRECISION,
  asset_growth_yoy DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, date)
);

-- Momentum Metrics (from loadmomentummetrics.py)
CREATE TABLE IF NOT EXISTS momentum_metrics (
  symbol VARCHAR(50),
  date DATE,
  -- RELATIVE MOMENTUM
  momentum_12m_1 DOUBLE PRECISION,
  momentum_6m DOUBLE PRECISION,
  momentum_3m DOUBLE PRECISION,
  risk_adjusted_momentum DOUBLE PRECISION,
  -- ABSOLUTE MOMENTUM
  price_vs_sma_50 DOUBLE PRECISION,
  price_vs_sma_200 DOUBLE PRECISION,
  price_vs_52w_high DOUBLE PRECISION,
  -- Supporting data
  current_price DOUBLE PRECISION,
  sma_50 DOUBLE PRECISION,
  sma_200 DOUBLE PRECISION,
  high_52w DOUBLE PRECISION,
  volatility_12m DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, date)
);

-- Risk Metrics (from loadriskmetrics.py)
CREATE TABLE IF NOT EXISTS risk_metrics (
  symbol VARCHAR(50),
  date DATE,
  volatility_12m_pct DOUBLE PRECISION,
  volatility_risk_component DOUBLE PRECISION,
  max_drawdown_52w_pct DOUBLE PRECISION,
  beta DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, date)
);

-- Positioning Metrics
CREATE TABLE IF NOT EXISTS positioning_metrics (
  symbol VARCHAR(50),
  date DATE,
  institutional_ownership DOUBLE PRECISION,
  insider_ownership DOUBLE PRECISION,
  short_percent_of_float DOUBLE PRECISION,
  short_ratio DOUBLE PRECISION,
  institution_count INTEGER,
  acc_dist_rating DOUBLE PRECISION,
  days_to_cover DOUBLE PRECISION,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, date)
);

-- Earnings Data
CREATE TABLE IF NOT EXISTS earnings (
  symbol VARCHAR(50),
  date DATE,
  actual DOUBLE PRECISION,
  estimate DOUBLE PRECISION,
  surprise_pct DOUBLE PRECISION,
  PRIMARY KEY (symbol, date)
);

-- Last Updated Tracker
CREATE TABLE IF NOT EXISTS last_updated (
  script_name VARCHAR(255) PRIMARY KEY,
  last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol ON stock_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol ON quality_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_date ON quality_metrics(date DESC);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol ON growth_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_growth_metrics_date ON growth_metrics(date DESC);
CREATE INDEX IF NOT EXISTS idx_momentum_metrics_symbol ON momentum_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_momentum_metrics_date ON momentum_metrics(date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_metrics_symbol ON risk_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_risk_metrics_date ON risk_metrics(date DESC);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol ON positioning_metrics(symbol);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_date ON positioning_metrics(date DESC);
