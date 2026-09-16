#!/usr/bin/env python3
"""Exit-side backstop coverage for the Real Estate sector-concentration override
(sector_position_cap(), added 2026-09-11 - see
tests/unit/test_sector_position_cap_real_estate_override_20260911.py for the entry-side
gate and the direct sector_position_cap() unit tests, and
reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911 in memory for why).

_check_sector_concentration() (phase6_exit_execution.py) used to filter over-limit
sectors directly in SQL via `HAVING COUNT(*) > %s` against the single global
max_positions_per_sector. It now fetches every sector's count unconditionally and
filters in Python via sector_position_cap(), so these tests mock the (now unparameterized)
GROUP BY query's fetchall() to return raw per-sector counts and verify only the sectors
that actually exceed their EFFECTIVE cap get flagged - Real Estate's tighter override
should bind where the untouched global cap alone would not have.

Follows the exact mocking pattern established in test_phase6_concentration_decimal_handling.py.
"""

from datetime import date as _date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase6_exit_execution import run as phase6_run


def _base_config(**overrides):
    config = {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "min_hold_days": 1,
        "max_hold_days": 90,
        "eight_week_rule_threshold_pct": 1.3,
        "eight_week_rule_window_days": 56,
        "exit_on_distribution_day": False,
        "max_distribution_days": 4,
        "move_be_at_r": 1.5,
        "chandelier_atr_mult": 3.0,
        "max_positions_per_sector": 10,
        "max_position_size_pct": 6.0,
    }
    config.update(overrides)
    return config


def _mock_db_context(sector_counts):
    """Query-aware mock: dispatches fetchall/fetchone off the last-executed SQL text
    rather than positional side_effect order, since the orphaned-trade cleanup at the top
    of run() issues its own SELECT/fetchall and SELECT COUNT/fetchone before the sector
    concentration check ever runs (a purely positional side_effect list breaks the moment
    that upstream query count changes for unrelated reasons)."""
    mock_context = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 0
    mock_context.__enter__ = MagicMock(return_value=mock_cursor)
    mock_context.__exit__ = MagicMock(return_value=None)

    def _last_sql() -> str:
        if not mock_cursor.execute.call_args_list:
            return ""
        return str(mock_cursor.execute.call_args_list[-1].args[0]).upper()

    def _fetchall():
        sql = _last_sql()
        if "GROUP BY CS.SECTOR" in sql:
            return sector_counts
        return []  # broker-order-orphan check, weak-positions query, etc.

    def _fetchone():
        sql = _last_sql()
        if "SELECT COUNT(*) FROM ALGO_TRADES" in sql:
            return (0,)  # no orphaned trades past cleanup
        return (0,)

    mock_cursor.fetchall = MagicMock(side_effect=_fetchall)
    mock_cursor.fetchone = MagicMock(side_effect=_fetchone)
    return mock_context, mock_cursor


def test_real_estate_override_flags_sector_global_cap_would_not_bind():
    """Real Estate at 3 open positions: under the global cap (10) but over its override
    (2) -> flagged as over-concentrated. Technology at 5 stays under the global cap and
    has no override -> not flagged. Only Real Estate's weak-positions query should fire."""
    mock_context, mock_cursor = _mock_db_context([("Real Estate", 3), ("Technology", 5)])

    config = _base_config(max_positions_per_sector_real_estate=2)

    with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
        with patch("algo.trading.ExitEngine"):
            with patch("algo.orchestrator.phase6_exit_execution.logger") as mock_logger:
                result = phase6_run(
                    config=config,
                    run_date=_date.today(),
                    dry_run=True,
                    alerts=MagicMock(),
                    verbose=False,
                    log_phase_result_fn=MagicMock(),
                    position_recs=[],
                    exposure_actions=[],
                )

    assert result is not None
    concentration_warnings = [
        c for c in mock_logger.warning.call_args_list if "PHASE 6 CONCENTRATION" in str(c.args[0])
    ]
    assert any("Real Estate" in str(c.args[0]) and "limit 2" in str(c.args[0]) for c in concentration_warnings)
    assert not any("Technology" in str(c.args[0]) for c in concentration_warnings)


def test_no_override_configured_behaves_identically_to_prior_global_only_gate():
    """Regression guard: max_positions_per_sector_real_estate unset -> Real Estate uses
    the global cap exactly like every sector always has (matches pre-2026-09-11 behavior)."""
    mock_context, mock_cursor = _mock_db_context([("Real Estate", 3)])

    config = _base_config()  # no max_positions_per_sector_real_estate key

    with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
        with patch("algo.trading.ExitEngine"):
            with patch("algo.orchestrator.phase6_exit_execution.logger") as mock_logger:
                result = phase6_run(
                    config=config,
                    run_date=_date.today(),
                    dry_run=True,
                    alerts=MagicMock(),
                    verbose=False,
                    log_phase_result_fn=MagicMock(),
                    position_recs=[],
                    exposure_actions=[],
                )

    assert result is not None
    concentration_warnings = [
        c for c in mock_logger.warning.call_args_list if "PHASE 6 CONCENTRATION" in str(c.args[0])
    ]
    assert not concentration_warnings
