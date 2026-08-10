"""Regression test: SectorIndustryDailyLoader.fetch_incremental() must not silently report
success when all 3 of its INSERT...SELECT statements match zero rows.

Bug found 2026-08-10 (flagged, not yet fixed, in a concurrent session's loader audit): the
function always `return []` regardless of how many rows the sector_performance/sector_ranking/
industry_ranking INSERTs actually wrote. `sector_ranking` is one of the 15 critical loaders
gating Phase 1 (utils/loader_priority.py) - a day where e.g. stock_scores.composite_score is
entirely NULL would make both ranking CTEs empty, all 3 cur.rowcount == 0, and this loader
would still report success with no exception and no failed status - identical to a healthy run
from every downstream consumer's perspective. Fixed by raising when total_rows == 0, matching
this same function's existing fail-fast convention for the previous-trading-day case (Session
291) just above it.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sector_industry_daily import SectorIndustryDailyLoader


def _make_loader() -> SectorIndustryDailyLoader:
    loader = SectorIndustryDailyLoader.__new__(SectorIndustryDailyLoader)
    return loader


def test_fetch_incremental_raises_when_all_three_inserts_write_zero_rows():
    loader = _make_loader()
    mock_cur = MagicMock()
    mock_cur.rowcount = 0
    # target_date coverage check (2026-08-10 fix): well above MIN_EXPECTED_SYMBOLS so the
    # today->fallback-date logic doesn't interfere with this test's own zero-rows scenario.
    mock_cur.fetchone.return_value = (9999,)

    with (
        patch(
            "loaders.load_sector_industry_daily.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 8, 6),
        ),
        patch("loaders.load_sector_industry_daily.DatabaseContext") as mock_db_ctx,
    ):
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        with pytest.raises(RuntimeError, match="All 3 INSERT statements matched 0 rows"):
            loader.fetch_incremental("market", None)


def test_fetch_incremental_succeeds_when_at_least_one_insert_writes_rows():
    loader = _make_loader()
    mock_cur = MagicMock()
    # target_date coverage check (2026-08-10 fix): well above MIN_EXPECTED_SYMBOLS so the
    # today->fallback-date logic doesn't interfere with this test's own zero-rows scenario.
    mock_cur.fetchone.return_value = (9999,)
    # First INSERT (sector_performance) writes rows, the other two don't - should NOT raise,
    # since a single empty table isn't necessarily this loader's fault (each has an
    # independent, legitimately-partial source query).
    mock_cur.rowcount = 0
    call_count = {"n": 0}

    def _execute(*args, **kwargs):
        call_count["n"] += 1
        # Call #1 is the new target_date coverage SELECT (2026-08-10 fix) - leave rowcount
        # alone for it. Call #2 is the sector_performance INSERT, give it rows.
        if call_count["n"] == 2:
            mock_cur.rowcount = 5
        elif call_count["n"] > 2:
            mock_cur.rowcount = 0

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

        result = loader.fetch_incremental("market", None)
        assert result == []
