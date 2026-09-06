-- Migration 1260: Create algo_risk_monitor_state for the unified intraday risk monitor's
-- debounce state.
--
-- PROBLEM:
-- algo/risk/unified_risk_monitor.py (real-money-readiness consolidation, 2026-09-06) must
-- require a breach to be re-confirmed against fresh live data on 2 consecutive 5-minute
-- runs before taking any automated action (halt, then reduce/flatten if the breach
-- persists past the halt) - a single noisy tick, stale beta row, or transient API hiccup
-- must not trigger a real trade. That requires persisting, per check type, how many
-- consecutive runs have seen a breach - state that must survive across Lambda invocations
-- (each invocation is a fresh process), so it cannot live in memory.
--
-- SOLUTION:
-- One row per check_key (e.g. 'variance', 'beta', 'concentration', 'market_health'),
-- tracking the current consecutive-breach streak and enough context to reconstruct the
-- decision sequence after the fact.

BEGIN;

CREATE TABLE algo_risk_monitor_state (
    check_key TEXT PRIMARY KEY,
    consecutive_breach_count INTEGER NOT NULL DEFAULT 0,
    last_breached BOOLEAN NOT NULL DEFAULT FALSE,
    last_action TEXT,
    last_result_json TEXT,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE algo_risk_monitor_state IS
    'Debounce/escalation state for algo/risk/unified_risk_monitor.py - one row per check '
    'type, tracking consecutive-breach streaks so a single noisy reading never triggers an '
    'automated halt or position reduction.';

COMMIT;
