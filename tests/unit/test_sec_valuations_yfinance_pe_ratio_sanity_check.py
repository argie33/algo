"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit, ONC follow-up) to
load_sec_valuations.py: pe_ratio doesn't depend on shares_outstanding (current_price / ttm_eps
only), so the market_cap sanity check (see test_sec_valuations_yfinance_market_cap_sanity_check.py)
correctly leaves it untouched - but that also means a separately-mis-scaled ttm_eps (a different
SEC concept, same underlying class of per-filing XBRL scale bug) survives completely unguarded.

Live-confirmed: ONC (BeOne Medicines) still shows pe_ratio=1884.30 after the market_cap fix, vs
yfinance's pe_ratio=67.58 for the same company - a ~28x gap. A DB-wide scan found 38 symbols
with a >10x pe_ratio mismatch against yfinance_snapshot.pe_ratio.

Same validity-check-only discipline as market_cap (never a yfinance value substitution): nulls
pe_ratio and its sole dependent, peg_ratio, on a >10x disagreement.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None)]]
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


# ONC-shaped: current_price=376.86, mis-scaled ttm_eps=0.2 -> pe_ratio=1884.30 (real EPS would
# be ~5.58, giving pe_ratio~67.5, matching yfinance).
_ONC_EPS_SHAPED_INCOME_ROWS = [
    (2026, 1_500_000_000.0, 227_000_000.0, 0.2, None, None, None, None, 40_000_000.0, None),
]


class TestYfinancePeRatioSanityCheck:
    def test_large_mismatch_nulls_pe_and_peg_ratio_not_market_cap(self) -> None:
        fetchone_results = [
            (5_000_000.0,),  # cash_and_equivalents
            (1_000_000.0, None, None, None),  # debt_row
            (39_000_000.0,),  # company_info_sec shares cross-check - agrees, no override
            (376.86,),  # price_daily.close
            (60_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (None, 67.58),  # yfinance_snapshot: market_cap unavailable, pe_ratio=67.58 (real)
        ]

        result, cursor = _run_fetch_incremental("ONC", _ONC_EPS_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["pe_ratio"] is None
        assert row["peg_ratio"] is None
        # market_cap does not depend on ttm_eps - must survive untouched.
        assert row["market_cap"] == pytest.approx(376.86 * 40_000_000.0, rel=1e-9)
        assert row["reason"] == "eps_scale_mismatch"

        sanity_check_queries = [sql for sql in cursor.executed_sql if "FROM yfinance_snapshot" in sql]
        assert len(sanity_check_queries) == 1

    def test_no_yfinance_pe_ratio_leaves_result_untouched(self) -> None:
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            (39_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (None, None),  # yfinance_snapshot - nothing available for either field
        ]

        result, _ = _run_fetch_incremental("ONC2", _ONC_EPS_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["pe_ratio"] == round(376.86 / 0.2, 2)

    def test_agreeing_pe_ratios_within_10x_not_touched(self) -> None:
        fetchone_results = [
            (5_000_000.0,),
            (1_000_000.0, None, None, None),
            (39_000_000.0,),
            (376.86,),
            (60_000_000.0,),
            (1.0,),
            (4.5,),
            (None, 300.0),  # yfinance pe_ratio within 10x of the SEC-derived 1884.30
        ]

        result, _ = _run_fetch_incremental("ONC3", _ONC_EPS_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["pe_ratio"] == round(376.86 / 0.2, 2)
