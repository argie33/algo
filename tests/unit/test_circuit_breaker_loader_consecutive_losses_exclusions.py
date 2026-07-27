"""Regression test: loaders/compute_circuit_breakers.py's _compute_consecutive_losses must
exclude the same non-representative closes (reconciliation/force-close/delisted/DATA-QC)
that algo/risk/circuit_breaker.py's _check_consecutive_losses (the live trading gate)
already excludes.

Before this fix, this reporting loader used a plain query with no exclusions and no
exit_time tiebreak, so it kept counting bug-induced closes (marked DATA-QC after the live
gate was fixed) as real losses. Live-reproduced 2026-07-27: the dashboard-facing
circuit_breaker_status table showed consecutive_losses=10 (CB3 triggered) for hours after
the live gate had already been fixed to correctly report 0 - the two were meant to agree
and didn't.
"""

import importlib
from unittest.mock import MagicMock

module = importlib.import_module("loaders.compute_circuit_breakers")


def test_consecutive_losses_query_excludes_non_representative_closes():
    cur = MagicMock()
    cur.fetchall.return_value = []
    module._compute_consecutive_losses(cur)

    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]

    assert "EXT-%%" in sql
    assert "exit_time DESC NULLS LAST" in sql
    assert params == ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%")


def test_consecutive_losses_skips_null_pnl_and_stops_at_first_win():
    cur = MagicMock()
    cur.fetchall.return_value = [
        {"profit_loss_pct": -1.0},
        {"profit_loss_pct": None},
        {"profit_loss_pct": -2.0},
        {"profit_loss_pct": 0.5},
        {"profit_loss_pct": -3.0},
    ]
    assert module._compute_consecutive_losses(cur) == 2


def test_consecutive_losses_returns_zero_for_no_closed_trades():
    cur = MagicMock()
    cur.fetchall.return_value = []
    assert module._compute_consecutive_losses(cur) == 0
