-- Migration 1293: extend data_patrol_finding_acknowledgments (migration 1292) to the sibling
-- cross-sectional-outlier checks on quality_metrics/value_metrics that 1292 missed.
--
-- ADDED 2026-09-14 (same goal session, immediate follow-up). 1292 only acknowledged
-- roic_pct_cross_sectional_outlier/fcf_yield_cross_sectional_outlier (the two columns named
-- in the originally-pasted dashboard snapshot). Live-checking data_patrol_log after applying
-- 1292 showed quality_metrics and value_metrics still read active_findings, because the same
-- check module (score_ratio_outliers.py - "a single most-extreme raw value always wins
-- percentile-rank 100" cross-sectional design, identical docstring/SOAR-LX-ROC-MSB precedent
-- across every column it covers) also runs per-column for roe/roce_pct (quality_metrics) and
-- pe_ratio/pb_ratio/forward_pe/ev_ebitda/ev_revenue (value_metrics) - same design, same
-- reasoning, just not named in the user's pasted snapshot. Acknowledging all of them
-- consistently rather than leaving siblings of an already-reviewed check unacknowledged for
-- no principled reason.
INSERT INTO data_patrol_finding_acknowledgments (check_name, target_table, reason, acknowledged_by)
VALUES
    ('roe_cross_sectional_outlier', 'quality_metrics',
     'Same cross-sectional-outlier design as roic_pct_cross_sectional_outlier (migration 1292) - '
     'a single most-extreme raw roe value always wins percentile-rank 100 regardless of whether '
     'it is genuine or an extraction artifact - by-design review queue, not a bug.',
     'claude-session-20260914'),
    ('roce_pct_cross_sectional_outlier', 'quality_metrics',
     'Same cross-sectional-outlier design as roic_pct_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914'),
    ('pe_ratio_cross_sectional_outlier', 'value_metrics',
     'Same cross-sectional-outlier design as fcf_yield_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914'),
    ('pb_ratio_cross_sectional_outlier', 'value_metrics',
     'Same cross-sectional-outlier design as fcf_yield_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914'),
    ('forward_pe_cross_sectional_outlier', 'value_metrics',
     'Same cross-sectional-outlier design as fcf_yield_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914'),
    ('ev_ebitda_cross_sectional_outlier', 'value_metrics',
     'Same cross-sectional-outlier design as fcf_yield_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914'),
    ('ev_revenue_cross_sectional_outlier', 'value_metrics',
     'Same cross-sectional-outlier design as fcf_yield_cross_sectional_outlier (migration 1292) - '
     'by-design review queue, not a bug.', 'claude-session-20260914')
ON CONFLICT (check_name, target_table) DO NOTHING;
