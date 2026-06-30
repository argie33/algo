-- Migration 108: Add avg_win_r, avg_loss_r, and expectancy columns to algo_performance_metrics
-- Required metrics for expectancy calculation and performance analysis
-- Aligns with compute_performance_metrics.py which now calculates these metrics

DO $$ BEGIN
    -- Add columns to algo_performance_metrics if they don't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_win_r'
    ) THEN
        ALTER TABLE algo_performance_metrics ADD COLUMN avg_win_r NUMERIC(8, 4);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_loss_r'
    ) THEN
        ALTER TABLE algo_performance_metrics ADD COLUMN avg_loss_r NUMERIC(8, 4);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_performance_metrics' AND column_name = 'expectancy'
    ) THEN
        ALTER TABLE algo_performance_metrics ADD COLUMN expectancy NUMERIC(8, 4);
    END IF;
END $$;
