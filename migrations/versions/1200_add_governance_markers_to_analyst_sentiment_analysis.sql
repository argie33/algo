-- Migration 1200: Add data_unavailable/data_unavailable_reason governance markers to
-- analyst_sentiment_analysis
--
-- ISSUE: same untracked-drift class as migrations 1181-1187. loaders/load_analyst_sentiment_
-- analysis.py always upserts an explicit data_unavailable/data_unavailable_reason marker for
-- symbols with no analyst coverage rather than silently dropping the row (the standard
-- governance pattern used throughout this codebase's loaders) - analyst_sentiment_analysis was
-- missing both columns. utils/bulk_insert_manager.py has an explicit fail-fast check for
-- exactly this case ("GOVERNANCE VIOLATION: ... governance marker columns do not exist on the
-- target table") rather than silently dropping the audit trail - live-reproduced: a local dev
-- database missing these columns failed 100% of symbols (1093/1093) on analyst_sentiment_
-- analysis with that exact error, blocking the entire load.

BEGIN;

ALTER TABLE analyst_sentiment_analysis
    ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(500);

COMMIT;
