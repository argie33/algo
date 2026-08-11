"""Regression test: SectorIndustryDailyLoader.fetch_incremental() must fall back to the last
completed trading day when today's price_daily coverage isn't loaded yet, instead of silently
computing a near-empty sector_performance "success" for today().

Bug found 2026-08-10 (live-reproduced, 11-day real gap): this loader is scheduled in the
"morning" PIPELINES list (runs before market close), but hardcoded target_date=date.today() -
which only has real EOD price_daily coverage after today's close loads. Confirmed live:
price_daily had 1 row for today vs ~4900 for a normal trading day, so the sector_performance
day-over-day INNER JOIN matched almost nothing ("Inserted 1 sector performance row" instead of
~388), with no exception - sector_ranking/industry_ranking are computed from stock_scores, not
today's price_daily, so they kept succeeding normally and the existing zero-rows fail-fast
(which only fires when ALL THREE tables are empty) never caught it. sector_performance sat
frozen at 11 real days stale while sector_ranking was fresh.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_sector_industry_daily import SectorIndustryDailyLoader


def _make_loader() -> SectorIndustryDailyLoader:
    loader = SectorIndustryDailyLoader.__new__(SectorIndustryDailyLoader)
    return loader


def test_falls_back_to_last_completed_trading_day_when_today_has_no_coverage():
    loader = _make_loader()
    mock_cur = MagicMock()
    mock_cur.rowcount = 5
    # today_count = 1, well below MIN_EXPECTED_SYMBOLS - triggers the fallback.
    mock_cur.fetchone.return_value = (1,)

    with (
        patch(
            "loaders.load_sector_industry_daily.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 8, 7),
        ) as mock_get_prev_day,
        patch("loaders.load_sector_industry_daily.date") as mock_date,
        patch("loaders.load_sector_industry_daily.DatabaseContext") as mock_db_ctx,
    ):
        mock_date.today.return_value = date(2026, 8, 10)
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        loader.fetch_incremental("market", None)

        # get_previous_trading_day is called at least twice: once to resolve the fallback
        # target_date (from today - 1 day), once more for the actual prev_date (from the
        # resolved target_date - 1 day) - both must be real trading-day-anchored, not today().
        assert mock_get_prev_day.call_count >= 2

        # The INSERT statements' bound params must use the fallback date (2026-08-07), not
        # today() (2026-08-10) - check the sector_performance INSERT's params.
        insert_calls = [
            call for call in mock_cur.execute.call_args_list if "INSERT INTO sector_performance" in str(call)
        ]
        assert insert_calls, "sector_performance INSERT was never executed"
        params = insert_calls[0][0][1]
        assert date(2026, 8, 10) not in params, (
            "sector_performance INSERT used today()'s date despite today's price_daily "
            "having near-zero coverage - should have fallen back to the last completed "
            "trading day instead."
        )


def test_uses_today_directly_when_coverage_is_adequate():
    loader = _make_loader()
    mock_cur = MagicMock()
    mock_cur.rowcount = 5
    # today_count = 4900, well above MIN_EXPECTED_SYMBOLS - no fallback needed.
    mock_cur.fetchone.return_value = (4900,)

    with (
        patch(
            "loaders.load_sector_industry_daily.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 8, 7),
        ),
        patch("loaders.load_sector_industry_daily.date") as mock_date,
        patch("loaders.load_sector_industry_daily.DatabaseContext") as mock_db_ctx,
    ):
        mock_date.today.return_value = date(2026, 8, 10)
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        loader.fetch_incremental("market", None)

        insert_calls = [
            call for call in mock_cur.execute.call_args_list if "INSERT INTO sector_performance" in str(call)
        ]
        assert insert_calls, "sector_performance INSERT was never executed"
        params = insert_calls[0][0][1]
        assert date(2026, 8, 10) in params, (
            "today() has adequate price_daily coverage - should use it directly, not fall back unnecessarily."
        )
