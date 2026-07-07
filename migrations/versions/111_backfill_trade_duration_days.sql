-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 111_backfill_trade_duration_days
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Backfill trade_duration_days for all closed trades
--
-- FIXES:
-- - Dashboard panel was failing with StrictValidationError when trade_duration_days was NULL
-- - Ensures all closed trades have trade_duration_days calculated as (exit_time - entry_time)
--
-- CREATED: 2026-07-03

DO $$
BEGIN
    -- Only run if both columns and the table exist
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'algo_trades'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'algo_trades' AND column_name = 'entry_time'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'algo_trades' AND column_name = 'exit_time'
    ) THEN
        UPDATE algo_trades
        SET trade_duration_days = EXTRACT(DAY FROM (exit_time - entry_time))::INTEGER
        WHERE status = 'closed'
          AND exit_time IS NOT NULL
          AND entry_time IS NOT NULL
          AND trade_duration_days IS NULL;
    END IF;
END $$;

-- Add comment if table exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'algo_trades'
    ) THEN
        COMMENT ON COLUMN algo_trades.trade_duration_days IS
        'Number of days between entry_time and exit_time. Calculated at trade exit in TradeRecorder. Required for dashboard panels.';
    END IF;
END $$;
