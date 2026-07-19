-- Session 282: Add NOT NULL constraints for critical fields
-- Enforces at database level what was validated at application level

-- CRITICAL: Positions must have stop prices (prevents exit failures)
-- Session 281 audit found NULL stop prices block all stop-based exit strategies
ALTER TABLE algo_positions
  ALTER COLUMN current_stop_price SET NOT NULL;

-- Positions should always track how many target levels have been hit
-- Session 281 found NULL target_levels_hit prevents target-based exits
-- Note: Some old positions may have NULL - backfill with 0 first
UPDATE algo_positions
  SET target_levels_hit = 0
  WHERE target_levels_hit IS NULL;

ALTER TABLE algo_positions
  ALTER COLUMN target_levels_hit SET NOT NULL;

-- Database integrity: entry_price should never be NULL (needed for P&L calculations)
ALTER TABLE algo_positions
  ALTER COLUMN entry_price SET NOT NULL;

-- Database integrity: entry_date should never be NULL (audit trail)
ALTER TABLE algo_positions
  ALTER COLUMN entry_date SET NOT NULL;

-- Database integrity: stop_loss_price should never be NULL
ALTER TABLE algo_positions
  ALTER COLUMN stop_loss_price SET NOT NULL;

-- Trades: entry_quantity should never be NULL (used in position sizing)
UPDATE algo_trades
  SET entry_quantity = 0
  WHERE entry_quantity IS NULL AND status != 'cancelled';

ALTER TABLE algo_trades
  ALTER COLUMN entry_quantity SET NOT NULL;
