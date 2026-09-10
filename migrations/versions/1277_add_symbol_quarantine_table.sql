-- Migration 1277: Add symbol_quarantine table - per-symbol quarantine for DataPatrol
-- findings that are isolable to specific symbols (goal session 2026-09-10: "identify bad
-- data, quarantine it, triage/fix, verify - like a real institution would").
--
-- Named `symbol_quarantine`, not `data_quality_flags`, to avoid any confusion with the
-- unrelated, already-fixed 2026-08-11 bug (see
-- tests/unit/test_data_patrol_no_write_side_effect_in_ohlc_check.py) where QualityChecker's
-- identical-OHLC check used to silently write to a `price_daily.data_quality_flags` column -
-- that column no longer exists; this is a new, separate top-level table.
--
-- Audit finding: DataPatrol's CRIT/ERROR severities are already thoughtfully tiered - most
-- per-symbol review-queue checks (price_sanity, statistical_anomaly, tie_out, xbrl gaps) are
-- deliberately WARN-only per their own docstrings, so they never halt Phase 1. The genuine
-- CRIT/ERROR checks (staleness, ohlc_sanity) are correctly table-wide systemic conditions
-- EXCEPT ohlc_sanity's negative-price/bad-high-low case: that's real per-row data corruption
-- (e.g. one bad tick from a feed) reported only as an aggregate count, which halts the
-- *entire* pipeline for the whole universe over what is often a handful of instruments.
--
-- This table lets a check identify the specific symbols responsible for a CRIT/ERROR finding
-- so Phase 1 (_check_data_patrol_results) can quarantine just those symbols - excluding them
-- from scoring/trading via the existing data_unavailable convention - and let the rest of the
-- universe proceed, instead of an all-or-nothing halt. Any check that does NOT report specific
-- symbols still halts the whole pipeline as before (fail-safe default, unchanged).
--
-- Lifecycle mirrors data_patrol_log's supersede-on-reinsert pattern (migration/commit
-- 2026-09-09): a symbol's flag for a given check_name is resolved automatically once that
-- check no longer reports it, rather than requiring a manual clear.

CREATE TABLE IF NOT EXISTS symbol_quarantine (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('error', 'critical')),
    reason TEXT NOT NULL,
    patrol_run_id VARCHAR(100) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_symbol_quarantine_symbol_open
    ON symbol_quarantine(symbol) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_symbol_quarantine_check_open
    ON symbol_quarantine(check_name) WHERE resolved_at IS NULL;
