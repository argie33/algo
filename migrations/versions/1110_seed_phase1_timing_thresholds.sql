-- Migration 1110: Seed phase1_recent_cutoff_days / phase1_prior_cutoff_days /
-- phase1_halt_table_max_tolerance_days into algo_config
--
-- ISSUE: Commit e5d995361 ("eliminate configuration fallback anti-patterns") correctly
-- removed the silent config.get(key, <default>) fallbacks for these three Phase 1
-- staleness-tolerance keys per GOVERNANCE.md's no-silent-fallbacks rule, but never added
-- a migration to seed the now-required rows into algo_config. Since that commit deployed,
-- Phase 1 has raised "Config missing required timing thresholds" and halted on every
-- single production orchestrator run (confirmed live via CloudWatch
-- /aws/lambda/algo-algo-dev, runs at 20:39, 21:12, 21:19 UTC on 2026-07-13), which cascades
-- into Phase 3/6 being skipped and blocks live paper trading entirely.
--
-- Seeds the exact values the removed .get() fallback used, so behavior is unchanged from
-- before the fallback-elimination commit -- only the missing-config crash is fixed.

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('phase1_recent_cutoff_days', '2', 'int',
        'Phase 1: lookback window (days) for "recent" symbol coverage count',
        'migration-1110')
ON CONFLICT (key) DO UPDATE
    SET value = '2',
        description = 'Phase 1: lookback window (days) for "recent" symbol coverage count',
        updated_by = 'migration-1110',
        updated_at = CURRENT_TIMESTAMP;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('phase1_prior_cutoff_days', '2', 'int',
        'Phase 1: additional lookback window (days) for the prior-period coverage baseline',
        'migration-1110')
ON CONFLICT (key) DO UPDATE
    SET value = '2',
        description = 'Phase 1: additional lookback window (days) for the prior-period coverage baseline',
        updated_by = 'migration-1110',
        updated_at = CURRENT_TIMESTAMP;

INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES ('phase1_halt_table_max_tolerance_days', '1', 'int',
        'Phase 1: max days a halt-critical table (price_daily, market_health_daily, market_exposure_daily) may lag before halting',
        'migration-1110')
ON CONFLICT (key) DO UPDATE
    SET value = '1',
        description = 'Phase 1: max days a halt-critical table (price_daily, market_health_daily, market_exposure_daily) may lag before halting',
        updated_by = 'migration-1110',
        updated_at = CURRENT_TIMESTAMP;
