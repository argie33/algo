-- Migration 1229: Raise phase7_min_composite_score default from 50 to 60
--
-- 2026-08-24 exposure-tier selectivity pass raised EXPOSURE_TIERS.min_composite_score across
-- the board (50/60/70/80 -> 60/65/70/75, see algo/risk/exposure_policy.py's EXPOSURE_TIERS
-- comment) so the algo only trades higher-quality signals. phase7_min_composite_score is the
-- config-driven fallback used only if the regime-tier lookup itself fails
-- (algo/orchestrator/phase7_signal_generation.py) and was updated to 60 in
-- algo/infrastructure/config_schema.py's DEFAULTS/VALIDATION_SCHEMA and
-- algo/infrastructure/config/main.py the same day, with the live algo_config row updated
-- manually to match - but no migration file was ever committed for the algo_config change
-- itself (superseding migration 094's original default of 50). This backfills that gap so a
-- fresh environment's algo_config table matches config_schema.py's DEFAULTS without a manual
-- UPDATE. See MEMORY.md exposure_tier_min_composite_score_selectivity_raised_20260824.

UPDATE algo_config
SET value = '60',
    description = 'Minimum composite score (0-100) for a signal to qualify in Phase 7 signal generation',
    updated_by = 'migration-1229',
    updated_at = CURRENT_TIMESTAMP
WHERE key = 'phase7_min_composite_score'
  AND value IS DISTINCT FROM '60';
