-- Migration 113: Fix perf_anl schema - add missing R-metrics columns
-- Purpose: Ensure algo_performance_metrics has all required columns for perf_anl API endpoint
-- Reason: AWS RDS missing avg_win_r, avg_loss_r, expectancy columns that were added in migration 108

DO $$ BEGIN
    -- Verify the table exists first
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'algo_performance_metrics') THEN
        -- Add avg_win_r column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_win_r'
        ) THEN
            ALTER TABLE algo_performance_metrics ADD COLUMN avg_win_r NUMERIC(8, 4);
            RAISE NOTICE 'Added column avg_win_r to algo_performance_metrics';
        END IF;

        -- Add avg_loss_r column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'algo_performance_metrics' AND column_name = 'avg_loss_r'
        ) THEN
            ALTER TABLE algo_performance_metrics ADD COLUMN avg_loss_r NUMERIC(8, 4);
            RAISE NOTICE 'Added column avg_loss_r to algo_performance_metrics';
        END IF;

        -- Add expectancy column if missing
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'algo_performance_metrics' AND column_name = 'expectancy'
        ) THEN
            ALTER TABLE algo_performance_metrics ADD COLUMN expectancy NUMERIC(8, 4);
            RAISE NOTICE 'Added column expectancy to algo_performance_metrics';
        END IF;
    ELSE
        RAISE NOTICE 'algo_performance_metrics table does not exist - skipping R-metrics column additions';
    END IF;
END $$;

-- Log migration completion
INSERT INTO schema_migrations (version, description, installed_on)
VALUES ('113', 'Add R-metrics columns to algo_performance_metrics and fix perf_anl schema', NOW())
ON CONFLICT (version) DO NOTHING;
