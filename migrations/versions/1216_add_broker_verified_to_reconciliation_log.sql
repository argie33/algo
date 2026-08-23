-- Migration 1216: Add broker_verified to algo_reconciliation_log
--
-- Goal (2026-08-22/23, "before real money" finance-accuracy audit): algo/infrastructure/
-- reconciliation.py::check_partial_fills() returns {"mismatches": 0, "no_broker": True}
-- unconditionally in paper-trading mode (no broker to check against) - a real, deliberate
-- code path, already commented in that file and in
-- algo/orchestrator/phase4_reconciliation.py as "The 0 mismatches means 'not checked', not
-- 'checked and clean'". But algo_reconciliation_log only ever persisted match_percentage/
-- sync_count, both of which come out to a vacuous 100.00/positions_count in that exact case
-- (0 mismatches / N positions = 100%) - indistinguishable in the stored row, and in the
-- /api/algo/health "phase_4_broker_reconciliation.avg_match_pct" field it feeds, from a
-- genuine broker-verified 100% match. An operator (or a future live-trading session)
-- reading "Broker Reconciliation: 100% avg match" on the health dashboard during local
-- paper-mode dev has no way to tell "verified against Alpaca, positions match exactly"
-- apart from "no broker was available, so nothing was actually compared". This is exactly
-- the kind of silently-vacuous-looking-clean signal the "no cheats or bypasses" governance
-- principle exists to catch before real capital is on the line.
--
-- broker_verified=TRUE means check_partial_fills() actually reached the broker (whether or
-- not it found any closed orders to check); FALSE means no_broker=True (paper mode, nothing
-- was compared). NULL means a pre-migration row (unknown - the distinction wasn't tracked
-- yet). The auth_unavailable case never reaches this INSERT at all (phase4_reconciliation.py
-- fails fast on it before the audit-log write), so it never needs to be represented here.

ALTER TABLE algo_reconciliation_log ADD COLUMN IF NOT EXISTS broker_verified BOOLEAN;

COMMENT ON COLUMN algo_reconciliation_log.broker_verified IS
    'TRUE if this reconciliation actually checked against the broker (Alpaca) - FALSE if no broker was available (paper-trading mode) and match_percentage is a vacuous 100% rather than a real verified match. NULL for pre-migration rows (not tracked).';
