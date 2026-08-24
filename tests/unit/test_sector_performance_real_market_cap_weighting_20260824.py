"""Regression test: sector_performance must weight by real market cap
(close * shares_outstanding), not raw closing price.

Bug found 2026-08-24 (finance-accuracy "no cheats" goal-session audit): the module's own
docstring already claimed "weighted by market cap", but the actual query used
`pd_today.close as market_cap_proxy` - raw share price - as the weight. Price has no
relationship to actual market cap: a $500 stock with 10M shares outstanding ($5B company)
was weighted identically to a $500 stock with 10B shares ($5T company). No major real-world
index uses raw-price weighting except the Dow, a well-known historical anachronism, not a
methodology to emulate.

Fixed by joining company_info_sec.shares_outstanding and computing a real
`market_cap = close * shares_outstanding`. Symbols with missing/invalid shares_outstanding
drop out of the weighted SUMs (NULL propagates) but still count toward `stock_count`,
preserving that field's existing "sector breadth" meaning.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_sector_industry_daily import SectorIndustryDailyLoader


def _make_loader() -> SectorIndustryDailyLoader:
    loader = SectorIndustryDailyLoader.__new__(SectorIndustryDailyLoader)
    return loader


def test_sector_performance_query_weights_by_real_market_cap_not_raw_price():
    loader = _make_loader()
    mock_cur = MagicMock()
    mock_cur.rowcount = 5
    mock_cur.fetchone.return_value = (9999,)

    executed_queries = []

    def _execute(query, *args, **kwargs):
        executed_queries.append(query)

    mock_cur.execute.side_effect = _execute

    with (
        patch(
            "loaders.load_sector_industry_daily.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 8, 6),
        ),
        patch("loaders.load_sector_industry_daily.DatabaseContext") as mock_db_ctx,
    ):
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        loader.fetch_incremental("market", None)

    sector_performance_query = next(q for q in executed_queries if "INSERT INTO sector_performance" in q)

    # Must compute real market cap from shares_outstanding, not use raw close as the weight.
    assert "c.shares_outstanding" in sector_performance_query
    assert "pd_today.close * c.shares_outstanding" in sector_performance_query
    assert "market_cap_proxy" not in sector_performance_query
    # Weighted-average SUMs must use the real market_cap column.
    assert "SUM(daily_return * market_cap)" in sector_performance_query
    assert "NULLIF(SUM(market_cap), 0)" in sector_performance_query
    # stock_count must still count every symbol with a valid return, not just cap-weighted
    # ones - the fix must not silently narrow this field's meaning.
    assert "COUNT(DISTINCT symbol) as stock_count" in sector_performance_query
