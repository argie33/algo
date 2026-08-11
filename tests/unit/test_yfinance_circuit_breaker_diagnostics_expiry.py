"""Regression test: get_diagnostics() must apply the same ban-expiry auto-clear as is_banned().

Live-confirmed bug: get_diagnostics() read raw ban state via _get_ban_state() without the
expiry check is_banned() applies, so it kept reporting is_banned=True (with a
self-contradictory backoff_secs=0.0) after the real ban_until had already passed, until some
other code path happened to call is_banned() first and cleared it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from utils.external.yfinance_circuit_breaker import YFinanceIPCircuitBreaker


def test_get_diagnostics_clears_an_expired_ban_without_a_prior_is_banned_call():
    cb = YFinanceIPCircuitBreaker()
    expired_state = {
        "is_banned": True,
        "failure_count": 3,
        "ban_until": datetime.now(timezone.utc) - timedelta(seconds=1),
        "last_error_time": datetime.now(timezone.utc) - timedelta(minutes=5),
        "last_success_time": None,
        "reason": "Rate limit detected (429/401)",
    }
    cleared_state = {**expired_state, "is_banned": False, "ban_until": None, "reason": "Ban expired"}

    # First _get_ban_state() call happens inside is_banned() (sees the still-expired record and
    # triggers _clear_ban()); the second happens in get_diagnostics()'s own read afterward and
    # must see the now-cleared state - real _clear_ban() would make this true against a real DB,
    # this side_effect stands in for that write taking effect.
    with patch.object(YFinanceIPCircuitBreaker, "_get_ban_state", side_effect=[expired_state, cleared_state]):
        with patch.object(YFinanceIPCircuitBreaker, "_clear_ban") as mock_clear:
            diagnostics = cb.get_diagnostics()

    mock_clear.assert_called_once()
    assert diagnostics["is_banned"] is False
