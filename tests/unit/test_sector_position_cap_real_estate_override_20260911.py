"""Tests for the Real Estate sector-concentration override added 2026-09-11.

Context: this session's live leaderboard investigation confirmed Real Estate is
overweighted (14% of the top-50 vs 4.8% of the qualifying universe) AND underperforming
(21-day forward return -0.63% median vs +0.35% rest-of-universe) - see
reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911 in memory. Three
scoring-math fixes were tested and rejected before this; sector_position_cap()
(algo/orchestrator/type_converters.py) is a portfolio-construction fix instead: a
sector-specific override of the existing generic max_positions_per_sector gate, applied
identically at both enforcement points (phase8_entry_execution.py entry-side,
phase6_exit_execution.py exit-side backstop) so they keep agreeing on what "over the
limit" means for every sector, per the same design note the 2026-09-08 entry-side gate
commit already established.
"""

from unittest.mock import patch

from algo.orchestrator.phase8_entry_execution import run
from algo.orchestrator.type_converters import sector_position_cap
from tests.unit.test_phase8_run_core_loop_integration_20260831 import (
    Phase8Deps,
    _FakeCursor,
    _make_signal,
    _run_kwargs,
)


def _cursor_with_sector_counts(base_cursor: _FakeCursor, sector_counts: list[tuple]) -> None:
    real_fetchall = _FakeCursor.fetchall

    def _fetchall():
        sql = base_cursor._last_sql.upper()
        if "GROUP BY CS.SECTOR" in sql:
            return sector_counts
        return real_fetchall(base_cursor)

    base_cursor.fetchall = _fetchall


# --- sector_position_cap() unit tests -------------------------------------------------


def test_real_estate_override_applied():
    config = {"max_positions_per_sector_real_estate": 2}
    assert sector_position_cap(config, "Real Estate", global_cap=8) == 2


def test_non_real_estate_sector_always_uses_global_cap():
    config = {"max_positions_per_sector_real_estate": 2}
    assert sector_position_cap(config, "Financial Services", global_cap=8) == 8
    assert sector_position_cap(config, "Technology", global_cap=8) == 8


def test_missing_override_falls_back_to_global_cap():
    config: dict = {}
    assert sector_position_cap(config, "Real Estate", global_cap=8) == 8


def test_malformed_override_fails_closed_to_global_cap():
    config = {"max_positions_per_sector_real_estate": "not-a-number"}
    assert sector_position_cap(config, "Real Estate", global_cap=8) == 8


def test_none_sector_uses_global_cap():
    config = {"max_positions_per_sector_real_estate": 2}
    assert sector_position_cap(config, None, global_cap=8) == 8


# --- entry-side integration: Real Estate binds tighter than Financial Services --------


def test_real_estate_blocked_at_tighter_cap_while_other_sector_unaffected():
    """Both sectors have 1 open position and the global cap is 8 (unreached by either) -
    only Real Estate's override (2) actually binds anything, and it binds at count=1
    reaching the override's own value being tested against >=, so use count=2 to trip it
    while Financial Services at the same count=2 stays under the untouched global cap."""
    reit_signal = _make_signal("REITA", sector="Real Estate", composite_score=90.0)
    bank_signal = _make_signal("BANKA", sector="Financial Services", composite_score=80.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sector_counts(deps.fake_cursor, [("Real Estate", 2), ("Financial Services", 2)])
        with patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection:
            result = run(
                **_run_kwargs(
                    [reit_signal, bank_signal],
                    max_positions_per_sector=8,
                    max_positions_per_sector_real_estate=2,
                )
            )

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert deps.mock_trade_executor.execute_trade.call_args.kwargs["symbol"] == "BANKA"
    assert result.data["entered"] == 1

    sector_rejections = [c for c in mock_log_rejection.call_args_list if "sector_concentration_limit" in c.args[2]]
    assert len(sector_rejections) == 1
    assert sector_rejections[0].args[0] == "REITA"
    assert "limit 2" in sector_rejections[0].args[2]


def test_real_estate_override_absent_behaves_identically_to_prior_gate():
    """No override configured -> Real Estate uses the global cap exactly like every other
    sector always has (regression guard: this change must not alter existing behavior when
    the new config key is simply unset, matching the pre-2026-09-11 gate)."""
    reit_signal = _make_signal("REITA", sector="Real Estate", composite_score=90.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sector_counts(deps.fake_cursor, [("Real Estate", 1)])
        result = run(**_run_kwargs([reit_signal], max_positions_per_sector=8))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert result.data["entered"] == 1
