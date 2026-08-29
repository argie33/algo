#!/usr/bin/env python3
"""Regression test (2026-08-29, goal: "full data" audit continuation): YieldCurveFetcher.fetch()
used to pass an empty dict straight through when economic_data had zero T10Y2Y rows for the
requested range - _fetch_yield_curve_data's own docstring documents this as its normal
"no data for this period" outcome, not an error, so no exception was raised and no reason was
ever attached to the empty dict.

load_market_status_daily.py's caller only had `not yield_data` (an empty dict is falsy) to
detect this, and its own `yield_data.get("reason")` lookup found nothing, so it fell back to the
generic "yield_curve_fetcher_returned_unavailable_without_reason" placeholder - live-confirmed on
5 real market_health_daily dates (2026-08-05/06/07/14/28) even though economic_data.T10Y2Y now
has real rows for every one of them (a same-day loader-ordering race against economic_data at
the time those rows were written, not a permanent gap).

Fixed: fetch() now attaches a specific, aggregatable reason
("no_t10y2y_data_for_range:{start}_{end}") whenever the underlying query returns zero rows, so
the generic placeholder is never needed for this path. Uses this codebase's "prefix:suffix"
dynamic-reason convention (matching e.g. sic_code_unmapped:700) rather than a free-form sentence,
so lambda/api/routes/scores.py's _categorize_reason() and scripts/audit_unavailable_reasons.py
(both of which group on reason.split(":")[0]) aggregate every date range under one base string
instead of treating each distinct range as its own uncategorized reason.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.market_health_fetchers import YieldCurveFetcher


class TestYieldCurveFetcherEmptyResultGetsSpecificReason:
    def test_empty_query_result_returns_specific_reason_not_bare_dict(self) -> None:
        fetcher = YieldCurveFetcher()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # no T10Y2Y rows for this range

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cursor
            result = fetcher.fetch(date(2026, 8, 5), date(2026, 8, 5))

        assert result["data_unavailable"] is True
        assert result["reason"] == "no_t10y2y_data_for_range:2026-08-05_2026-08-05"
        assert result["reason"].split(":")[0] == "no_t10y2y_data_for_range"

    def test_non_empty_result_passes_through_unchanged(self) -> None:
        fetcher = YieldCurveFetcher()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(date(2026, 8, 5), 0.42)]

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.return_value = mock_cursor
            result = fetcher.fetch(date(2026, 8, 5), date(2026, 8, 5))

        assert "data_unavailable" not in result
        assert result["2026-08-05"]["yield_spread"] == 0.42
