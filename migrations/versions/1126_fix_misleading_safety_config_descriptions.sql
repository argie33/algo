-- Migration 1126: Fix misleading algo_config descriptions on safety-critical keys
--
-- Found during a local-dev audit of "why does the health panel look fine but the
-- algo halts": algo_config.description strings for the earnings-blackout thresholds
-- still read "AGGRESSIVE RELAX" even though migration 033 already restored their
-- VALUES to the safe defaults (earnings_blackout_days_before=7, _after=3). Migration
-- 033's UPSERT only set value/updated_by/updated_at, never description, so the old
-- "relaxed" wording from whatever originally zeroed these out is still stuck on the
-- row - an operator reading algo_config sees a safe value paired with a description
-- that says the opposite, which is exactly the kind of self-contradicting signal this
-- audit was asked to find and fix.
--
-- block_days_before_earnings=0 ("RELAXED: Disable earnings block") is a SEPARATE,
-- similarly-named key belonging to the disabled algo/signals/advanced_filters.py
-- module (enable_advanced_filters=false) - NOT the live earnings-blackout gate, which
-- is algo/risk/earnings_blackout.py reading earnings_blackout_days_before/_after and
-- is wired into Phase 8 via algo/trading/pretrade_checks.py. Left as-is functionally
-- (advanced_filters is intentionally disabled in favor of the 5-tier pipeline), but
-- the description is clarified so it isn't mistaken for the live blackout gate.

BEGIN;

UPDATE algo_config
SET description = 'Days before earnings to block new entries (restored to safe default by migration 033; live gate is algo/risk/earnings_blackout.py via Phase 8 pretrade_checks)',
    updated_by = 'migration-1126',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'earnings_blackout_days_before' AND description = 'AGGRESSIVE RELAX';

UPDATE algo_config
SET description = 'Days after earnings to block new entries (restored to safe default by migration 033; live gate is algo/risk/earnings_blackout.py via Phase 8 pretrade_checks)',
    updated_by = 'migration-1126',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'earnings_blackout_days_after' AND description = 'AGGRESSIVE RELAX';

UPDATE algo_config
SET description = 'Inert: belongs to algo/signals/advanced_filters.py, which is disabled (see enable_advanced_filters=false). Does NOT affect the live earnings-blackout gate (earnings_blackout_days_before/_after, enforced in algo/risk/earnings_blackout.py via Phase 8).',
    updated_by = 'migration-1126',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'block_days_before_earnings' AND description = 'RELAXED: Disable earnings block';

COMMIT;
