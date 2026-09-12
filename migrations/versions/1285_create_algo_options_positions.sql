-- Migration 1285: Create algo_options_positions.
--
-- Phase 4 of the options-strategy plan (steering/OPTIONS_STRATEGY_SPEC.md) - risk/collateral
-- infrastructure. Tracks the full CSP/covered-call wheel lifecycle described in spec section 5
-- (open CSP -> assignment -> covered call -> called away / roll chain), so
-- algo/risk/options_collateral.py has a single source of truth for how much cash collateral
-- is currently committed (never double-counted) and algo/risk/circuit_breaker_options.py can
-- enforce the sleeve/per-underlying/sector caps in spec section 4.
--
-- Following the same phantom-migration lessons this session's CLAUDE.md documents
-- (options_chains/iv_history never had a CREATE TABLE anywhere in this repo's history until
-- migrations 1283/1284 fixed it) - this is a genuinely new table, guarded with IF NOT EXISTS
-- throughout so a re-run (or a future migration that also touches this table) can't hard-fail
-- migrations/run.py's apply_all_pending(), which stops at the first failure.
--
-- No execution code exists yet (phase 5, not started) - this table has no writer in production
-- yet. It exists so phase 5's future order-submission code has real infrastructure to write
-- into instead of inventing ad hoc accounting at that point.
CREATE TABLE IF NOT EXISTS algo_options_positions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    sector VARCHAR(100),
    option_type VARCHAR(4) NOT NULL CHECK (option_type IN ('put', 'call')),
    strategy_leg VARCHAR(20) NOT NULL CHECK (strategy_leg IN ('csp', 'covered_call')),
    strike NUMERIC(12, 4) NOT NULL,
    expiration_date DATE NOT NULL,
    contracts INTEGER NOT NULL CHECK (contracts > 0),
    entry_date DATE NOT NULL,
    -- Per-share premium collected at entry (not multiplied by contracts/100) - matches the
    -- rest of this codebase's convention of storing per-share prices (see options_chains.iv/
    -- strike_price) and computing notional amounts at read time.
    entry_premium NUMERIC(12, 4) NOT NULL,
    -- Cash collateral actually committed for an open CSP (strike * 100 * contracts). 0/NULL
    -- for a covered call, which is share-collateralized (the sleeve already owns the shares
    -- from a prior CSP assignment), not cash-collateralized - see spec section 4's "strict
    -- cash-secured, no margin" posture. compute_committed_collateral() in
    -- algo/risk/options_collateral.py sums exactly this column over status='open' rows as the
    -- single source of truth for committed collateral.
    collateral_amount NUMERIC(14, 2),
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'assigned', 'closed', 'rolled', 'expired')),
    -- Set only on CSP assignment: strike - premium collected (spec section 5). NULL until then.
    cost_basis NUMERIC(12, 4),
    -- Set only on CSP assignment: shares received (contracts * 100 at assignment time).
    assigned_shares INTEGER,
    -- Self-referential FK for roll chains (spec section 5: "roll a CSP" closes this row and
    -- opens a new one pointing back at it via rolled_from_id). Nullable - most rows are not
    -- the result of a roll.
    rolled_from_id BIGINT REFERENCES algo_options_positions(id),
    closed_date DATE,
    exit_price NUMERIC(12, 4),
    realized_pnl NUMERIC(14, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Collateral accounting (compute_committed_collateral, underlying/sector exposure checks) and
-- the equity-overlap check filter on status='open' constantly - see options_collateral.py.
CREATE INDEX IF NOT EXISTS idx_algo_options_positions_symbol_status
    ON algo_options_positions(symbol, status);

CREATE INDEX IF NOT EXISTS idx_algo_options_positions_status
    ON algo_options_positions(status);
