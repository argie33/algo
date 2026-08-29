-- Migration 1251: Drop orphaned altman_z_score columns from quality_metrics
-- Date: 2026-08-29 (goal session: "keep working through the data issues" full-data pass)

-- ROOT CAUSE: altman_z_score was added to quality_metrics by migration
-- 1237_add_altman_z_score_to_quality_metrics.sql (commit c568eccfe, 2026-08-26 - Quality
-- pillar literature audit, Fama-MacBeth t=3.49, "strongest component in the composite" at
-- the time) then cut from the scoring formula in a later same-week rebuild. `git grep -w
-- altman_z_score` across the entire repo (loaders, lambda/api, webapp/frontend, tests)
-- returns ZERO matches - no code reads OR writes this column anymore, on either side of
-- score computation or display.
--
-- The removal was recorded in memory as "[[quality_altman_z_score_removed_entirely_20260828]]
-- - REMOVED ENTIRELY, migration 1244 drops columns (SHIPPED with the 033e0d449 commit)" -
-- that claim is WRONG: migration 1244 in this repo's actual git history
-- (migrations/versions/1244_retire_size_score_from_stock_scores.sql, part of the same
-- 033e0d449 commit) is the SIZE-pillar retirement migration, unrelated to Altman Z - no
-- commit anywhere in `git log --all` ever drops these columns. The two "retire a factor"
-- stories from the same commit got conflated when that memory was written. Corrected in
-- memory this session (see [[inr_added_and_stale_raw_currency_cleanup_20260829]] for the
-- broader data-completeness pass this was found during).
--
-- Live-confirmed impact of leaving this undone: quality_metrics.altman_z_score_unavailable_reason
-- carried 1,916 rows of stale "missing_retained_earnings"/"missing_sec_data" noise from a
-- column nothing computes or reads anymore - actively muddying any future "what's really
-- missing for our scores" coverage audit (scripts/audit_unavailable_reasons.py) with a dead
-- factor's leftover gaps mixed in among live ones.

BEGIN;

ALTER TABLE quality_metrics DROP COLUMN IF EXISTS altman_z_score;
ALTER TABLE quality_metrics DROP COLUMN IF EXISTS altman_z_score_unavailable_reason;

COMMIT;
