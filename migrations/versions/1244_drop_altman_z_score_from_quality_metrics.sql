-- Migration 1244: Drop altman_z_score from quality_metrics.
--
-- Removed entirely 2026-08-28 (user directive). Already stopped feeding quality_score's
-- composite on 2026-08-26 (methodological objection: the Z''-Score's literature frames it as a
-- discrete distress-triage classifier, not a continuously-scaled magnitude input meant to be
-- averaged alongside ROA/ROE/margin ratios - see migration 1237 and
-- loaders/load_value_quality_growth_metrics.py git history for the full evidence trail), but the
-- raw value was still being computed and persisted here for reference. That's gone too now -
-- computation, persistence, and the frontend display (already removed 2026-08-26,
-- StockScoreAccordion.jsx) are all retired together. retained_earnings itself
-- (annual_balance_sheet, migration 1234) is untouched - it has no other consumer in this repo,
-- but dropping a shared upstream column is out of scope for a quality_metrics cleanup.

ALTER TABLE quality_metrics
DROP COLUMN IF EXISTS altman_z_score;

ALTER TABLE quality_metrics
DROP COLUMN IF EXISTS altman_z_score_unavailable_reason;
