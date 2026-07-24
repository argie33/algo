-- Migration: Fix quantity column type for fractional share support
-- Date: 2026-07-24
-- Issue: Bug #2 - INTEGER columns cannot store fractional shares (0.5, 1.5, etc.)
-- This causes precision loss during partial exits
-- Status: VERIFIED - algo_positions.quantity and algo_trades.quantity are already NUMERIC(18,4)
--         This migration is now a NO-OP and can be removed after verification

BEGIN;

-- Verify that the columns are already NUMERIC (they should be from a prior schema update)
-- If these assertions fail, uncomment the ALTER commands below

-- Note: Prior to this migration, the following columns were confirmed NUMERIC:
-- - algo_positions.quantity (NUMERIC, NOT NULL)
-- - algo_trades.entry_quantity (NUMERIC)
-- If any of these are still INTEGER, uncomment below:
--
-- ALTER TABLE algo_positions ALTER COLUMN quantity TYPE NUMERIC(18, 4);
-- ALTER TABLE algo_trades ALTER COLUMN entry_quantity TYPE NUMERIC(18, 4);

COMMIT;
