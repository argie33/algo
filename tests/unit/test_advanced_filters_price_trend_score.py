"""Verifies AdvancedFilters._price_trend_score() scoring logic.

Current scoring (as of 2026-07-28):
- +2 pts if 5-day return positive
- +2 pts if 20-day return positive

Max score: 4 pts (capped at filter weight)

REMOVED 2026-07-28: a +1 "weekly BUY alignment" bonus that queried buy_sell_weekly, a
table with no active loader (confirmed via git history - no load_buy_sell_weekly.py has
ever existed in this codebase) and data frozen since 2026-05-22. Its 30-day lookback
window could structurally never match that stale data again, so the bonus had been
silently, permanently contributing exactly 0 for every symbol - removing it is a
verified no-op for actual scoring output, not a behavior change. See
algo/signals/advanced_filters.py::_price_trend_score's docstring for the full history.
"""

from datetime import date
from unittest.mock import Mock, patch

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


def test_price_trend_score_no_longer_queries_buy_sell_weekly():
    """buy_sell_weekly must not be queried at all - its loader has been gone since
    2026-05-22 and the bonus it fed could never fire (see module docstring)."""
    filters = _filters()
    cur = Mock()
    cur.execute = Mock()

    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        filters._price_trend_score("AAPL", date(2026, 7, 21), cur)

    assert not cur.execute.called, "no DB query should run - the weekly bonus was removed, not just gated"


def test_price_trend_score_both_positive_returns_four():
    """r5=positive, r20=positive: score = 2+2 = 4."""
    filters = _filters()
    cur = Mock()

    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 4.0


def test_price_trend_score_one_positive_returns_two():
    """r5=positive, r20=negative: score = 2."""
    filters = _filters()
    cur = Mock()

    with patch.object(filters, "_period_return", side_effect=[1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 2.0


def test_price_trend_score_neither_positive_returns_zero():
    """r5=negative, r20=negative: score = 0."""
    filters = _filters()
    cur = Mock()

    with patch.object(filters, "_period_return", side_effect=[-1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 0.0
