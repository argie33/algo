"""Regression test for the 2026-08-17 total_debt mislabeling fix (migration 1204) and its
lease-liability follow-up (migration 1205).

sec_valuations.total_debt used to be sourced from annual_balance_sheet.total_liabilities
(every non-debt liability included: accounts payable, deferred revenue, accrued expenses,
pensions, leases) instead of any real debt concept - live-confirmed against SEC EDGAR and the
local DB: AAPL FY2025 real long_term_debt = $90.7B vs the old total_debt = $285.5B (exactly
total_liabilities for that year). Fixed (migration 1204) to sum long_term_debt + short_term_debt
from annual_balance_sheet instead, then (migration 1205, same session) extended to also include
operating_lease_liability + finance_lease_liability - post-ASC 842 capitalized lease liabilities
that long_term_debt/short_term_debt never captured (live-confirmed via AAPL's real companyfacts
JSON: neither lease concept overlaps LongTermDebt).

This test mocks the DB layer to prove the query no longer reads total_liabilities into
total_debt, and that all four real debt components (long-term debt, short-term debt, operating
lease liability, finance lease liability) are summed correctly with any missing component
treated as 0, not as a reason to null out the whole figure.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in matching fetch_incremental's real query order
    for a symbol with a directly-usable reported share count (skips every shares_out fallback
    query branch).

    FIXED 2026-08-18 (missing factor inputs audit, continued): fetchall() used to be a single
    static response reused for every call, correct only for the FIRST fetchall() (income_rows).
    The 2026-08-18 DCF 3-year-average-FCF fallback (load_sec_valuations.py) added a SECOND
    fetchall() call (cash_rows: up to 3 years of operating_cash_flow/capex/dividends_paid) -
    live-confirmed this reused the same 9-column income_rows tuple for that call too, so
    `ocf, capex, dividends_paid = cash_rows[0]` crashed with "too many values to unpack
    (expected 3)" on every real symbol (caught by the loader's own ValueError handler, silently
    turning every fetch_incremental() call into a data_invalid marker - this test's assertions
    were never actually exercising the real code path). Made fetchall() sequential like
    fetchone() so the second call gets cash_rows-shaped data instead.
    """

    def __init__(
        self,
        fetchone_results: list[tuple[Any, ...]],
        cash_rows: list[tuple[Any, ...]] | None = None,
    ) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        # income_rows: (fiscal_year, revenue, net_income, eps, operating_income, pretax_income,
        # depreciation_expense, amortization_expense, shares_outstanding_basic, income_tax_expense)
        income_rows = [
            (
                2026,
                1_000_000_000.0,
                100_000_000.0,
                2.0,
                150_000_000.0,
                120_000_000.0,
                10_000_000.0,
                5_000_000.0,
                1_000_000_000.0,  # shares_outstanding_basic (> MIN_PLAUSIBLE_SHARES_OUTSTANDING)
                20_000_000.0,
            )
        ]
        # cash_rows: (operating_cash_flow, capex, dividends_paid) x up to 3 fiscal years -
        # defaults to the same single-year figures the old hardcoded fetchone "cash_row" used,
        # so callers that don't care about the 3-year DCF average keep the same effective values.
        self._fetchall_results = [
            income_rows,
            cash_rows if cash_rows is not None else [(80_000_000.0, 10_000_000.0, None)],
        ]
        self._fetchall_idx = 0

    def execute(self, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


class TestTotalDebtNotTotalLiabilities:
    def test_total_debt_sums_all_four_real_debt_components(self) -> None:
        loader = _make_loader()

        # Order matches fetch_incremental's real query sequence: total_debt/total_cash/ebitda
        # (MOVED 2026-08-19 to compute before the shares_outstanding/price gates, since none of
        # the three depend on shares or price) - cash_row2 (cash_and_equivalents), debt_row (long_
        # term_debt, short_term_debt, operating_lease_liability, finance_lease_liability) - then
        # price, balance_row (stockholders_equity). [cash_rows is a fetchall(), not a fetchone() -
        # see _FakeCursor].
        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (
                20_000_000.0,  # long_term_debt - real debt
                5_000_000.0,  # short_term_debt - real debt
                8_000_000.0,  # operating_lease_liability - real debt (S&P/Moody's adjusted-debt convention)
                2_000_000.0,  # finance_lease_liability - real debt
            ),
            (50.0,),  # price_daily.close
            (500_000_000.0,),  # annual_balance_sheet.stockholders_equity
        ]
        fake_cursor = _FakeCursor(fetchone_results)

        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
            result = loader.fetch_incremental("TESTCO", None)

        assert len(result) == 1
        row = result[0]
        # Real debt = long_term_debt + short_term_debt + operating_lease_liability +
        # finance_lease_liability = 35,000,000 - NOT total_liabilities (never even queried
        # here; a regression back to reading total_liabilities would either crash on a
        # column-count mismatch or silently pick up a wildly different, much larger figure
        # than this test's fixture provides).
        assert row["total_debt"] == 35_000_000.0

    def test_total_debt_treats_missing_component_as_zero_not_null(self) -> None:
        """A company with real long-term debt but no leases at all still gets a real
        total_debt (leases missing = 0 contribution), not a NULL just because 2 of 4
        components are absent."""
        loader = _make_loader()

        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (
                20_000_000.0,  # long_term_debt
                5_000_000.0,  # short_term_debt
                None,  # operating_lease_liability - not reported
                None,  # finance_lease_liability - not reported
            ),
            (50.0,),
            (500_000_000.0,),
        ]
        fake_cursor = _FakeCursor(fetchone_results)

        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
            result = loader.fetch_incremental("TESTCO3", None)

        assert len(result) == 1
        row = result[0]
        assert row["total_debt"] == 25_000_000.0

    def test_total_debt_none_when_no_debt_column_present(self) -> None:
        """A company with none of the 4 debt/lease concepts reported gets an honest NULL,
        not a fabricated $0 or a fallback to some unrelated liabilities figure."""
        loader = _make_loader()

        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (None, None, None, None),  # debt_row: nothing reported
            (50.0,),
            (500_000_000.0,),
        ]
        fake_cursor = _FakeCursor(fetchone_results)

        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
            result = loader.fetch_incremental("TESTCO2", None)

        assert len(result) == 1
        row = result[0]
        assert row["total_debt"] is None

    def test_total_debt_zero_preserved_not_collapsed_to_none(self) -> None:
        """FIXED 2026-08-18 (AA live-confirmed): a genuinely debt-free fiscal year (a real,
        reported short_term_debt=0 with the other 3 components NULL) used to hit
        `float(total_debt) if total_debt else None` downstream - 0.0 is falsy in Python, so
        this silently coerced a real "this company has zero debt" answer into the same
        "missing_sec_data" NULL as a company with no debt data at all. Must store the real 0."""
        loader = _make_loader()

        fetchone_results = [
            (30_000_000.0,),  # cash_and_equivalents
            (None, 0.0, None, None),  # debt_row: only short_term_debt reported, and it's 0
            (50.0,),
            (500_000_000.0,),
        ]
        fake_cursor = _FakeCursor(fetchone_results)

        fake_ctx = MagicMock()
        fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
        fake_ctx.__exit__ = MagicMock(return_value=False)

        with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
            result = loader.fetch_incremental("TESTCO3", None)

        assert len(result) == 1
        row = result[0]
        assert row["total_debt"] == 0.0
