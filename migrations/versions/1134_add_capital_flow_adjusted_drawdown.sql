-- Migration 1134: Cash-flow-adjusted drawdown (fixes circuit breaker false-halt)
-- Date: 2026-07-20
--
-- ROOT CAUSE (Session 314 audit): The drawdown circuit breaker
-- (algo/risk/circuit_breaker.py::_check_drawdown) computes peak/drawdown from raw
-- total_portfolio_value, which is Alpaca's live account equity. That number moves for
-- TWO different reasons that the code never distinguished:
--   1. Trading performance (the thing a drawdown circuit breaker should measure)
--   2. External capital flows - the user depositing or withdrawing real money
--
-- algo_portfolio_snapshots shows 3 overnight equity drops with ZERO open positions and
-- ZERO trades/audit-log entries around them - impossible to produce via trading:
--   2024-06-11: -$11,522.46 (106,446.98 -> 94,924.52)
--   2024-07-16: -$9,969.92  (102,766.71 -> 92,796.79)
--   2025-11-18: -$20,554.24 (95,871.09 -> 75,316.85)  <- user-confirmed real withdrawal
-- Since the account was 100% cash with 0 positions at every one of these points, the
-- ENTIRE delta is the withdrawal (no ambiguity from mixed trading activity).
--
-- The circuit breaker's peak (all-time MAX(total_portfolio_value) = $106,914.68 from
-- 2024-06-06, pre-dating the first withdrawal) was therefore being compared against a
-- current equity that had since had ~$42k of real withdrawals baked in, producing a
-- reported 32.63% drawdown and halting EVERY orchestrator run for 8+ months. Recomputed
-- with capital flows backed out, the strategy's actual peak-to-current drawdown is ~5%
-- and its worst historical drawdown was ~7.3% (2025-04-09) - both comfortably under the
-- 20% halt threshold. With 0 open positions and trading halted, the raw-dollar drawdown
-- could never self-correct: no trading was permitted, so equity could never earn its way
-- back to within 8% of a peak that no longer reflected invested capital. Permanent
-- deadlock, not a real risk event.
--
-- FIX: track external capital flows explicitly (auditable ledger, not a threshold
-- tweak) and compute a parallel "adjusted" equity curve that adds back cumulative net
-- withdrawals (or subtracts cumulative net deposits) so peak/drawdown reflect trading
-- performance only. Raw total_portfolio_value / running_peak / drawdown_pct are left
-- untouched (still the real dollar history); circuit_breaker.py is updated separately
-- to read the new adjusted_* columns instead.

BEGIN;

CREATE TABLE IF NOT EXISTS algo_capital_flows (
    id SERIAL PRIMARY KEY,
    flow_date DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,  -- positive = deposit (inflow), negative = withdrawal (outflow)
    flow_type VARCHAR(20) NOT NULL CHECK (flow_type IN ('deposit', 'withdrawal')),
    source VARCHAR(50) NOT NULL DEFAULT 'manual',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_algo_capital_flows_date ON algo_capital_flows(flow_date);

INSERT INTO algo_capital_flows (flow_date, amount, flow_type, source, notes)
VALUES
    ('2024-06-11', -11522.46, 'withdrawal', 'inferred_from_snapshot_gap_session314',
     'Overnight equity drop with 0 open positions, 0 trades, 0 audit-log entries (106,446.98 -> 94,924.52). Inferred withdrawal amount = exact delta since account was 100% cash.'),
    ('2024-07-16', -9969.92, 'withdrawal', 'inferred_from_snapshot_gap_session314',
     'Overnight equity drop with 0 open positions, 0 trades, 0 audit-log entries (102,766.71 -> 92,796.79). Inferred withdrawal amount = exact delta since account was 100% cash.'),
    ('2025-11-18', -20554.24, 'withdrawal', 'user_confirmed_session314',
     'Overnight equity drop with 0 open positions, 0 trades, 0 audit-log entries (95,871.09 -> 75,316.85). User confirmed this was a real capital withdrawal, not a trading loss.')
ON CONFLICT DO NOTHING;

ALTER TABLE algo_portfolio_snapshots ADD COLUMN IF NOT EXISTS net_capital_flow_cum NUMERIC(14, 2);
ALTER TABLE algo_portfolio_snapshots ADD COLUMN IF NOT EXISTS adjusted_equity NUMERIC(14, 2);
ALTER TABLE algo_portfolio_snapshots ADD COLUMN IF NOT EXISTS adjusted_running_peak NUMERIC(14, 2);
ALTER TABLE algo_portfolio_snapshots ADD COLUMN IF NOT EXISTS adjusted_drawdown_pct NUMERIC(8, 4);

COMMENT ON COLUMN algo_portfolio_snapshots.net_capital_flow_cum IS
    'Cumulative sum of algo_capital_flows.amount with flow_date <= this snapshot_date. Positive = net deposited, negative = net withdrawn.';
COMMENT ON COLUMN algo_portfolio_snapshots.adjusted_equity IS
    'total_portfolio_value - net_capital_flow_cum. Strips out external deposits/withdrawals so the series reflects trading performance only.';
COMMENT ON COLUMN algo_portfolio_snapshots.adjusted_running_peak IS
    'Running MAX(adjusted_equity) up to and including this date. Used by circuit_breaker.py drawdown checks instead of raw running_peak.';
COMMENT ON COLUMN algo_portfolio_snapshots.adjusted_drawdown_pct IS
    'Percent below adjusted_running_peak. Used by circuit_breaker.py instead of raw drawdown_pct so capital withdrawals are not misread as trading losses.';

WITH flow_cum AS (
    SELECT
        s.id,
        s.snapshot_date,
        s.total_portfolio_value,
        COALESCE((
            SELECT SUM(f.amount) FROM algo_capital_flows f WHERE f.flow_date <= s.snapshot_date
        ), 0) AS cum_flow
    FROM algo_portfolio_snapshots s
    WHERE s.total_portfolio_value > 0
),
adj AS (
    SELECT
        id,
        snapshot_date,
        cum_flow,
        (total_portfolio_value - cum_flow) AS adjusted_equity,
        MAX(total_portfolio_value - cum_flow) OVER (
            ORDER BY snapshot_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS adjusted_peak
    FROM flow_cum
)
UPDATE algo_portfolio_snapshots s
SET
    net_capital_flow_cum = a.cum_flow,
    adjusted_equity = a.adjusted_equity,
    adjusted_running_peak = a.adjusted_peak,
    adjusted_drawdown_pct = CASE
        WHEN a.adjusted_peak > 0 THEN ((a.adjusted_peak - a.adjusted_equity) / a.adjusted_peak * 100)::DECIMAL(8, 4)
        ELSE 0
    END
FROM adj a
WHERE s.id = a.id;

COMMIT;
