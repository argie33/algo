"""Regression test for a 2026-09-03 fix (goal session continuation, same eps_scale_mismatch
sweep) to load_sec_valuations.py's RECENT_REVERSE_SPLITS_SHARES_OUT.

A real REVERSE split creates the mirror-image problem to RECENT_STOCK_SPLITS: SEC's cover-page
shares_outstanding_basic is "as of filing date," so for a filer whose most recent filing
predates a reverse split that happened only days ago, the stored share count is still the
stale PRE-split (too-large) figure while current_price is live/post-split - producing a
market_cap wildly too big, correctly rejected by _sanity_check_market_cap as
shares_outstanding_scale_mismatch.

Live-confirmed via PPCB (Propanc Biopharma, 1-for-25 reverse split effective 2026-05-18) and
NXTT (Next Technology Holding, 1-for-100 reverse split effective 2026-08-10): dividing
shares_out by the confirmed ratio and multiplying by the live price matched a fresh live
yfinance market cap fetch to the DOLLAR (2,323,938.62 vs 2,323,938.0; 8,734,664.19 vs
8,734,664.0) - the strongest confirmation this kind of cross-check can give.

Fixture shape copied from the existing, verified AMRN fixture in
test_sec_valuations_domestic_filer_ads_ratio_override_20260831.py - only the final
yfinance_snapshot fetchone result and the override symbol/ratio differ per test.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import RECENT_REVERSE_SPLITS_SHARES_OUT, SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, params: Any = None) -> None:
        pass

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
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


# PPCB-shaped: domestic filer (is_foreign_private_issuer=False), pre-split cover-page share
# count resolves via the first ("reported shares_outstanding_basic") tier.
_PPCB_SHAPED_INCOME_ROWS = [
    (2026, 2_000_000.0, -3_000_000.0, -0.05, None, None, None, None, 56_959_280.0, None, False),
]


class TestRecentReverseSplitsSharesOut:
    def test_ppcb_shares_out_divided_by_reverse_split_ratio(self) -> None:
        fetchone_results = [
            (1_000_000.0,),  # cash_and_equivalents
            (500_000.0, None, None, None),  # debt_row
            None,  # has_dual_class_sibling check - no matching row
            (None, None),  # freshest shares_outstanding_basic check - no fresher row
            (None,),  # company_info_sec cross-check
            (1.02,),  # price_daily.close
            (5_000_000.0,),  # stockholders_equity
            (1.0,),  # beta
            (4.5,),  # risk_free_rate
            (20.0,),  # current VIX
            (20.0,),  # long-run avg VIX
            None,  # net borrowing check
            (2_323_938.0, None),  # yfinance_snapshot - agrees with the split-adjusted market cap
        ]

        result = _run_fetch_incremental("PPCB", _PPCB_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 56_959_280.0 / 25.0
        assert row["market_cap"] == 1.02 * (56_959_280.0 / 25.0)
        assert row["data_unavailable"] is False
        assert row["reason"] is None

    def test_other_domestic_symbol_unaffected(self) -> None:
        """The override must only apply to registered symbols - a similarly-shaped domestic
        filer with the same real share count must be untouched."""
        fetchone_results = [
            (1_000_000.0,),
            (500_000.0, None, None, None),
            None,
            (None, None),
            (None,),
            (1.02,),
            (5_000_000.0,),
            (1.0,),
            (4.5,),
            (20.0,),
            (20.0,),
            None,
            (1.02 * 56_959_280.0, None),  # yfinance_snapshot agrees with the UNadjusted value
        ]

        result = _run_fetch_incremental("NOTPPCB", _PPCB_SHAPED_INCOME_ROWS, fetchone_results)

        row = result[0]
        assert row["shares_outstanding"] == 56_959_280.0
        assert row["market_cap"] == 1.02 * 56_959_280.0

    def test_qnrx_registered_with_confirmed_ads_ratio(self) -> None:
        # QNRX: SEC 8-K confirms ADS ratio changed 1:1 -> 1:35, effective 2025-04-09 -
        # cross-checked against a live yfinance market cap fetch (matched within 2.4%).
        assert RECENT_REVERSE_SPLITS_SHARES_OUT["QNRX"] == 35.0
