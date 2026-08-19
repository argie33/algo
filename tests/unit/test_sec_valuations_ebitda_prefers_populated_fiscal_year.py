"""Regression test for the 2026-08-18 "no SEC data" audit finding: load_sec_valuations.py's
operating_income/pretax_income suffer the identical "premature fiscal year stub" gap already
fixed for revenue and earnings_per_share (see the sibling
test_sec_valuations_revenue/eps_prefers_populated_fiscal_year.py files) - same anchor row, same
root cause, but silently killed ebitda/ev_ebitda instead.

Live-confirmed on HG (Hamilton Insurance Group, a real NYSE-listed Bermuda insurer): FY2026's
annual_income_statement row has real net_income=$217.032M but BOTH operating_income=NULL and
pretax_income=NULL (neither tagged yet in this premature filing), while FY2025 one row back has
a real pretax_income=$824.905M. Neither of this file's two existing operating_income fallbacks
(pretax_income->operating_income; net_income+tax->operating_income) can help, since both depend
on the SAME anchor row's own pretax_income/income_tax_expense, which are equally missing. This
was previously mis-diagnosed (missing_factor_inputs_audit_20260818 memory) as "a downstream
cascade of genuine per-fiscal-year gaps, not an independent bug" - it's actually the same
anchor-row-timing bug already fixed for revenue/EPS, just not recognized as such at the time.

Fixed by substituting the WHOLE income_rows[1] set together (operating_income, pretax_income,
D&A) when both anchor-row income-statement figures are missing, rather than mixing fields from
two different fiscal years (which would produce an internally inconsistent EBITDA).
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


# Downstream fetchone() calls, in order: price_daily.close, stockholders_equity,
# cash_and_equivalents, debt_row.
_DOWNSTREAM_FETCHONE = [
    (35.26,),
    (500_000_000.0,),
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
]


class TestEbitdaPrefersPopulatedFiscalYear:
    def test_falls_back_to_prior_row_pretax_income_when_anchor_has_neither(self) -> None:
        # HG-shaped: anchor row (FY2026) has real net_income but NULL operating_income AND
        # NULL pretax_income; prior row (FY2025) has a real pretax_income (typical insurer -
        # never tags operating_income at all, even in a complete year).
        income_rows = [
            (
                2026,
                None,
                217_032_000.0,
                5.75,  # eps present here so the EPS substitution doesn't also fire
                None,  # operating_income - not tagged
                None,  # pretax_income - not tagged
                None,
                None,
                98_614_386.0,
                None,
            ),
            (
                2025,
                2_905_524_000.0,
                840_029_000.0,
                5.75,
                None,  # operating_income - insurer never tags this, even in a complete year
                824_905_000.0,  # pretax_income - real
                1_000_000.0,  # depreciation_expense
                500_000.0,  # amortization_expense
                100_364_000.0,
                -15_124_000.0,
            ),
        ]

        result = _run_fetch_incremental("HG", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert not row.get("data_unavailable")
        # operating_income substituted from FY2025's pretax_income via the existing
        # pretax_income->operating_income fallback, now that pretax_income itself has a
        # real substituted value to fall back to.
        assert row["ebitda"] == 824_905_000.0 + 1_000_000.0 + 500_000.0

    def test_does_not_fire_when_anchor_has_a_real_pretax_income(self) -> None:
        """A normal financial-services anchor row (operating_income NULL, but pretax_income
        real) must keep using its OWN pretax_income via the existing fallback - the new
        substitution must only fire when BOTH anchor fields are missing."""
        income_rows = [
            (
                2026,
                1_000_000_000.0,
                100_000_000.0,
                1.0,
                None,
                120_000_000.0,
                2_000_000.0,
                1_000_000.0,
                10_000_000.0,
                None,
            ),
            (2025, 900_000_000.0, 90_000_000.0, 0.9, None, 999_999_999.0, 0.0, 0.0, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("REALPRETAX", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row["ebitda"] == 120_000_000.0 + 2_000_000.0 + 1_000_000.0

    def test_no_fallback_available_leaves_ebitda_null_not_a_crash(self) -> None:
        """Neither row has operating_income or pretax_income - must not crash and must not
        fabricate a value."""
        income_rows = [
            (2026, 100_000_000.0, 10_000_000.0, 1.0, None, None, None, None, 10_000_000.0, None),
            (2025, 90_000_000.0, 9_000_000.0, 0.9, None, None, None, None, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("NOOI", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row.get("ebitda") is None
