-- Migration: Fix algo_trades.position_id FK to reference algo_positions.position_id
-- Date: 2026-07-13
-- Context: Session 114 - first-ever real end-to-end paper trade test (live Alpaca
--          credentials) revealed every single trade failed at the DB insert step.
--
-- Root cause: a prior fix (commit 0a35f8cc5, "Resolve schema type mismatch -
-- algo_trades.position_id VARCHAR to INTEGER") converted algo_trades.position_id to
-- INTEGER and pointed its FK at algo_positions.id (the INTEGER primary key), to fix a
-- FK type mismatch. But the application code generates a UUID string
-- (str(uuid.uuid4())) for position_id, and algo_positions already has its own
-- VARCHAR(100) position_id column with a unique constraint
-- (algo_positions_position_id_key) - the FK should have pointed there instead. The
-- INTEGER conversion made every trade insert fail with
-- "invalid input syntax for type integer: <uuid>".
--
-- This migration ensures algo_trades.position_id is VARCHAR(100) and repoints the FK
-- at algo_positions.position_id (VARCHAR, unique) instead of algo_positions.id
-- (INTEGER). It also makes the FK DEFERRABLE INITIALLY DEFERRED, since the trade row
-- and its linked position row are inserted in that order within the same transaction
-- (algo/trading/executor_entry_handler.py) - a non-deferred FK fails on the trade
-- insert before the position row exists, even though both commit together.
--
-- SESSION 124 FIX: the original version of this migration assumed
-- algo_trades.position_id already existed (true in local dev, where 0a35f8cc5's DDL
-- was run directly against the dev DB, bypassing the migration system entirely -- it
-- shipped no migration file). Production had never had that ad-hoc DDL applied, so the
-- column didn't exist there at all, and this migration failed outright with
-- "column position_id does not exist" the first time migrations/versions/ ever
-- actually ran end-to-end against production (2026-07-13, after the Terraform
-- provisioned-concurrency deploy blocker was fixed). Rewritten to handle all three
-- possible starting states -- column absent, column INTEGER, column already
-- VARCHAR(100) -- so it's correct regardless of which environment it runs against.

BEGIN;

ALTER TABLE algo_trades DROP CONSTRAINT IF EXISTS fk_trades_positions;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'algo_trades' AND column_name = 'position_id'
    ) THEN
        ALTER TABLE algo_trades ADD COLUMN position_id VARCHAR(100);
    ELSIF (
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'algo_trades' AND column_name = 'position_id'
    ) != 'character varying' THEN
        ALTER TABLE algo_trades
            ALTER COLUMN position_id TYPE VARCHAR(100) USING position_id::VARCHAR(100);
    END IF;
END $$;

ALTER TABLE algo_trades
    ADD CONSTRAINT fk_trades_positions
    FOREIGN KEY (position_id) REFERENCES algo_positions(position_id)
    DEFERRABLE INITIALLY DEFERRED;

COMMIT;
