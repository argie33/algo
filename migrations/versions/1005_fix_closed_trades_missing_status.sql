-- Migration 1005: Fix algo_trades rows with exit recorded but status not updated
-- Root cause: Phase 9 reconciliation (algo/orchestrator/phase9_reconciliation.py) set
-- exit_date/exit_price/profit_loss on exit but never set status = 'closed' in the same
-- UPDATE, leaving trades that are actually closed still showing an open-ish status
-- (open/accepted/pending_new) in the dashboard. Code fixed alongside this migration;
-- this backfills rows already corrupted by the bug.

UPDATE algo_trades
SET status = 'closed'
WHERE exit_date IS NOT NULL
  AND status != 'closed';
