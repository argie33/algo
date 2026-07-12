-- Migration: Add missing tables and fix schema gaps from Session 77-78
-- Date: 2026-07-11
-- Context: System diagnostics discovered critical missing tables (trend_template_data, sector_rotation_signal)
--          that were blocking orchestrator and dashboard functionality

-- ============================================================================
-- Table 1: trend_template_data
-- ============================================================================
-- Used by: Minervini/Weinstein trend analysis, market exposure calculation, signal filtering
-- Dependency: technical_data_daily, price_daily
-- Loaded by: load_trend_analysis.py
-- Purpose: Precompute trend scores (Minervini 0-8, Weinstein stage 1-4) for all symbols daily

CREATE TABLE IF NOT EXISTS trend_template_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    weinstein_stage INT,
    minervini_trend_score FLOAT,
    trend_direction VARCHAR(20),
    price_above_sma50 BOOLEAN,
    data_unavailable BOOLEAN DEFAULT FALSE,
    reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_trend_template_data_date ON trend_template_data(date DESC);
CREATE INDEX IF NOT EXISTS idx_trend_template_data_symbol ON trend_template_data(symbol);
CREATE INDEX IF NOT EXISTS idx_trend_template_data_symbol_date ON trend_template_data(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_trend_template_data_unavailable ON trend_template_data(data_unavailable) WHERE data_unavailable = TRUE;

-- ============================================================================
-- Table 2: sector_rotation_signal
-- ============================================================================
-- Used by: Market exposure calculation (defensive vs cyclical rotation), strategy analysis
-- Loaded by: load_market_exposure_daily.py (as part of sector rotation detection)
-- Purpose: Store daily sector rotation signal (defensive or cyclical leadership)

CREATE TABLE IF NOT EXISTS sector_rotation_signal (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    sector VARCHAR(100) NOT NULL,
    signal VARCHAR(50),
    strength FLOAT,
    rank INT,
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(date, sector)
);

CREATE INDEX IF NOT EXISTS idx_sector_rotation_signal_date ON sector_rotation_signal(date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_rotation_signal_date_sector ON sector_rotation_signal(date, sector);

-- ============================================================================
-- Bootstrap Data: sector_ranking historical ranks
-- ============================================================================
-- Issue: System too new (< 12 weeks old) to have full historical rank data
-- Fix: Bootstrap 1w_ago, 4w_ago, 12w_ago with current_rank to allow system to start
-- Note: Real historical ranks will accumulate over time; this is temporary bootstrap

UPDATE sector_ranking
SET rank_1w_ago = COALESCE(rank_1w_ago, current_rank),
    rank_4w_ago = COALESCE(rank_4w_ago, current_rank),
    rank_12w_ago = COALESCE(rank_12w_ago, current_rank)
WHERE rank_1w_ago IS NULL OR rank_4w_ago IS NULL OR rank_12w_ago IS NULL;

-- ============================================================================
-- Verification
-- ============================================================================
-- SELECT COUNT(*) as trend_data_count FROM trend_template_data;
-- SELECT COUNT(*) as sector_rotation_count FROM sector_rotation_signal;
-- SELECT COUNT(*) as complete_sector_ranks FROM sector_ranking WHERE rank_12w_ago IS NOT NULL;
