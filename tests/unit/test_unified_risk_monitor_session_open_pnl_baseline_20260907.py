"""Regression test for a real-money-readiness audit finding: unified_risk_monitor.py's
_check_portfolio_variance used to read `unrealized_pnl_total` as the "session open" P&L
baseline. That column is NOT fixed per day - Phase 9 reconciliation (always_run=True) runs
multiple times per trading day (premarket/morning/afternoon/preclose/evening, per
terraform/modules/services/2x-daily-orchestrator.tf) and every run UPSERTs the same
snapshot_date row's unrealized_pnl_total to whatever the current value is at that run.

Concrete failure mode: a portfolio down 10% by 1pm (correctly measured against the 9:30am
open) would have its baseline silently reset to the 1pm value by that run's Phase 9 write.
A further 8% slide by 3pm would then measure as only -8% against the reset baseline, not
the true -18% since actual market open - potentially staying under a variance threshold
that a real cumulative session loss should have tripped.

Fix (migration 1269): a new session_open_unrealized_pnl_total column, written once per day
on the first Phase 9 write and excluded from every later same-day ON CONFLICT DO UPDATE, so
it stays a genuine market-open baseline all day. This test proves the SQL query now targets
that column, not the mutable one.
"""

from unittest.mock import patch

from algo.risk.unified_risk_monitor import _check_portfolio_variance


class _FakeCursor:
    def __init__(self, session_open_value: float):
        self.session_open_value = session_open_value
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        last_query = self.queries[-1]
        if "algo_portfolio_snapshots" in last_query:
            return (self.session_open_value,)
        raise AssertionError(f"unexpected query: {last_query}")


def test_variance_check_queries_session_open_column_not_mutable_total():
    """The SQL must select session_open_unrealized_pnl_total (immutable per day), never
    unrealized_pnl_total (overwritten by every same-day Phase 9 run)."""
    fake_cur = _FakeCursor(session_open_value=1000.0)
    with (
        patch("algo.risk.unified_risk_monitor.DatabaseContext", return_value=fake_cur),
        patch(
            "algo.risk.unified_risk_monitor.get_open_portfolio_totals",
            return_value={"total_equity": 100000.0, "current_pnl": 1500.0},
        ),
    ):
        result = _check_portfolio_variance(config={})

    snapshot_query = next(q for q in fake_cur.queries if "algo_portfolio_snapshots" in q)
    assert "session_open_unrealized_pnl_total" in snapshot_query, (
        "must read the immutable per-day session-open column, not unrealized_pnl_total "
        "(which every Phase 9 run that day overwrites)"
    )
    assert "unrealized_pnl_total" not in snapshot_query.replace("session_open_unrealized_pnl_total", "")

    # (1500 - 1000) / 100000 = 0.005
    assert result["variance"] == 0.005
    assert result["open_pnl"] == 1000.0


def test_missing_session_open_value_raises_not_silently_zero():
    fake_cur = _FakeCursor(session_open_value=None)
    with (
        patch("algo.risk.unified_risk_monitor.DatabaseContext", return_value=fake_cur),
        patch(
            "algo.risk.unified_risk_monitor.get_open_portfolio_totals",
            return_value={"total_equity": 100000.0, "current_pnl": 1500.0},
        ),
    ):
        try:
            _check_portfolio_variance(config={}, max_attempts=1)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as e:
            assert "NULL" in str(e) or "session_open_unrealized_pnl_total" in str(fake_cur.queries[-1])
