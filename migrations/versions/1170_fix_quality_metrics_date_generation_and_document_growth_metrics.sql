-- Migration 1170: Fix quality_metrics.date's generation expression + formally track
-- growth_metrics.date, neither of which was ever recorded in a migration file.
--
-- Bug found live 2026-07-28: quality_metrics.date is GENERATED ALWAYS AS
-- ((created_at)::date) STORED, unlike its sibling tables growth_metrics.date and
-- value_metrics.date, both of which correctly use (updated_at)::date (see migration
-- 1148, whose own comment says it exists specifically to make value_metrics "match
-- growth_metrics pattern"). created_at is set once at INSERT and is never touched by
-- this loader's ON CONFLICT DO UPDATE (see loaders/load_value_quality_growth_metrics.py
-- _insert_quality_metrics), so quality_metrics.date is permanently frozen at each row's
-- original creation date - it can never reflect a real data refresh again, no matter how
-- many times the loader successfully re-upserts fresh ROE/margin/debt values into that
-- row. Confirmed live: quality_metrics.updated_at for most symbols is 2026-07-27 (loader
-- ran and succeeded), but quality_metrics.date for those same rows is still 2026-07-24 or
-- earlier - which is exactly why scripts/monitor_data_staleness.py (which reads date/
-- created_at-derived age for this table) reported quality_metrics as 💀 DEAD (2.7 days)
-- while the sibling growth_metrics/value_metrics tables, written by the identical loader
-- in the identical run, correctly showed FRESH. This is not a one-time incident - it is
-- permanent, structural, and gets worse every day until fixed, since the column can
-- never self-correct.
--
-- Separately: neither quality_metrics.date nor growth_metrics.date's GENERATED column
-- definition exists in any tracked migration (only value_metrics's does, via 1148) even
-- though both are live in the database today. That is undocumented schema drift - a
-- fresh database built from migrations/run.py would not reproduce either column. This
-- migration both fixes the wrong expression on quality_metrics and brings both
-- definitions under migration tracking so schema is reproducible again.

BEGIN;

-- Fix quality_metrics: drop the wrong created_at-based generated column, recreate from
-- updated_at to match growth_metrics/value_metrics. No CASCADE: verified live (dry-run,
-- rolled back) that nothing depends on this specific column - the one dependent object,
-- the stock_fundamentals view, joins quality_metrics/growth_metrics but only references
-- named non-date columns (qm.roe, qm.roa, gm.revenue_growth_1y, etc), never qm.date/
-- gm.date, so a plain DROP COLUMN succeeds without touching it.
ALTER TABLE quality_metrics DROP COLUMN date;
ALTER TABLE quality_metrics ADD COLUMN date DATE GENERATED ALWAYS AS (CAST(updated_at AS DATE)) STORED;

-- Document growth_metrics.date's existing (correct) definition under migration tracking.
-- No-op in effect (same expression before/after); DROP+ADD keeps behavior identical to
-- today's live column while making it reproducible from migrations.
ALTER TABLE growth_metrics DROP COLUMN IF EXISTS date;
ALTER TABLE growth_metrics ADD COLUMN date DATE GENERATED ALWAYS AS (CAST(updated_at AS DATE)) STORED;

COMMIT;

-- After this migration, quality_metrics.date will track updated_at like its siblings,
-- so monitor_data_staleness.py and any other consumer of quality_metrics.date will
-- correctly reflect actual data freshness going forward.
