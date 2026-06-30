-- Migration 107: Restore and expand algo_performance_daily table with performance metrics
-- Pre-computed daily performance metrics including Sharpe, win rate, expectancy, and other key metrics
-- Referenced by the performance API and computed by algo/reporting/performance.py
-- Replaces deprecated separate daily performance tracking with consolidated metrics table

CREATE TABLE IF NOT EXISTS algo_performance_daily (
    report_date DATE PRIMARY KEY,

    -- Trade counts and rates
    total_trades INT DEFAULT 0,
    num_wins INT DEFAULT 0,
    num_losses INT DEFAULT 0,

    -- Profitability metrics
    gross_win_dollars DECIMAL(12, 2),
    gross_loss_dollars DECIMAL(12, 2),
    total_pnl_dollars DECIMAL(12, 2),
    profit_factor DECIMAL(8, 4),

    -- Average trade metrics
    avg_win DECIMAL(12, 2),
    avg_loss DECIMAL(12, 2),
    avg_win_pct DECIMAL(8, 4),
    avg_loss_pct DECIMAL(8, 4),

    -- R-multiple metrics (average win R, average loss R, expectancy)
    avg_r DECIMAL(8, 4),
    avg_w_r DECIMAL(8, 4),                  -- Average R-multiple on winning trades
    avg_l_r DECIMAL(8, 4),                  -- Average R-multiple on losing trades (as positive value)
    expectancy DECIMAL(8, 4),                -- Expectancy = (WR × Avg Win R) - (LR × Avg Loss R)

    -- Position metrics
    avg_hold_days DECIMAL(8, 2),

    -- Risk metrics
    rolling_sharpe_252d DECIMAL(8, 4),
    rolling_sortino_252d DECIMAL(8, 4),
    calmar_ratio DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),

    -- Trade quality
    win_rate_50t DECIMAL(8, 2),
    avg_win_r_50t DECIMAL(8, 4),             -- Last 50 trades average win R
    avg_loss_r_50t DECIMAL(8, 4),            -- Last 50 trades average loss R

    -- Best/worst trades
    biggest_win DECIMAL(12, 2),
    biggest_loss DECIMAL(12, 2),
    best_trade_r DECIMAL(8, 4),
    worst_trade_r DECIMAL(8, 4),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_algo_performance_daily_date ON algo_performance_daily(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_performance_daily_sharpe ON algo_performance_daily(rolling_sharpe_252d DESC);
