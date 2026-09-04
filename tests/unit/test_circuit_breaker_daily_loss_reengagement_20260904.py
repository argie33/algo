"""Regression test: daily-loss circuit breaker gets a minimum-elapsed-trading-days
re-engagement lockout, generalized from drawdown's existing protection.

GAP FOUND 2026-09-04 (real-money-readiness adversarial audit): only `drawdown` had a
re-engagement lockout (_check_drawdown_re_engagement). vix_spike/daily_loss/weekly_loss/
total_risk could clear the instant the underlying metric ticked back under threshold on
the very next check_all() call, with no minimum-time-elapsed requirement - a real flap
risk (trip -> clear -> trip again) even though the underlying condition (e.g. a bad
trading day) hadn't actually resolved on a meaningfully longer timescale.

Fixed via _check_min_reengagement_days, a generalization of drawdown's day-gate (the
recovery-pct/Follow-Through-Day parts of drawdown's protocol don't apply to these four -
they aren't "distance from peak" concepts - so only the shared day-gate is reused).
"""

from datetime import date, timedelta
from unittest.mock import Mock

from algo.infrastructure import MarketCalendar
from algo.risk import CircuitBreaker


def _cb(min_days: int = 2):
    return CircuitBreaker(
        config={
            "daily_loss_min_reengagement_days": min_days,
        }
    )


def test_daily_loss_reengagement_blocks_immediately_after_halt_even_if_metric_recovered():
    """A daily_loss halt fired today; even though the caller only asks about
    re-engagement (not the daily_loss metric itself, which is a separate check), the
    lockout must still hold until min_days trading sessions have elapsed."""
    halt_today = date(2026, 9, 3)
    cb = _cb(min_days=2)
    mock_cur = Mock()
    mock_cur.fetchone.return_value = (halt_today,)

    result = cb._check_daily_loss_re_engagement(halt_today, mock_cur)

    assert result["halted"] is True
    assert "0d ago" in result["reason"]
    assert "2d" in result["reason"]


def test_daily_loss_reengagement_clears_after_min_trading_days_elapsed():
    halt_date = date(2026, 9, 3)
    current_date = halt_date
    while MarketCalendar.trading_days_elapsed(halt_date, current_date) < 2:
        current_date += timedelta(days=1)

    cb = _cb(min_days=2)
    mock_cur = Mock()
    mock_cur.fetchone.return_value = (halt_date,)

    result = cb._check_daily_loss_re_engagement(current_date, mock_cur)

    assert result["halted"] is False


def test_daily_loss_reengagement_not_halted_when_no_prior_halt_found():
    cb = _cb(min_days=2)
    mock_cur = Mock()
    mock_cur.fetchone.return_value = None

    result = cb._check_daily_loss_re_engagement(date(2026, 9, 4), mock_cur)

    assert result["halted"] is False
