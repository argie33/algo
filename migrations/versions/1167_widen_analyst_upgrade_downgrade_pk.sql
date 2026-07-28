-- Migration 1167: Add a real uniqueness constraint to analyst_upgrade_downgrade
--
-- ROOT CAUSE: analyst_upgrade_downgrade's only historical writer (load_yfinance_snapshot.py)
-- was deleted in Session 275 and never replaced - the table had no live writer since. A new
-- loader (load_analyst_upgrade_downgrade.py) restores this using yfinance's
-- Ticker.upgrades_downgrades data (same "no free official feed exists, this unofficial-but-real
-- source is the accepted tradeoff" pattern already used for put_call_ratio - see
-- steering/DATA_LOADERS.md).
--
-- The live table (created from an older version of lambda/db-init/schema.sql before someone
-- edited the CREATE TABLE statement without a migration to carry existing databases forward)
-- has PRIMARY KEY (id) only - no uniqueness constraint at all on (symbol, action_date, firm).
-- Real data confirms multiple firms commonly issue ratings for the same symbol on the same
-- calendar date (e.g. during earnings season) - without this constraint the loader has no
-- idempotent way to upsert (ON CONFLICT needs a matching unique constraint/index to target).
--
-- NOTE: utils/bulk_insert_manager.py's BulkInsertManager._ensure_unique_constraint() will
-- auto-create this same constraint at runtime on first use if it's missing (a self-healing
-- fallback for exactly this situation) - this migration exists anyway to match this codebase's
-- established convention of explicit, versioned, reviewable schema changes (see migrations
-- 1150/1157/1159/1131 for the same table-lifecycle pattern) rather than relying on an implicit
-- runtime side effect as the only record of the change.

-- Postgres has no "ADD CONSTRAINT IF NOT EXISTS" - guard explicitly so this is safe to run
-- even if BulkInsertManager's runtime self-healing (see note above) already created an
-- equivalent constraint under a different auto-generated name first.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'analyst_upgrade_downgrade'
          AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
        GROUP BY tc.constraint_name
        HAVING array_agg(kcu.column_name ORDER BY kcu.column_name) = ARRAY['action_date', 'firm', 'symbol']
    ) THEN
        ALTER TABLE analyst_upgrade_downgrade
            ADD CONSTRAINT analyst_upgrade_downgrade_symbol_date_firm_key
            UNIQUE (symbol, action_date, firm);
    END IF;
END $$;

COMMIT;
