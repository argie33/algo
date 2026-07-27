-- Migration 1162: Seed reentry_cooldown_minutes into algo_config
--
-- ISSUE: algo/trading/pretrade_checks.py's flip-flop-prevention check (blocks re-entering
-- a symbol within N minutes of it being closed) has required an explicit
-- reentry_cooldown_minutes config value with no silent fallback since it was written -
-- but no migration or config_schema.py/config/main.py entry ever seeded it. Confirmed live
-- 2026-07-27: a forced local orchestrator re-run hit this exact path for OHI (a symbol
-- closed minutes earlier the same run) and crashed Phase 8 entry execution with
-- "[PRE-TRADE CRITICAL] reentry_cooldown_minutes config missing" - this is a universal gap
-- (the key has never existed in any environment's algo_config), not local-dev-only, so any
-- production re-entry attempt within the same session as a prior close would hit it too.
--
-- Distinct from the existing min_days_before_reentry_same_symbol (a days-scale reset
-- period after a stop-out, enforced in trade_validator.py) - this is a much shorter
-- minutes-scale cooldown guarding against same-run whipsaw re-entries. Seeded at 30
-- minutes per the check's own recommended-range comment ("recommended: 30-60 minutes").

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('reentry_cooldown_minutes', '30', 'int',
        'Minutes to wait after a position closes before re-entering the same symbol (flip-flop prevention)',
        'migration-1162')
ON CONFLICT (key) DO UPDATE
    SET value = '30',
        description = 'Minutes to wait after a position closes before re-entering the same symbol (flip-flop prevention)',
        updated_by = 'migration-1162',
        updated_at = CURRENT_TIMESTAMP;
