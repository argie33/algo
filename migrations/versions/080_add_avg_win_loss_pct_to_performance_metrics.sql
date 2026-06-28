-- Migration 080: Add avg_win_pct and avg_loss_pct to algo_performance_metrics
-- The API was aliasing best_trade_pct/worst_trade_pct as avg_win_pct/avg_loss_pct,
-- which showed the single best/worst trade instead of the average across winners/losers.
-- These new columns store the true average P&L % for winning and losing trades separately.

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_win_pct'
    ) THEN
        ALTER TABLE algo_performance_metrics ADD COLUMN avg_win_pct NUMERIC(8, 2);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_loss_pct'
    ) THEN
        ALTER TABLE algo_performance_metrics ADD COLUMN avg_loss_pct NUMERIC(8, 2);
    END IF;
END $$;
