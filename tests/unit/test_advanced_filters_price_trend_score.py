"""Verifies AdvancedFilters._price_trend_score() scoring logic.

Current scoring (restored 2026-07-21+):
- +2 pts if 5-day return positive
- +2 pts if 20-day return positive
- +1 pt bonus if also a BUY signal on weekly timeframe (very strong combo)

Max score: 5 pts (capped at filter weight)
"""

from datetime import date
from unittest.mock import MagicMock, Mock, patch

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def _filters() -> AdvancedFilters:
    return AdvancedFilters(dict(BASE_CONFIG))


def test_price_trend_score_does_query_buy_sell_weekly():
    """Weekly alignment bonus is evaluated: queries buy_sell_weekly."""
    filters = _filters()
    cur = Mock()
    cur.execute = Mock()
    cur.fetchone.return_value = None  # No weekly BUY signal

    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        filters._price_trend_score("AAPL", date(2026, 7, 21), cur)

    # Verify that buy_sell_weekly IS queried (restored)
    assert any("buy_sell_weekly" in str(call) for call in cur.execute.call_args_list)


def test_price_trend_score_both_positive_no_weekly_returns_four():
    """r5=positive, r20=positive, no weekly BUY: score = 2+2 = 4."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = None  # No weekly BUY signal

    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 4.0


def test_price_trend_score_both_positive_with_weekly_returns_five():
    """r5=positive, r20=positive, weekly BUY: score = 2+2+1 = 5."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = (1,)  # Weekly BUY signal found

    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 5.0


def test_price_trend_score_one_positive_no_weekly_returns_two():
    """r5=positive, r20=negative, no weekly: score = 2."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = None

    with patch.object(filters, "_period_return", side_effect=[1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 2.0


def test_price_trend_score_one_positive_with_weekly_returns_three():
    """r5=positive, r20=negative, weekly BUY: score = 2+1 = 3."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = (1,)  # Weekly BUY found

    with patch.object(filters, "_period_return", side_effect=[1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 3.0


def test_price_trend_score_neither_positive_no_weekly_returns_zero():
    """r5=negative, r20=negative, no weekly: score = 0."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = None

    with patch.object(filters, "_period_return", side_effect=[-1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 0.0


def test_price_trend_score_neither_positive_with_weekly_returns_one():
    """r5=negative, r20=negative, weekly BUY: score = 1 (bonus only)."""
    filters = _filters()
    cur = Mock()
    cur.fetchone.return_value = (1,)  # Weekly BUY found (bonus still applies)

    with patch.object(filters, "_period_return", side_effect=[-1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 1.0
