"""Regression test: reconciliation_broker_positions.py's open-position query must
aggregate ALL open algo_trades legs per symbol, not just the most recent one.

Before this fix, `_fetch_and_analyze_open_positions`'s `open_trades` CTE used
`SELECT DISTINCT ON (at.symbol) ... ORDER BY at.symbol, at.trade_date DESC` - for a
pyramided (scaled-in) position (2+ open algo_trades rows for the same symbol, a real,
supported case per position_sizer.py), this kept only the MOST RECENT leg's
quantity/entry_price and silently dropped every earlier leg. That understated
unrealized_pnl/winning_count and, via _compute_broker_snapshot_metrics, the
concentration/Herfindahl metrics written to algo_portfolio_snapshots - meaning the
concentration circuit-breaker could be blind to a symbol's true aggregate position size.

This module's SQL is too DB-heavy to unit-test end to end without a real Postgres
instance (see the reconciliation module's own existing precedent of source-level checks
for exactly this reason) - verified via source inspection: the query must GROUP BY
symbol (aggregating every open leg) rather than DISTINCT ON (collapsing to one).
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "infrastructure" / "reconciliation_broker_positions.py").read_text(encoding="utf-8")


def _open_trades_cte() -> str:
    start = SOURCE.index("open_trades AS (")
    end = SOURCE.index("SELECT symbol, quantity, avg_entry_price, entry_price_source, current_price, position_value")
    return SOURCE[start:end]


class TestReconciliationAggregatesPyramidedLegs:
    def test_does_not_collapse_to_one_row_per_symbol(self):
        cte = _open_trades_cte()
        # The actual SQL clause, not this file's own explanatory comment about the old bug.
        assert "SELECT DISTINCT ON (at.symbol)" not in cte, (
            "open_trades must not use SELECT DISTINCT ON (at.symbol) - that keeps only the "
            "most recent algo_trades row per symbol and silently drops every earlier "
            "pyramided leg's quantity/entry_price from unrealized P&L and concentration "
            "metrics."
        )

    def test_groups_by_symbol_to_aggregate_all_open_legs(self):
        cte = _open_trades_cte()
        assert "GROUP BY at.symbol" in cte, (
            "open_trades must GROUP BY at.symbol so every open algo_trades leg for a "
            "pyramided position is summed, not just the latest one."
        )

    def test_quantity_is_summed_across_legs(self):
        cte = _open_trades_cte()
        assert "SUM(at.entry_quantity) as quantity" in cte

    def test_entry_price_is_cost_basis_weighted_average(self):
        cte = _open_trades_cte()
        # Cost-basis-weighted average: sum(qty*price) / sum(qty), matching
        # PositionAnalyzer's own cost-basis-weighted P&L% convention.
        assert "SUM(at.entry_quantity * at.entry_price) / NULLIF(SUM(at.entry_quantity), 0)" in cte
