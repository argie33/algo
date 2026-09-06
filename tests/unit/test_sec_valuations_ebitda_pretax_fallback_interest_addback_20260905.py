"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up /
"implausible values" sweep): the pretax_income-as-operating_income fallback in
sec_valuations_income_context.py's _fetch_income_statement_context was applying
unconditionally to ANY symbol lacking a tagged operating_income, not just the financial-
services companies (banks/insurers) its own comment describes - pretax_income is AFTER
interest expense, so using it bare as a proxy for operating_income (which is BEFORE interest)
silently and massively understated EBITDA for any real industrial/leveraged filer with material
interest_expense.

Live-confirmed HRI (Herc Holdings, equipment rental, NOT a financial company): FY2025
pretax_income=$1M, interest_expense=$416M - the bare fallback produced ebitda=$1M (matching
sec_valuations' stored value exactly) for a company with a $4.4B market cap, a wrong-by-2-
orders-of-magnitude EV/EBITDA input. Fixed by adding back interest_expense (mathematically
correct for any company type, and a no-op for genuine financial companies which typically
don't tag a separate interest_expense concept at all).
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None, None)]]
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


# Same downstream fetchone() sequence as the sibling
# test_sec_valuations_ebitda_prefers_populated_fiscal_year.py file.
_DOWNSTREAM_FETCHONE = [
    None,  # entity_type exemption gate check (138006446) - not exempt
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
    None,
    (None, None),
    (None,),
    (35.26,),
    (500_000_000.0,),
    (1.0,),
    (4.5,),
    (20.0,),
    (20.0,),
    None,
    (None, None),
]


class TestEbitdaPretaxFallbackInterestAddback:
    def test_hri_shaped_leveraged_industrial_gets_interest_added_back(self) -> None:
        # HRI-shaped: no operating_income tagged, real pretax_income near breakeven after a
        # large interest_expense - the bare pretax_income fallback would produce a wrong-by-
        # orders-of-magnitude ebitda; adding back interest_expense recovers the real figure.
        income_rows = [
            (
                2025,
                4_376_000_000.0,
                1_000_000.0,
                None,
                None,  # operating_income - not tagged
                1_000_000.0,  # pretax_income - real, near breakeven after interest
                None,
                None,
                90_000_000.0,
                0.0,
                False,  # is_foreign_private_issuer
                7359,  # sic_code (equipment rental, not financial services)
                416_000_000.0,  # interest_expense - real, material
            ),
            (
                2024,
                3_568_000_000.0,
                211_000_000.0,
                None,
                None,
                291_000_000.0,
                None,
                None,
                90_000_000.0,
                80_000_000.0,
                False,
                7359,
                260_000_000.0,
            ),
        ]

        result = _run_fetch_incremental("HRI", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert not row.get("data_unavailable")
        # operating_income = pretax_income + interest_expense = 1M + 416M = 417M, then
        # ebitda = operating_income (no dep/amort tagged here) = 417M - NOT the bare 1M the
        # old unconditional fallback would have produced.
        assert row["ebitda"] == 1_000_000.0 + 416_000_000.0

    def test_bank_shaped_with_no_interest_expense_concept_unchanged(self) -> None:
        # A genuine financial-services filer (bank/insurer) that never tags a standalone
        # interest_expense concept at all (interest is netted into revenue) must keep using
        # bare pretax_income, exactly as before this fix - interest_expense_val is None here,
        # so the addback is a no-op.
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
                False,
                6021,
                None,  # interest_expense - never tagged, genuine financial-company shape
            ),
            (2025, 900_000_000.0, 90_000_000.0, 0.9, None, 999_999_999.0, 0.0, 0.0, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("REALBANK", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row["ebitda"] == 120_000_000.0 + 2_000_000.0 + 1_000_000.0
