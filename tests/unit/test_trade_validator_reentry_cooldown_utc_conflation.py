"""Regression test: re-entry cooldown day-counting must use ET trading dates, not UTC.

TradeValidator.check_reentry_rules() computed days_since_exit using
datetime.now(timezone.utc).date(), while this same file's validate_entry_preconditions() (a few
lines above) correctly uses datetime.now(EASTERN_TZ).date() for the equivalent "today" concept
(signal_date/entry_date defaults). exit_date is an ET trading date. Between ~7pm-midnight ET,
UTC's calendar date has already rolled to the next day while the ET trading date has not, so the
UTC-based days_since_exit read one day too HIGH - an evening/afterhours orchestrator run could
let a re-entry through one day earlier than min_days_before_reentry_same_symbol actually
requires, a live risk-control bypass. Confirmed live 2026-07-27.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from algo.trading.trade_validator import TradeValidator
from utils.infrastructure import EASTERN_TZ


def _make_validator(min_days=8, max_reentries=3):
    config = {
        "t1_target_r_multiple": 2.0,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": max_reentries,
        "min_days_before_reentry_same_symbol": min_days,
    }
    return TradeValidator(config)


def test_reentry_cooldown_uses_et_date_not_utc_near_day_boundary():
    """11:30 PM EDT on 2026-07-26 is 2026-07-27 03:30 UTC - ET date is still 07-26, UTC date is
    already 07-27. exit_date is 2026-07-19 (7 ET-days elapsed, 8 UTC-days elapsed) with an
    8-day cooldown: the correct (ET) answer is BLOCKED (7 < 8); the buggy (UTC) answer was
    wrongly ALLOWED (8 < 8 is False)."""
    validator = _make_validator(min_days=8)
    cur = MagicMock()
    cur.fetchone.return_value = (
        "TRD-PRIOR",
        date(2026, 7, 19),
        "STOP hit: hard capital preservation",
        -0.83,
        0,
    )

    # Same real instant, two different .now(tz) results - exactly what a real
    # datetime.now(EASTERN_TZ) vs datetime.now(timezone.utc) call pair would produce.
    def fake_now(tz=None):
        if tz is EASTERN_TZ:
            return datetime(2026, 7, 26, 23, 30, 0, tzinfo=tz)
        if tz is timezone.utc:
            return datetime(2026, 7, 27, 3, 30, 0, tzinfo=tz)
        raise AssertionError(f"unexpected tz passed to datetime.now(): {tz!r}")

    with patch("algo.trading.trade_validator.datetime") as mock_dt:
        mock_dt.now.side_effect = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        is_valid, message, _ = validator.check_reentry_rules(cur, "TEST")

    assert is_valid is False, (
        f"Expected re-entry to be BLOCKED (only 7 ET-days since stop-out, need 8) but got "
        f"is_valid={is_valid}, message={message!r} - this is the UTC-date bug reappearing"
    )
    assert message is not None and "7d since stop-out" in message
