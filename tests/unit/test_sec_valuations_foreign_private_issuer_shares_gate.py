"""Regression test for the 2026-08-19 fix (migration 1211, goal: "no SEC data"/missing
factor inputs audit): TSM (Taiwan Semiconductor, 1 ADS = 5 ordinary shares) showed
market_cap=$10.7 TRILLION and pe_ratio=304 - both ~5x too high - because the
net_income/EPS-derived shares_outstanding tier (and the reported/older-fiscal-year/diluted
tiers) read figures a foreign private issuer files in its home-market ordinary-share terms,
not the ADS-equivalent terms the US trading price is quoted in. Independently cross-checked
against yfinance's live sharesOutstanding (5,186,474,013, matching our raw count divided by
~5.000) and marketCap ($2.14T)/trailingPE (30.9) - confirms the ADS ratio and that the
derived figure was ~5x too high, not a guess.

is_foreign_private_issuer (company_info_sec, migration 1211) gates every share-count tier
that reads un-independently-verified home-market figures, leaving only the two tiers already
separately guarded to domestic forms only (company_info_sec.shares_outstanding's own dei
extraction, and annual_income_statement.shares_outstanding_dei via sec_statements.py).
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in - see the sibling fallback tests' _FakeCursor
    docstrings for why fetchall() must be sequential (income_rows first, then the DCF
    3-year-average-FCF fallback's cash_rows)."""

    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
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
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


class TestForeignPrivateIssuerSharesGate:
    def test_tsm_shaped_derived_shares_out_is_rejected_not_trusted(self) -> None:
        """The real TSM shape: real, plausible-looking net_income/eps that would derive a
        real-looking ~25.9B share count via the mathematical identity - but this filer is
        flagged foreign, so that derivation must not run at all. No other fallback has
        anything (company_info_sec's own dei extraction is separately guarded and correctly
        empty for this filer too) - result must be an honest unavailable marker, not the
        ~5x-inflated market cap."""
        income_rows = [
            (2024, 88_268_000_000.0, 35_301_100_000.0, 1.36, None, None, None, None, None, None, True),
        ]
        fetchone_results = [
            (None,),  # older-fiscal-year shares_outstanding_basic fallback - also gated off
            (None,),  # company_info_sec fallback (already independently guarded, empty)
            (None,),  # shares_outstanding_diluted fallback - also gated off
            (None,),  # shares_outstanding_dei fallback (already independently guarded, empty)
        ]

        result = _run_fetch_incremental("TSM", income_rows, fetchone_results)

        row = result[0]
        assert row.get("data_unavailable") is True
        assert row.get("market_cap") is None
        assert row.get("pe_ratio") is None

    def test_domestic_filer_same_shape_still_computes_normally(self) -> None:
        """Companion case: a domestic filer (is_foreign_private_issuer=False) with the exact
        same real net_income/EPS numbers must still use the derived-shares tier exactly as
        before - this fix must not become a blanket rejection."""
        income_rows = [
            (2024, 88_268_000_000.0, 35_301_100_000.0, 1.36, None, None, None, None, None, None, False),
        ]
        fetchone_results = [
            (30_000_000_000.0,),  # cash_and_equivalents
            (970_500_000.0, None, None, None),  # debt_row
            (413.41,),  # price_daily.close
            (500_000_000_000.0,),  # stockholders_equity
        ]

        result = _run_fetch_incremental("DOMESTICCO", income_rows, fetchone_results)

        row = result[0]
        assert not row.get("data_unavailable")
        # The derived-shares tier fired (not gated off) - market_cap lands near the
        # TSM-shaped raw figure this test intentionally mirrors (real production value was
        # $10.7T before the fix; small float-rounding slop is expected here, not asserted
        # bit-exact).
        assert row["market_cap"] == pytest.approx(10_730_755_699_264.71, rel=1e-9)

    def test_missing_company_info_sec_row_defaults_to_not_foreign(self) -> None:
        """A symbol with no company_info_sec row at all (LEFT JOIN finds nothing, NULL) must
        not be treated as foreign - default to the pre-existing (domestic) behavior rather
        than silently losing coverage for every symbol company_info_sec hasn't reached yet."""
        income_rows = [
            (2024, 1_000_000_000.0, 100_000_000.0, 2.0, None, None, None, None, None, None, None),
        ]
        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            (35.26,),  # price_daily.close
            (500_000_000.0,),  # stockholders_equity
        ]

        result = _run_fetch_incremental("NOROWCO", income_rows, fetchone_results)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row["market_cap"] == round(35.26 * 50_000_000.0, 2)
