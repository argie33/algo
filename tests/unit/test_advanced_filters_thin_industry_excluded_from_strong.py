"""Regression test: thin-sample industries must not qualify as "strong" (top-quartile).

company_profile.industry is ~391 narrow SIC-style buckets live, nearly half with <5 stocks
(58 with exactly 1). An industry's avg_score/momentum_score there is one stock's
composite_score on a given day, not a real momentum read - yet _industry_momentum_score()
awards the full momentum_industry weight to every stock sharing that industry label when it
lands in the top quartile by momentum_score. Without a sample-size floor, a single lucky/unlucky
stock in a 1-2 company "industry" can hand every peer a real trading-signal point swing driven
by noise, and can also crowd a genuinely well-sampled industry out of the top-quartile cutoff.

Fixed in load_market_context(): the top-quartile cutoff is now computed only over industries
with stock_count >= MIN_INDUSTRY_STOCK_COUNT_FOR_STRONG. Thin industries stay in
_industry_full_ranking (so they still score 0, not raise) but can never enter _strong_industries.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def _mock_cursor(
    sector_rows: list[tuple[Any, ...]],
    industry_rows: list[tuple[Any, ...]],
    sentiment_row: tuple[Any, ...] | None = None,
) -> MagicMock:
    cur = MagicMock()
    # load_market_context calls execute/fetchall in order: sectors, industries, then
    # execute/fetchone for aaii_sentiment.
    cur.fetchall.side_effect = [sector_rows, industry_rows]
    cur.fetchone.return_value = sentiment_row
    return cur


def test_thin_industry_excluded_from_strong_but_stays_in_full_ranking() -> None:
    # "Dairy Products" has the single highest momentum_score (noise from n=1) and would win the
    # top-quartile slot under the old all-industries cutoff; "Real Software" is well-sampled
    # (50 stocks) but ranks just below it.
    industry_rows = [
        ("Dairy Products", 95.0, 1),
        ("Real Software", 70.0, 50),
        ("Carpets & Rugs", 60.0, 2),
        ("Regional Banks", 50.0, 40),
    ]
    sector_rows = [("Technology", 1, 60.0)]
    cur = _mock_cursor(sector_rows, industry_rows)

    filters = AdvancedFilters(dict(BASE_CONFIG))
    with patch("algo.signals.advanced_filters.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = cur
        filters.load_market_context(date(2026, 8, 21))

    strong_industries = filters._strong_industries
    assert strong_industries is not None
    assert "Dairy Products" not in strong_industries
    assert "Carpets & Rugs" not in strong_industries
    assert "Real Software" in strong_industries

    # Thin industries are still known (score 0), not a hard-fail data problem.
    assert filters._industry_momentum_score("Dairy Products") == 0.0
    assert filters._industry_momentum_score("Real Software") > 0.0
