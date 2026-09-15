-- Migration 1292: Create data_patrol_finding_acknowledgments.
--
-- ADDED 2026-09-14 (goal session: "lot of data issues finding" dashboard triage). Root cause
-- of the recurring "why does this still say Findings open" confusion: data_patrol_log.status
-- only has two states (`open`/`resolved` - see logger.py's own comment on that column), and
-- `resolved` only ever fires when a LATER RUN of the same (check_name, target_table) logs a
-- fresh row - PatrolLogger.log_results marks the prior 'open' row 'resolved' right before
-- inserting the new one. A WARN-severity review-queue check (analyst_sentiment_bounds,
-- roic_pct_cross_sectional_outlier, stability_metrics_bounds, fcf_yield_cross_sectional_outlier
-- - see each check module's own docstring) that keeps re-finding the SAME genuine outliers
-- every run therefore stays 'open' forever, even after a human has actually looked at it and
-- confirmed the flagged rows are real data, not a bug. There was no way to record "reviewed,
-- confirmed not a bug" as distinct from "nobody has looked at this yet" - both rendered
-- identically as "Findings open" on the correctness-coverage dashboard panel.
--
-- This is intentionally NOT a change to data_patrol_log.status itself (that column's
-- open/resolved semantics are load-bearing for "did a fresh run re-confirm this" elsewhere -
-- see logger.py) and NOT a per-row acknowledgment (a WARN check logs one aggregate row per
-- run, e.g. "3157 rows outside bounds", not one row per flagged symbol - acknowledging
-- "row N" would mean nothing next run when the aggregate count changes). Instead this mirrors
-- the existing xbrl_concept_coverage_dismissed.json pattern (CLAUDE.md) at the (check_name,
-- target_table) grain: a reviewer confirms this CHECK, for this TABLE, is a known/accepted
-- review-queue pattern (not that today's specific flagged rows are all fine forever) - the
-- check keeps running and logging every time, this just stops it from reading as an
-- unreviewed backlog item on the triage panel.
CREATE TABLE IF NOT EXISTS data_patrol_finding_acknowledgments (
    id SERIAL PRIMARY KEY,
    check_name VARCHAR(200) NOT NULL,
    target_table VARCHAR(200) NOT NULL,
    reason TEXT NOT NULL,
    acknowledged_by VARCHAR(200) NOT NULL DEFAULT 'unknown',
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (check_name, target_table)
);

CREATE INDEX IF NOT EXISTS idx_data_patrol_finding_acknowledgments_lookup
    ON data_patrol_finding_acknowledgments (check_name, target_table)
    WHERE active;

-- Seed the 4 checks independently confirmed this session (live DB re-verification, not just
-- taken from memory) as genuine data with no code fix warranted:
INSERT INTO data_patrol_finding_acknowledgments (check_name, target_table, reason, acknowledged_by)
VALUES
    ('analyst_sentiment_bounds', 'analyst_sentiment_analysis',
     'upside_downside_percent >500% rows are real crashing micro-caps with stale-but-unrevised '
     'analyst price targets, not an extraction bug - re-verified live 2026-09-14, matches prior '
     'dashboard_open_findings_audit_20260914d finding.', 'claude-session-20260914'),
    ('roic_pct_cross_sectional_outlier', 'quality_metrics',
     'A single most-extreme raw roic_pct value always wins percentile-rank 100 regardless of '
     'whether it is genuine deep-value/distress or an extraction artifact (see this check''s own '
     'module docstring, the SOAR/LX/ROC/MSB precedent) - by-design review queue, not a bug.',
     'claude-session-20260914'),
    ('stability_metrics_bounds', 'stability_metrics',
     'beta outside [-5, 8] rows are real weak-correlation names whose beta estimate saturates to '
     'the same floor/ceiling regardless of magnitude, not an extraction bug - re-verified live '
     '2026-09-14, matches prior dashboard_open_findings_audit_20260914d finding.',
     'claude-session-20260914'),
    ('fcf_yield_cross_sectional_outlier', 'value_metrics',
     'A single most-extreme raw fcf_yield value always wins percentile-rank 100 regardless of '
     'whether it is genuine deep-value/distress or an extraction artifact (see this check''s own '
     'module docstring, the SOAR/LX/ROC/MSB precedent) - by-design review queue, not a bug.',
     'claude-session-20260914')
ON CONFLICT (check_name, target_table) DO NOTHING;
