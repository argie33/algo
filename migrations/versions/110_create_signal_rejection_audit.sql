-- Migration 110: Create audit table for signal rejections
-- Date: 2026-07-19
--
-- Track every signal rejection with full details for analysis and debugging.
--
-- REWRITTEN 2026-07-20: the original 110_create_signal_rejection_audit.py was written in
-- Alembic's `op`/`sa` style (upgrade()/downgrade()), but migrations/run.py's Python-migration
-- path only recognizes a plain `up()` function (see apply_migration()'s
-- `if not hasattr(migration_module, "up")` check) - this repo does not otherwise use Alembic
-- anywhere. Running it via the actual runner (`migrations/run.py apply 110` or `apply --all`)
-- would fail immediately with AttributeError, and since apply_all_pending() stops at the first
-- failure, this dead file was silently blocking every later-numbered pending migration from
-- ever being applied through the normal path. The table itself was already created directly
-- against the DB (confirmed 2026-07-20: schema matches this file exactly) - this migration is
-- rewritten as plain idempotent SQL, matching every other migration in this directory, so the
-- tracker can correctly record it as applied and a fresh database can actually run it.

BEGIN;

CREATE TABLE IF NOT EXISTS algo_signal_rejections (
    id SERIAL PRIMARY KEY,
    rejection_date DATE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    rejection_stage VARCHAR(50) NOT NULL,
    rejection_reason VARCHAR(200) NOT NULL,
    entry_price NUMERIC(10, 2),
    risk_pct NUMERIC(5, 2),
    stop_loss_pct NUMERIC(5, 2),
    signal_quality_score NUMERIC(5, 2),
    atr NUMERIC(8, 4),
    sma_50 NUMERIC(8, 2),
    market_exposure_pct NUMERIC(5, 2),
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_rejections_date_stage
    ON algo_signal_rejections (rejection_date, rejection_stage);

CREATE INDEX IF NOT EXISTS idx_signal_rejections_symbol
    ON algo_signal_rejections (symbol, rejection_date);

COMMIT;
