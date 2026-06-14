-- Migration 056: Create circuit_breaker_status table
-- Pre-computed metrics for trading circuit breakers, computed nightly after Phase 7.

CREATE TABLE IF NOT EXISTS circuit_breaker_status (
    check_date DATE PRIMARY KEY,
    portfolio_drawdown_pct DECIMAL(8, 2),
    daily_loss_pct DECIMAL(8, 2),
    weekly_loss_pct DECIMAL(8, 2),
    consecutive_losses INT,
    open_risk_pct DECIMAL(8, 2),
    vix_level DECIMAL(8, 2),
    market_stage INT,
    spy_prior_day_change_pct DECIMAL(8, 2),
    win_rate_last_30_pct DECIMAL(8, 2),
    triggered_count INT,
    any_triggered BOOLEAN,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_status_date ON circuit_breaker_status(check_date DESC);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_status_triggered ON circuit_breaker_status(any_triggered);
