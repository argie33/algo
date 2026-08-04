"""Regression test: utils/data_queries.py's get_trade_win_loss_stats must exclude the same
non-representative closes as the live trading gate (algo/risk/circuit_breaker.py::
_check_win_rate_floor) and the reporting loader (loaders/compute_circuit_breakers.py::
_compute_win_rate) it's supposed to agree with.

Before this fix: get_trade_win_loss_stats had no exclusions at all (no reconciliation/
force-close/delisted/DATA-QC/CONCENTRATION filter, no exit_r_multiple guard, no
deterministic exit_time/id tiebreak) - the one CB9 win-rate implementation the
2026-08-03 CONCENTRATION-exclusion fix (commit 3078163b2) missed. Live-reproduced
2026-08-03: this function's dashboard endpoint (lambda/api/routes/algo_handlers/
dashboard.py CB9 "Win Rate Floor") reported a contaminated 24.0% - 8 of its 30 most
recent trades were POSITION_SIZE_CONCENTRATION force-exits / a reconciliation close -
falsely triggering "Win Rate Floor Breached" on the dashboard, right alongside the
already-patched consecutive_losses=0 (circuit_breaker_status), producing the
"consecutive_losses is 0 but win_rate_floor triggered" confusion this was filed under.
The live trading gate itself was never affected (it already had the exclusion fix);
only this dashboard display was wrong.
"""

import importlib
from unittest.mock import MagicMock

module = importlib.import_module("utils.data_queries")


def test_win_loss_stats_query_excludes_non_representative_closes():
    cur = MagicMock()
    cur.fetchone.return_value = {"wins": 1, "losses": 1, "total": 2}
    module.get_trade_win_loss_stats(cur, limit=30)

    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]

    assert "EXT-%%" in sql
    assert "exit_r_multiple IS NOT NULL" in sql
    assert "exit_time DESC NULLS LAST" in sql
    assert params == ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%", 30)


def test_win_loss_stats_returns_none_triple_when_query_returns_no_row():
    cur = MagicMock()
    cur.fetchone.return_value = None
    result = module.get_trade_win_loss_stats(cur, limit=30)
    assert result == {"wins": None, "losses": None, "total": None}


def test_win_loss_stats_defaults_missing_counts_to_zero():
    cur = MagicMock()
    cur.fetchone.return_value = {"wins": None, "losses": None, "total": None}
    result = module.get_trade_win_loss_stats(cur, limit=30)
    assert result == {"wins": 0, "losses": 0, "total": 0}
