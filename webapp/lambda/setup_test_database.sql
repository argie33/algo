-- Test Database Setup - Ensures core tables exist for tests
-- This file is part of the test setup and runs as global setup for Jest
-- The database schema is already loaded by data loaders

-- Ensure core tables exist with proper structure
-- These tables are created by the Python data loaders, so we just verify existence

-- Stock Symbols (foundational - needed for all stock data)
CREATE TABLE IF NOT EXISTS stock_symbols (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) UNIQUE NOT NULL,
  name VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Price Data (foundational - needed for technical indicators and scores)
CREATE TABLE IF NOT EXISTS price_daily (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  open DECIMAL(10,2),
  high DECIMAL(10,2),
  low DECIMAL(10,2),
  close DECIMAL(10,2),
  volume BIGINT,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(symbol, date)
);

-- Technical Data (needed for scoring)
CREATE TABLE IF NOT EXISTS technical_data_daily (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  rsi DECIMAL(10,2),
  macd DECIMAL(10,2),
  signal_line DECIMAL(10,2),
  macd_histogram DECIMAL(10,2),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(symbol, date)
);

-- Company Profile (fundamental company data)
CREATE TABLE IF NOT EXISTS company_profile (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL UNIQUE,
  name VARCHAR(255),
  sector VARCHAR(100),
  industry VARCHAR(100),
  website VARCHAR(255),
  description TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Stock Scores (composite scoring for screening)
CREATE TABLE IF NOT EXISTS stock_scores (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  quality_score DECIMAL(10,2),
  momentum_score DECIMAL(10,2),
  value_score DECIMAL(10,2),
  growth_score DECIMAL(10,2),
  positioning_score DECIMAL(10,2),
  risk_score DECIMAL(10,2),
  composite_score DECIMAL(10,2),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(symbol, date)
);

-- Positioning Data (for positioning analysis)
CREATE TABLE IF NOT EXISTS positioning_metrics (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  short_interest DECIMAL(10,2),
  put_call_ratio DECIMAL(10,2),
  institutional_ownership DECIMAL(10,2),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(symbol, date)
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily(symbol, date);
CREATE INDEX IF NOT EXISTS idx_stock_scores_symbol_date ON stock_scores(symbol, date);
CREATE INDEX IF NOT EXISTS idx_positioning_metrics_symbol_date ON positioning_metrics(symbol, date);
