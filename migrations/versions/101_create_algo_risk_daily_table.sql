-- Migration 101: Create algo_risk_daily table for daily portfolio risk metrics
-- Description: Stores VaR, CVaR, stressed VaR, portfolio beta, and concentration metrics
-- Updated by: ValueAtRisk.generate_daily_risk_report() in Phase 9 reconciliation
-- API: _get_risk_metrics() in lambda/api/routes/algo_handlers/metrics.py
-- Created: 2026-06-28

CREATE TABLE IF NOT EXISTS algo_risk_daily (
    report_date DATE PRIMARY KEY,
    var_pct_95 NUMERIC(8, 2),          -- Value at Risk (95% confidence) as % of portfolio
    cvar_pct_95 NUMERIC(8, 2),         -- Conditional VaR (expected loss beyond VaR) as %
    stressed_var_pct NUMERIC(8, 2),    -- VaR using worst 12-month historical window
    portfolio_beta NUMERIC(8, 3),      -- Portfolio beta vs S&P 500 (systematic risk)
    top_5_concentration NUMERIC(8, 2), -- Top 5 holdings as % of portfolio
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_algo_risk_daily_report_date ON algo_risk_daily(report_date DESC);
