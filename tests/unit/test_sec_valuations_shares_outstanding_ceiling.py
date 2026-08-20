"""Regression test for a 2026-08-18 live crash: load_sec_valuations.py's derived-shares-out
fallback (`shares = net_income / eps`) had a MIN_PLAUSIBLE_SHARES_OUTSTANDING floor but no
matching ceiling.

Live-caught via NMR (Nomura Holdings, a JPY-reporting IFRS filer - JPY is FX-CONVERTED, not
rejected outright, unlike KRW/VND): a currency-scale mismatch between net_income (converted)
and eps (apparently not converted the same way) produced a derived share count of
2,942,280,410,000,000 - NUMERIC(15,0) couldn't even hold the value, aborting the whole COPY
batch and rolling back 15 symbols' worth of otherwise-good corrections, not just NMR's.

Fixed by adding MAX_PLAUSIBLE_SHARES_OUTSTANDING (100 billion - generous enough to never reject
a genuine value) as a ceiling alongside the existing floor, applied everywhere the floor already
was: the primary reported value, the derived net_income/eps fallback, and every SQL-based
fallback tier (older fiscal year, company_info_sec, diluted, dei cover-page).
"""

from typing import Any
from unittest.mock import MagicMock, patch

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


class TestSharesOutstandingCeiling:
    def test_currency_mismatched_derived_shares_out_rejected_not_crashed(self) -> None:
        # NMR-shaped: no reported shares_outstanding_basic tagged (None, falls to the derived
        # path), and net_income/eps whose ratio is wildly implausible (currency-scale mismatch)
        # - would derive ~2.94e15 shares, far past MAX_PLAUSIBLE_SHARES_OUTSTANDING.
        income_rows = [
            (2026, 1_000_000_000.0, 50_000_000_000.0, 0.000017, None, None, None, None, None, None),
        ]
        # No reported/older/company_info_sec/diluted/dei fallback has anything usable either -
        # shares_out should end up None, not the absurd derived value. total_debt/total_cash
        # (MOVED 2026-08-19 to compute before the shares_outstanding gate) are queried first,
        # unconditionally, regardless of how shares_out resolves.
        fetchone_results = [
            (None,),  # cash_and_equivalents
            (None, None, None, None),  # debt_row
            (None,),  # older shares_outstanding_basic fallback query
            (None,),  # company_info_sec fallback query
            (None,),  # shares_outstanding_diluted fallback query
            (None,),  # shares_outstanding_dei fallback query
        ]

        result = _run_fetch_incremental("NMR", income_rows, fetchone_results)

        row = result[0]
        # No plausible share count anywhere -> market_cap (and everything derived from it)
        # comes back as an honest unavailable marker, not a fabricated/overflowing value.
        assert row.get("data_unavailable") is True
        assert row.get("market_cap") is None

    def test_normal_derived_shares_out_still_computes(self) -> None:
        # A genuinely plausible net_income/eps ratio (a real mid-cap) must still work.
        income_rows = [
            (2026, 1_000_000_000.0, 100_000_000.0, 2.0, None, None, None, None, None, None),
        ]
        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            (35.26,),  # price_daily.close
            (500_000_000.0,),  # stockholders_equity
        ]

        result = _run_fetch_incremental("NORMALCO", income_rows, fetchone_results)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row["market_cap"] == round(35.26 * 50_000_000.0, 2)
