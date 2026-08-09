"""Regression test: circuit breaker snapshot queries must bound by current_date.

Guards against the exact bug class fixed 2026-08-09: _check_drawdown,
_check_drawdown_re_engagement, and _check_total_risk each took a `current_date`
argument but ignored it in their "latest snapshot" query, using an unbounded
`ORDER BY snapshot_date DESC LIMIT 1`. A stray future-dated row in the shared
dev DB (a leftover local `--date` simulation snapshot) outranked the real
current snapshot and corrupted the drawdown/risk halt calculation - live-
reproduced 2026-08-09 (a 2026-08-11 test snapshot beat a 2026-08-07 real run).
_check_daily_loss and _check_daily_profit_cap already bounded correctly and
serve as the reference pattern these three now match.
"""

from datetime import date
from unittest.mock import Mock

from algo.risk import CircuitBreaker


def _cb():
    return CircuitBreaker(
        config={
            "circuit_breaker_enabled": True,
            "halt_drawdown_pct": -20.0,
            "max_total_risk_pct": 4.0,
        }
    )


def _executed_sql(mock_cur):
    return "\n".join(call.args[0] for call in mock_cur.execute.call_args_list)


def _executed_params(mock_cur):
    return [call.args[1] for call in mock_cur.execute.call_args_list if len(call.args) > 1]


def test_check_drawdown_bounds_by_current_date():
    cb = _cb()
    mock_cur = Mock()
    mock_cur.fetchone.return_value = (100000.0, 90000.0)
    current_date = date(2026, 8, 7)

    cb._check_drawdown(current_date, mock_cur)

    sql = _executed_sql(mock_cur)
    assert "snapshot_date <= %s" in sql, "drawdown check must bound the current-value subquery by current_date"
    params = _executed_params(mock_cur)
    assert any(current_date in p for p in params), "current_date must be passed as a bound query parameter"


def test_check_drawdown_re_engagement_bounds_by_current_date():
    cb = _cb()
    mock_cur = Mock()
    mock_cur.fetchone.return_value = None  # short-circuits after the query; only shape matters here
    current_date = date(2026, 8, 7)

    cb._check_drawdown_re_engagement(current_date, mock_cur)

    sql = _executed_sql(mock_cur)
    assert "snapshot_date <= %s" in sql
    params = _executed_params(mock_cur)
    assert any(current_date in p for p in params)


def test_check_total_risk_bounds_by_current_date():
    cb = _cb()
    mock_cur = Mock()
    # Query order in _check_total_risk: (1) missing-stops count, (2) risk SUM/COUNT,
    # (3) actual-open-count cross-check, (4) the portfolio snapshot query under test.
    mock_cur.fetchone.side_effect = [(0,), (0, 0), (0,), None]
    current_date = date(2026, 8, 7)

    cb._check_total_risk(current_date, mock_cur)

    sql = _executed_sql(mock_cur)
    assert "snapshot_date <= %s" in sql
    params = _executed_params(mock_cur)
    assert any(current_date in p for p in params)
