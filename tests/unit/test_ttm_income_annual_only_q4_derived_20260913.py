"""Regression test for the 2026-09-13 fix (goal session: MU TTM-builder gap): MU-shaped
annual reporters never file a standalone Q4 10-Q (Q4 = FY total - Q1-Q3, disclosed only in the
10-K's own comparative tables). Live-confirmed via MU's real quarterly_income_statement rows:
2024-11-28/2025-02-27/2025-05-29 (each ~91 days apart) then a 182-day gap to 2025-11-27,
because FY2025 Q4 (period ~2025-08-28) was never separately filed. Before this fix,
`_validate_ttm_quarter_window` correctly rejected this shape (not 4 valid consecutive
quarters), so `_compute_ttm_income_from_quarters` returned None and the primary path silently
fell back to a stale annual EPS ($7.59), producing pe_ratio=127.48 despite MU having 60 real
quarters on file - not a shallow-history case at all.

`_find_single_missing_quarter_gap` + `_derive_missing_annual_only_quarter` now detect this
exact shape and derive the missing quarter as `annual_total - sum(the other 3 real quarters of
that fiscal year)`, matching real-world Micron's own reported FY2025 Q4 (~$11.3B revenue).
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.helpers.sec_valuations_checks import ValuationSanityCheckMixin

_TODAY = date.today()


class _FakeCursor:
    """Dispatches on the query text so one patched DatabaseContext can serve both the
    quarterly-history fetch and the annual_income_statement lookup `_derive_missing_annual_
    only_quarter` issues on its own separate DatabaseContext call."""

    def __init__(self, quarterly_rows: list[tuple[Any, ...]], annual_rows_by_fy: dict[int, tuple[Any, ...]]) -> None:
        self._quarterly_rows = quarterly_rows
        self._annual_rows_by_fy = annual_rows_by_fy
        self._last_query_was_annual = False
        self._last_fy: int | None = None

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        self._last_query_was_annual = "annual_income_statement" in query
        if self._last_query_was_annual:
            self._last_fy = params[1]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._quarterly_rows

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._last_fy is None:
            return None
        return self._annual_rows_by_fy.get(self._last_fy)


def _make_mixin(quarterly_rows: list[tuple[Any, ...]], annual_rows_by_fy: dict[int, tuple[Any, ...]]) -> Any:
    mixin = ValuationSanityCheckMixin.__new__(ValuationSanityCheckMixin)
    cursor = _FakeCursor(quarterly_rows, annual_rows_by_fy)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)
    mixin._fake_ctx = fake_ctx  # type: ignore[attr-defined]
    return mixin


def _q(
    days_ago: int, revenue: float, net_income: float, eps: float, fiscal_year: int, fiscal_quarter: int
) -> tuple[Any, ...]:
    return (_TODAY - timedelta(days=days_ago), revenue, net_income, eps, fiscal_year, fiscal_quarter)


# MU-shaped: 3 clean quarters (~91 days apart), then a 182-day gap, then 3 more clean quarters
# (the real 3 quarters of the fiscal year whose Q4 was never separately filed).
_MU_SHAPED_QUARTERS = [
    _q(5, 41_456_000_000.0, 28_243_000_000.0, 25.03, 2026, 3),
    _q(96, 23_860_000_000.0, 13_785_000_000.0, 12.25, 2026, 2),
    _q(187, 13_643_000_000.0, 5_240_000_000.0, 4.66, 2025, 1),
    _q(369, 9_301_000_000.0, 1_885_000_000.0, 1.69, 2025, 3),  # 182-day gap before this row
    _q(460, 8_053_000_000.0, 1_583_000_000.0, 1.42, 2025, 2),
    _q(551, 8_709_000_000.0, 1_870_000_000.0, 1.68, 2024, 1),
]
_MU_ANNUAL_FY2025 = (37_378_000_000.0, 8_539_000_000.0, 7.59)


class TestFindSingleMissingQuarterGap:
    def test_mu_shaped_gap_detected(self) -> None:
        mixin = ValuationSanityCheckMixin.__new__(ValuationSanityCheckMixin)
        gap = mixin._find_single_missing_quarter_gap(_MU_SHAPED_QUARTERS[:4])
        assert gap == (2, 3)

    def test_no_gap_returns_none(self) -> None:
        mixin = ValuationSanityCheckMixin.__new__(ValuationSanityCheckMixin)
        clean = [_q(d, 1.0, 1.0, 1.0, 2026, 1) for d in (5, 96, 187, 278)]
        assert mixin._find_single_missing_quarter_gap(clean) is None

    def test_two_irregular_gaps_returns_none(self) -> None:
        mixin = ValuationSanityCheckMixin.__new__(ValuationSanityCheckMixin)
        rows = [_q(d, 1.0, 1.0, 1.0, 2026, 1) for d in (5, 96, 400, 800)]
        assert mixin._find_single_missing_quarter_gap(rows) is None


class TestComputeTtmIncomeFromQuartersAnnualOnlyQ4:
    def test_mu_shaped_gap_derives_missing_quarter_and_computes_ttm(self) -> None:
        mixin = _make_mixin(_MU_SHAPED_QUARTERS, {2025: _MU_ANNUAL_FY2025})
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_income_from_quarters("MU")
        assert result is not None
        # derived Q4: revenue=37,378M-(8,709+8,053+9,301)=11,315M; net_income=8,539M-
        # (1,870+1,583+1,885)=3,201M; eps=7.59-(1.68+1.42+1.69)=2.80
        # TTM = 3 known (25.03+12.25+4.66) + derived 2.80 = 44.74
        assert result["revenue"] == 41_456_000_000.0 + 23_860_000_000.0 + 13_643_000_000.0 + 11_315_000_000.0
        assert result["net_income"] == 28_243_000_000.0 + 13_785_000_000.0 + 5_240_000_000.0 + 3_201_000_000.0
        assert abs(result["eps"] - 44.74) < 0.01

    def test_missing_annual_row_returns_none(self) -> None:
        mixin = _make_mixin(_MU_SHAPED_QUARTERS, {})
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_income_from_quarters("MU")
        assert result is None

    def test_implausible_derived_quarter_returns_none(self) -> None:
        # Annual total far too small relative to the 3 known quarters (e.g. a wrong-fiscal-
        # year match) - must fail closed, not fabricate a nonsense quarter.
        mixin = _make_mixin(_MU_SHAPED_QUARTERS, {2025: (100.0, 50.0, 0.01)})
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_income_from_quarters("MU")
        assert result is None

    def test_clean_four_quarters_unaffected(self) -> None:
        clean = [_q(d, 1_000.0, 100.0, 2.0, 2026, i) for i, d in enumerate((5, 96, 187, 278), start=1)]
        mixin = _make_mixin(clean, {})
        with patch("loaders.helpers.sec_valuations_checks.DatabaseContext", return_value=mixin._fake_ctx):
            result = mixin._compute_ttm_income_from_quarters("TEST")
        assert result == {"period_end": clean[0][0], "revenue": 4000.0, "net_income": 400.0, "eps": 8.0}
