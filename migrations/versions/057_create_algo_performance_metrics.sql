-- Migration 057: Create algo_performance_metrics table
-- Pre-computed performance statistics computed nightly by compute_performance_metrics.py.

CREATE TABLE IF NOT EXISTS algo_performance_metrics (
    metric_date DATE PRIMARY KEY,
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    breakeven_trades INT,
    win_rate_pct DECIMAL(8, 2),
    profit_factor DECIMAL(8, 2),
    total_pnl_dollars DECIMAL(12, 2),
    total_pnl_pct DECIMAL(8, 2),
    avg_trade_pct DECIMAL(8, 2),
    best_trade_pct DECIMAL(8, 2),
    worst_trade_pct DECIMAL(8, 2),
    avg_holding_days DECIMAL(8, 2),
    sharpe_ratio DECIMAL(8, 4),
    sortino_ratio DECIMAL(8, 4),
    max_drawdown_pct DECIMAL(8, 4),
    calmar_ratio DECIMAL(8, 4),
    cagr_pct DECIMAL(8, 4),
    best_win_streak INT,
    worst_loss_streak INT,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_algo_performance_metrics_date ON algo_performance_metrics(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_algo_performance_metrics_win_rate ON algo_performance_metrics(win_rate_pct DESC);
