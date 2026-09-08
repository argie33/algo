"""Regression tests for the entry-side sector concentration gate added 2026-09-08.

phase6_exit_execution.py's `_check_sector_concentration()` already enforces
`max_positions_per_sector`, but only by force-exiting positions AFTER a sector is already over
the limit - nothing on the entry side stopped a new position from creating that overload in the
first place. `run()`'s pre-entry concentration-prefilter loop (phase8_entry_execution.py) now
also caps admissions per sector, using the same config key and the same "count of open
algo_positions per company_profile.sector" definition phase6 already uses.

Reuses the `Phase8Deps`/`_FakeCursor` harness from test_phase8_run_core_loop_integration_20260831.py
rather than rebuilding it - see that file's own docstring for why this harness exists.
"""

from unittest.mock import patch

from algo.orchestrator.phase8_entry_execution import run
from tests.unit.test_phase8_run_core_loop_integration_20260831 import (
    Phase8Deps,
    _FakeCursor,
    _make_signal,
    _run_kwargs,
)


def _cursor_with_sector_counts(base_cursor: _FakeCursor, sector_counts: list[tuple]) -> None:
    """Patches fetchall() to answer the sector-counts GROUP BY query, everything else unchanged."""
    real_fetchall = _FakeCursor.fetchall

    def _fetchall():
        sql = base_cursor._last_sql.upper()
        if "GROUP BY CS.SECTOR" in sql:
            return sector_counts
        return real_fetchall(base_cursor)

    base_cursor.fetchall = _fetchall


def test_second_candidate_in_same_sector_blocked_once_limit_reached():
    """Sector already at the configured cap -> a new candidate in that sector is rejected,
    never reaches TradeExecutor, but a same-batch candidate in a different sector still can."""
    same_sector = _make_signal("BANKA", sector="Financial Services", composite_score=90.0)
    other_sector = _make_signal("TECHA", sector="Technology", composite_score=80.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sector_counts(deps.fake_cursor, [("Financial Services", 1)])
        with patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection:
            result = run(**_run_kwargs([same_sector, other_sector], max_positions_per_sector=1))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert deps.mock_trade_executor.execute_trade.call_args.kwargs["symbol"] == "TECHA"
    assert result.data["entered"] == 1

    sector_rejections = [c for c in mock_log_rejection.call_args_list if "sector_concentration_limit" in c.args[2]]
    assert len(sector_rejections) == 1
    assert sector_rejections[0].args[0] == "BANKA"


def test_candidates_within_sector_limit_all_admitted():
    """Sector currently empty, cap of 2 -> both same-sector candidates in this batch are
    admitted (the gate increments its in-memory count as each candidate is accepted)."""
    first = _make_signal("BANKA", sector="Financial Services", composite_score=90.0)
    second = _make_signal("BANKB", sector="Financial Services", composite_score=80.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sector_counts(deps.fake_cursor, [])
        result = run(**_run_kwargs([first, second], max_positions_per_sector=2))

    assert deps.mock_trade_executor.execute_trade.call_count == 2
    assert result.data["entered"] == 2


def test_missing_config_fails_open_not_closed():
    """max_positions_per_sector missing from config -> gate disabled, entries proceed instead
    of every candidate being blocked (this is a diversification control, not a capital-safety
    gate - phase6's exit-side check remains as a backstop)."""
    same_sector_a = _make_signal("BANKA", sector="Financial Services", composite_score=90.0)
    same_sector_b = _make_signal("BANKB", sector="Financial Services", composite_score=80.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sector_counts(deps.fake_cursor, [("Financial Services", 5)])
        kwargs = _run_kwargs([same_sector_a, same_sector_b])
        assert "max_positions_per_sector" not in kwargs["config"]
        result = run(**kwargs)

    assert deps.mock_trade_executor.execute_trade.call_count == 2
    assert result.data["entered"] == 2
