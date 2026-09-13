"""Regression test: sector_ranking/industry_ranking must use the same canonical
investable-universe definition as the leaderboard (algo/signals/investable_universe.py),
not a narrower ad hoc `composite_score IS NOT NULL` check.

Gap found 2026-09-13 (/goal session, scores plan Item 2): live-verified 414 ETF/SPAC/
royalty-trust/structured-note/CEF/inactive symbols (~8% of the scored universe) were being
counted in sector_ranking/industry_ranking's stock_count/avg_score/current_rank, even though
none of them could ever appear on the actual leaderboard or get traded - the two ranking
CTEs never applied the leaderboard's investable-universe filter at all. Fixed by joining
stock_symbols and reusing investable_universe_conditions() in both CTEs.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.signals.investable_universe import investable_universe_conditions
from loaders.load_sector_industry_daily import SectorIndustryDailyLoader


def _make_loader() -> SectorIndustryDailyLoader:
    loader = SectorIndustryDailyLoader.__new__(SectorIndustryDailyLoader)
    return loader


def test_sector_and_industry_ranking_apply_investable_universe_filter() -> None:
    loader = _make_loader()
    mock_cur = MagicMock()
    mock_cur.rowcount = 5
    mock_cur.fetchone.return_value = (9999,)  # adequate price_daily coverage, no fallback

    with (
        patch(
            "loaders.load_sector_industry_daily.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 9, 12),
        ),
        patch("loaders.load_sector_industry_daily.DatabaseContext") as mock_db_ctx,
    ):
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        loader.fetch_incremental("market", None)

        expected_conditions = investable_universe_conditions("ss", "sy")
        for table in ("sector_ranking", "industry_ranking"):
            insert_calls = [call for call in mock_cur.execute.call_args_list if f"INSERT INTO {table}" in str(call)]
            assert insert_calls, f"{table} INSERT was never executed"
            sql = insert_calls[0][0][0]
            assert "JOIN stock_symbols sy ON sy.symbol = ss.symbol" in sql, (
                f"{table}'s CTE must join stock_symbols to apply the investable-universe filter"
            )
            assert expected_conditions in sql, (
                f"{table}'s CTE must reuse the shared investable_universe_conditions(), "
                f"not a narrower ad hoc filter that can silently drift from the leaderboard's"
            )
