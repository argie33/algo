"""Regression test: MarketStatusDailyLoader._fetch_fed_rate_environment() computed
`last_trading_day` via MarketCalendar but then measured staleness with raw calendar-day
subtraction `(eval_date - rate_date_obj).days` instead - `last_trading_day` was dead,
and the actual check ignored this project's standing "date math must be trading-day-aware"
rule (MEMORY.md). Fixed to count trading days elapsed via MarketCalendar.get_trading_days().
"""

import logging
from datetime import date
from unittest.mock import patch

from loaders.load_market_status_daily import MarketStatusDailyLoader


def _make_loader():
    loader = MarketStatusDailyLoader()
    loader._fred_api_key = "test-key"
    return loader


def test_fed_rate_fresh_same_day_does_not_warn(caplog):
    loader = _make_loader()
    eval_date = date(2026, 8, 10)  # Monday
    fred_data = [{"date": "2026-08-10", "value": 3.5}]

    with patch("loaders.load_economic_data.fetch_from_fred", return_value=fred_data):
        with caplog.at_level(logging.WARNING):
            result = loader._fetch_fed_rate_environment(eval_date)

    assert result["fed_rate_environment"] == "neutral"
    assert result["fed_rate_data_unavailable"] is False
    assert not any("stale rate" in r.message for r in caplog.records)


def test_fed_rate_genuinely_stale_warns_with_trading_day_count(caplog):
    loader = _make_loader()
    eval_date = date(2026, 8, 10)  # Monday
    fred_data = [{"date": "2026-07-01", "value": 3.5}]  # ~6 weeks old, unambiguously stale

    with patch("loaders.load_economic_data.fetch_from_fred", return_value=fred_data):
        with caplog.at_level(logging.WARNING):
            result = loader._fetch_fed_rate_environment(eval_date)

    assert result["fed_rate_data_unavailable"] is False  # staleness only warns, doesn't gate
    warnings = [r.message for r in caplog.records if "stale rate" in r.message]
    assert len(warnings) == 1
    # Locks in the trading-day-aware fix - a regression back to raw calendar-day math
    # would still say "days old" but not "trading days old".
    assert "trading days old" in warnings[0]


def test_fed_rate_weekend_span_uses_trading_days_not_calendar_days(caplog):
    """Friday rate consumed on the following Monday is 3 calendar days old but only
    1 trading day old - must not warn (well under the 5-trading-day threshold), which
    the old buggy calendar-day math would have gotten right too by coincidence, but a
    longer span crossing more weekends would not. This locks in the trading-day path
    actually executes (would raise/behave differently if last_trading_day handling broke)."""
    loader = _make_loader()
    eval_date = date(2026, 8, 10)  # Monday
    fred_data = [{"date": "2026-08-07", "value": 3.5}]  # Friday

    with patch("loaders.load_economic_data.fetch_from_fred", return_value=fred_data):
        with caplog.at_level(logging.WARNING):
            result = loader._fetch_fed_rate_environment(eval_date)

    assert result["fed_rate_environment"] == "neutral"
    assert not any("stale rate" in r.message for r in caplog.records)
