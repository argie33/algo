"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data"/implausible-
values sweep) to load_sec_valuations.py's RECENT_STOCK_SPLITS/_split_adjusted_eps.

Live-confirmed via BKNG (Booking Holdings): a real 25-for-1 stock split effective 2026-04-02
left FY2025's annual EPS ($166.52, pre-split) being compared against the live post-split
current_price ($195.13) - pe_ratio computed as ~1.17 vs yfinance's real ~29x, correctly
rejected by the existing >10x sanity check as `eps_scale_mismatch`, but for the wrong reason:
the EPS fed into that check was on the wrong share-count basis, not genuinely SEC-incomplete
data. Dividing a pre-split fiscal year's EPS by the confirmed split ratio before the sanity
check runs resolves a real, plausible pe_ratio instead of leaving it permanently null.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader, _split_adjusted_eps


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]
) -> tuple[list[dict[str, Any]], _RecordingCursor]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        result = loader.fetch_incremental(symbol, None)
    return result, fake_cursor


class TestSplitAdjustedEpsHelper:
    def test_pre_split_fiscal_year_divided_by_ratio(self) -> None:
        assert _split_adjusted_eps("BKNG", 166.52, 2025) == pytest.approx(166.52 / 25.0)

    def test_post_split_fiscal_year_untouched(self) -> None:
        # A fiscal year ENDING on/after the split's effective date already reflects the
        # post-split weighted-average share count in its own as-filed EPS (ASC 260).
        assert _split_adjusted_eps("BKNG", 6.66, 2026) == 6.66

    def test_unregistered_symbol_untouched(self) -> None:
        assert _split_adjusted_eps("ONC", 166.52, 2025) == 166.52

    def test_none_eps_or_fiscal_year_passthrough(self) -> None:
        assert _split_adjusted_eps("BKNG", None, 2025) is None
        assert _split_adjusted_eps("BKNG", 166.52, None) == 166.52


# BKNG-shaped: FY2025 (pre-split) annual EPS=166.52, current_price=195.13 (post-split, live).
_BKNG_EPS_SHAPED_INCOME_ROWS = [
    (2025, 20_000_000_000.0, 4_000_000_000.0, 166.52, None, None, None, None, 40_000_000.0, None),
]


class TestBkngStockSplitResolvesPeRatio:
    def test_pre_split_eps_adjusted_produces_plausible_pe_ratio(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no matching row
            (None, None),  # freshest shares_outstanding_basic check - no fresher row
            (39_000_000.0,),  # company_info_sec shares cross-check - agrees, no override
            (195.13,),  # price_daily.close (live, post-split)
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check - no adjacent-year debt data
            (None, 29.0),  # yfinance_snapshot pe_ratio - real, post-split-consistent
        ]

        result, _ = _run_fetch_incremental("BKNG", _BKNG_EPS_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        expected_eps = 166.52 / 25.0
        assert row["pe_ratio"] == round(195.13 / expected_eps, 2)
        assert row.get("reason") != "eps_scale_mismatch"
