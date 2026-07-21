"""Verifies AdvancedFilters._price_trend_score() no longer queries buy_sell_weekly.

That table has never had a loader (see algo/monitoring/pipeline_health.py's own
comment on this), so the "+1 weekly BUY alignment" bonus it fed could never
actually be awarded - it silently capped every symbol's price_trend_score at
4 of the configured 5-point weight. Removed 2026-07-21; this test locks in
that the dead query doesn't get reintroduced and that the score is now the
straightforward sum of the two reachable components.
"""

from datetime import date
from unittest.mock import MagicMock, patch

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


def test_price_trend_score_does_not_query_buy_sell_weekly():
    filters = _filters()
    cur = MagicMock()
    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        filters._price_trend_score("AAPL", date(2026, 7, 21), cur)

    for call in cur.execute.call_args_list:
        assert "buy_sell_weekly" not in call.args[0]


def test_price_trend_score_both_positive_returns_four():
    filters = _filters()
    cur = MagicMock()
    with patch.object(filters, "_period_return", side_effect=[1.0, 1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 4.0


def test_price_trend_score_one_positive_return_two():
    filters = _filters()
    cur = MagicMock()
    with patch.object(filters, "_period_return", side_effect=[1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 2.0


def test_price_trend_score_neither_positive_returns_zero():
    filters = _filters()
    cur = MagicMock()
    with patch.object(filters, "_period_return", side_effect=[-1.0, -1.0]):
        score = filters._price_trend_score("AAPL", date(2026, 7, 21), cur)
    assert score == 0.0
