"""Regression test for the 2026-08-18 "no SEC data" audit finding: load_sec_valuations.py's
earnings_per_share suffers the identical "premature fiscal year stub" gap already fixed for
revenue (see test_sec_valuations_revenue_prefers_populated_fiscal_year.py) - same anchor row,
same root cause, but the EPS side never got the matching same-year-substitute fallback.

Live-confirmed on HG (Hamilton Insurance Group, a real NYSE-listed Bermuda insurer): FY2026's
annual_income_statement row has net_income=$217.032M (real, wins the tier-0 tiebreak) but
earnings_per_share=NULL, while FY2025 one row back has a real earnings_per_share=$5.75.
ttm_eps_basic came back None, silently killing pe_ratio and peg_ratio ("SEC data not available"
on the scores page) even though growth_metrics elsewhere in the pipeline computes EPS growth
fine from the same underlying data.

Fixed by falling back to income_rows[1]'s earnings_per_share when the anchor row's is None (same
convention as the revenue fix). This required extra care PEG's existing bug-fix comment already
warns about: prior_year_eps must never collapse to the same fiscal year now supplying ttm_eps -
when the substitution consumes income_rows[1], prior_year_eps is re-fetched from a genuinely
older fiscal year instead of reusing income_rows[1] a second time.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone/fetchall stand-in - see the sibling revenue-fallback test's
    _FakeCursor docstring for why fetchall() must be sequential (income_rows first, then the
    DCF 3-year-average-FCF fallback's cash_rows)."""

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


# Downstream fetchone() calls after income_rows/EPS-fallback, in order: price_daily.close,
# stockholders_equity, cash_and_equivalents, debt_row.
_DOWNSTREAM_FETCHONE = [
    (35.26,),
    (500_000_000.0,),
    (30_000_000.0,),
    (20_000_000.0, 5_000_000.0, None, None),
]


class TestEpsPrefersPopulatedFiscalYear:
    def test_falls_back_to_prior_row_eps_when_anchor_row_eps_is_null(self) -> None:
        # HG-shaped: anchor row (FY2026) has real net_income but NULL earnings_per_share;
        # prior row (FY2025) has a real, complete earnings_per_share.
        income_rows = [
            (2026, None, 217_032_000.0, None, None, None, None, None, 98_614_386.0, None),  # FY2026 anchor
            (
                2025,
                2_905_524_000.0,
                840_029_000.0,
                5.75,
                None,
                824_905_000.0,
                None,
                None,
                100_364_000.0,
                -15_124_000.0,
            ),  # FY2025
        ]
        # The substitution fires (income_rows[1] consumed as ttm_eps), so prior_year_eps is
        # re-fetched from a genuinely older year - mock it as None (no 3rd year in this fixture).
        fetchone_results = [(None,), *_DOWNSTREAM_FETCHONE]

        result = _run_fetch_incremental("HG", income_rows, fetchone_results)

        row = result[0]
        assert not row.get("data_unavailable")
        assert row["pe_ratio"] is not None, "PE ratio should compute using the fallback EPS"
        assert row["pe_ratio"] == round(35.26 / 5.75, 2)

    def test_no_fallback_available_leaves_pe_ratio_null_not_a_crash(self) -> None:
        # Genuinely unprofitable-in-both-years company: neither row has EPS. Must not crash
        # and must not fabricate a value.
        income_rows = [
            (2026, 100_000_000.0, -10_000_000.0, None, None, None, None, None, 10_000_000.0, None),
            (2025, 90_000_000.0, -8_000_000.0, None, None, None, None, None, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("NOEPS", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row.get("pe_ratio") is None

    def test_anchor_row_with_real_eps_is_not_overridden_by_fallback(self) -> None:
        # A normal, complete anchor row must keep its own EPS - the fallback must only fire
        # when the anchor's earnings_per_share is actually NULL.
        income_rows = [
            (2026, 100_000_000.0, 10_000_000.0, 1.0, 15_000_000.0, 12_000_000.0, None, None, 10_000_000.0, None),
            (2025, 90_000_000.0, 9_000_000.0, 0.9, 14_000_000.0, 11_000_000.0, None, None, 10_000_000.0, None),
        ]

        result = _run_fetch_incremental("REALEPS", income_rows, _DOWNSTREAM_FETCHONE)

        row = result[0]
        assert row["pe_ratio"] == round(35.26 / 1.0, 2)

    def test_peg_growth_leg_does_not_double_count_the_substituted_year(self) -> None:
        """The exact bug this fallback must NOT reintroduce (see this loader's own
        governance comment): prior_year_eps must never equal ttm_eps's own source year, or
        PEG's growth_rate collapses to 0 for every symbol that hits this fallback."""
        income_rows = [
            (2026, None, 217_032_000.0, None, None, None, None, None, 98_614_386.0, None),  # anchor, no EPS
            (2025, 2_905_524_000.0, 840_029_000.0, 5.75, None, 824_905_000.0, None, None, 100_364_000.0, None),
        ]
        # A genuinely older year (FY2024) with its own real EPS - the re-fetch query result.
        fetchone_results = [(3.81,), *_DOWNSTREAM_FETCHONE]

        result = _run_fetch_incremental("HG2", income_rows, fetchone_results)

        row = result[0]
        # PEG should compute using FY2024's real 3.81 as the growth-rate denominator, not
        # reuse FY2025's 5.75 for both legs (which would make growth_rate exactly 0).
        assert row["peg_ratio"] is not None
        expected_growth_rate = ((5.75 - 3.81) / abs(3.81)) * 100
        expected_peg = round(row["pe_ratio"] / expected_growth_rate, 2)
        assert row["peg_ratio"] == expected_peg
