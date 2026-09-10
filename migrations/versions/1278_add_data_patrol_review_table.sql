-- Migration 1278: Add data_patrol_review table - human triage/ack workflow for
-- data_patrol_log's open backlog (goal session 2026-09-10, follow-up to migration 1277's
-- symbol_quarantine: "identify bad data, quarantine it, triage/fix the issues, verify clean").
--
-- Audit finding: 2026-09-09's supersede-on-reinsert fix (data_patrol_log.status) made "open"
-- mean "still true as of the latest run" instead of an ever-growing unfiltered feed - real
-- progress, but it still can't distinguish "nobody has ever looked at this" from "a human
-- reviewed this and it's a known/accepted condition (e.g. inherent XBRL source-data rounding
-- noise, a real M&A-driven YoY swing, sparse-by-design buy_sell_daily coverage)" - every open
-- finding looks equally urgent to a report or a dashboard. That's the actual triage gap: not
-- "we don't detect enough," but "we can't tell what's already been triaged."
--
-- Keyed on (check_name, target_table) - same granularity data_patrol_log itself already
-- groups on - so one review covers a check/table pair across every run that reproduces it,
-- the same way PatrolLogger's supersede-on-reinsert already treats that pair as one logical
-- finding over time. A reviewed pair whose finding's own text changes materially (e.g. a
-- symbol count that jumps by 5x) is still worth a human's attention despite being
-- "reviewed" - see scripts/data_patrol_backlog_report.py's --unreviewed-only flag design,
-- which surfaces exactly the never-triaged and expired-review subset.

CREATE TABLE IF NOT EXISTS data_patrol_review (
    id SERIAL PRIMARY KEY,
    check_name VARCHAR(100) NOT NULL,
    target_table VARCHAR(100),
    status VARCHAR(20) NOT NULL CHECK (status IN ('acceptable', 'needs_fix')),
    note TEXT NOT NULL,
    reviewed_by VARCHAR(200),
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (check_name, target_table)
);
CREATE INDEX IF NOT EXISTS idx_data_patrol_review_check_table
    ON data_patrol_review(check_name, target_table);
