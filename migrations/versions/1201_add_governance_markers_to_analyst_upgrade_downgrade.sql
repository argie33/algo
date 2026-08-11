-- Migration 1201: Add data_unavailable/data_unavailable_reason governance markers to
-- analyst_upgrade_downgrade
--
-- ISSUE: same untracked-drift class as migrations 1181-1187 and 1200 (analyst_sentiment_
-- analysis, found+fixed in the same investigation pass). loaders/load_analyst_upgrade_
-- downgrade.py always upserts an explicit data_unavailable/data_unavailable_reason marker
-- for symbols with no analyst coverage rather than silently dropping the row (the standard
-- governance pattern used throughout this codebase's loaders) - analyst_upgrade_downgrade was
-- missing both columns. utils/bulk_insert_manager.py has an explicit fail-fast check for
-- exactly this case ("GOVERNANCE VIOLATION: ... governance marker columns do not exist on the
-- target table") rather than silently dropping the audit trail.

BEGIN;

ALTER TABLE analyst_upgrade_downgrade
    ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS data_unavailable_reason VARCHAR(500);

COMMIT;
