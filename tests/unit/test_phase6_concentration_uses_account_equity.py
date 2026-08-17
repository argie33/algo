"""Regression test for the 2026-08-03 fix: Phase 6's position-size concentration
check must divide by total account equity, not the sum of currently-open positions.

Bug (confirmed live 2026-08-03): _check_position_size_concentration() used
`SELECT SUM(position_value) FROM algo_positions WHERE status='open'` as its
denominator. Phase 8 sizes positions against real account equity (algo_
portfolio_snapshots.total_portfolio_value), which is normally far larger than
the sum of a handful of currently-open positions (most of the account is
usually cash). Live-confirmed: a $1,441 position sized at ~2% of a $72k
account was reported as 23% concentrated (1441 / 6270, where 6270 was just
the sum of that run's 3 open positions) and force-exited - several of these
landing as losses and tripping the consecutive-losses circuit breaker, halting
the whole orchestrator.

This test drives the real, unmocked percentage/threshold arithmetic (not a
re-statement of it) by mocking only the DB layer, with position values and a
total account equity chosen so the bug and the fix produce different,
distinguishable outcomes:
  - position value: $2,000
  - sum of open positions (old, wrong denominator): $10,000  -> 20% (flagged, > 6%)
  - total account equity (new, correct denominator): $72,000 -> 2.8% (not flagged)

BUG FIX 2026-08-17: the patch target below used to be "algo.orchestrator.phase6_exit_execution.DatabaseContext" - the
wrong location. See test_phase6_concentration_decimal_handling.py's matching fix docstring for
why (phase6_exit_execution.py binds its own module-local DatabaseContext name at import time,
so patching the original definition site never intercepted it).
"""

from datetime import date as _date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase6_exit_execution import run as phase6_run
from algo.orchestrator.phase_result import PhaseResult

BASE_CONFIG = {
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


def test_small_legit_position_not_flagged_against_account_equity():
    """A position sized well under the limit vs. real equity must not be force-exited,
    even though it would exceed the limit against the old (wrong) open-positions-sum."""
    mock_context = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 0  # orphaned-trade cleanup DELETE (phase6_exit_execution.py) compares this to an int
    mock_context.__enter__ = MagicMock(return_value=mock_cursor)
    mock_context.__exit__ = MagicMock(return_value=None)

    position_value = Decimal("2000.00")
    total_account_equity = Decimal("72000.00")  # correct denominator -> 2.8%, under 6% limit

    mock_cursor.fetchone = MagicMock(
        side_effect=[
            (0,),  # phase6_exit_execution's own orphaned-trade validation check, runs first
            (1, 0),  # COUNT(*), COUNT(NULL position_value) - one open position, no NULLs
            (total_account_equity,),  # algo_portfolio_snapshots.total_portfolio_value
        ]
    )
    mock_cursor.fetchall = MagicMock(
        side_effect=[
            [],  # _check_sector_concentration runs first - no over-concentrated sectors
            [("pos_001", "XYZ", position_value)],  # all open positions, ordered by value desc
        ]
    )

    with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=mock_context):
        with patch("algo.trading.ExitEngine"):
            result = phase6_run(
                config=BASE_CONFIG,
                run_date=_date.today(),
                dry_run=True,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
                position_recs=[],
                exposure_actions=[],
            )

    assert isinstance(result, PhaseResult)
    # The position must NOT be counted as a would-be exit - 2.8% of real equity is
    # well under the 6% limit. Under the old bug (denominator = sum of open
    # positions = $2,000, i.e. this position IS the whole sum) it would read as
    # 100% concentrated, get force-exited, and exit_count would be 1.
    assert result.data["exits"] == 0
