"""Regression test: lambda/api/routes/health.py's basic health check computed its
"market_open" field (and the STALE/NO_DATA gates that key off it) from
MarketCalendar.is_trading_day(today) - a weekday/holiday check only, true at every hour
of a trading day including 3 AM. The field is exposed verbatim in the API response as
"market_open" and the surrounding code's own comments state the real intent ("Don't mark
as critical during non-market hours (loaders don't run then)"), which only
MarketCalendar.is_market_open() (the real 9:30 AM-4:00 PM ET window check) satisfies.

Confirmed live 2026-07-28: /api/health reported "market_open": true at 07:32 ET, nearly
two hours before the market actually opens. With signal_stale_threshold_hours=24
(default), this would have falsely flagged a stale Friday-evening signal as STALE
starting at midnight Monday instead of after 9:30 AM, when in fact it's completely
normal for signals to be >24h old before Monday's Phase 7 has had a chance to run.

Fixed by calling MarketCalendar.is_market_open(now) instead of is_trading_day(today).
"""

import inspect
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from algo.infrastructure.market_calendar import MarketCalendar

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_health_route_uses_is_market_open_not_is_trading_day():
    import routes.health as health_route

    source = inspect.getsource(health_route._handle_basic)
    freshness_block = source.split("market_is_open = ", 1)[1].split("\n", 1)[0]

    assert "MarketCalendar.is_market_open(" in freshness_block, (
        "health.py must compute market_is_open via the real 9:30-4:00 ET window check, "
        f"got: {freshness_block!r}"
    )
    assert "is_trading_day" not in freshness_block, (
        "is_trading_day() only checks weekday/holiday, not actual market hours - it is "
        "true at every hour of a trading day and must not be used for market_is_open"
    )


def test_is_trading_day_and_is_market_open_disagree_before_open():
    """Documents exactly why the swap matters: at 07:32 ET on a trading weekday,
    is_trading_day says yes (correct for its own purpose) but the market is not open yet -
    this is the gap the old code silently papered over."""
    a_trading_weekday = date(2026, 7, 28)  # confirmed non-holiday Tuesday
    pre_market = datetime(2026, 7, 28, 11, 32, tzinfo=timezone.utc)  # 07:32 ET

    assert MarketCalendar.is_trading_day(a_trading_weekday) is True
    assert MarketCalendar.is_market_open(pre_market) is False
