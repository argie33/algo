-- ════════════════════════════════════════════════════════════════════════════
-- MIGRATION: 111_backfill_trade_duration_days
-- ════════════════════════════════════════════════════════════════════════════
--
-- PURPOSE: Backfill trade_duration_days for all closed trades
--
-- FIXES:
-- - Dashboard panel was failing with StrictValidationError when trade_duration_days was NULL
-- - Ensures all closed trades have trade_duration_days calculated as (exit_date - entry_date)
--
-- CREATED: 2026-07-03

UPDATE algo_trades
SET trade_duration_days = (exit_date - entry_date)::INTEGER
WHERE status = 'closed'
  AND exit_date IS NOT NULL
  AND entry_date IS NOT NULL
  AND trade_duration_days IS NULL;

COMMENT ON COLUMN algo_trades.trade_duration_days IS
'Number of days between entry_date and exit_date. Calculated at trade exit in TradeRecorder. Required for dashboard panels.';
