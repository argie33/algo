"""End-to-end regression test for the 2026-08-25 multi-year EPS CAGR fix (goal: "finance best
practices" methodology audit, deferred item #2), exercised through the full fetch_incremental
path rather than _compute_valuations directly - confirms the income_rows query's LIMIT-6 (was
LIMIT-2) actually reaches _compute_multi_year_eps_cagr and its result actually drives the
stored intrinsic_value_per_share/margin_of_safety_pct, not just the unit-level plumbing tested
in test_sec_valuations_dcf_multi_year_eps_cagr.py.

fetchone_results below is ordered to match fetch_incremental's actual fetchone() call sequence
for the simplest real call path (domestic filer, no dual-class sibling, shares_out resolved
directly from the income-statement row so no extra shares-tier query fires): cash_row2 (cash
query), debt_row (4-tuple), has_dual_class_sibling, cross_check_row (company_info_sec
shares_outstanding cross-check - fires unconditionally once shares_out is resolved, see
SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO's comment), price_row, balance_row, beta_row,
risk_free_rate, yf_row. income_rows/cash_rows are separate fetchall() calls, not part of this
list.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        # ocf=80M, capex=10M, no SBC -> fcf_base = 70M, same fixed shape every other e2e test
        # in this suite uses.
        self._fetchall_results = [income_rows, [(80_000_000.0, 10_000_000.0, None, None)]]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> Any:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, income_rows: list[tuple[Any, ...]], fetchone_results: list[Any]
) -> list[dict[str, Any]]:
    loader = _make_loader()
    fake_cursor = _FakeCursor(income_rows, fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        return loader.fetch_incremental(symbol, None)


class TestMultiYearEpsCagrEndToEnd:
    def test_dcf_uses_multi_year_cagr_from_full_income_rows_history(self) -> None:
        # 4 fiscal years, EPS 1.00 (2023) -> 1.15 (2026): CAGR-eligible (3 years apart).
        # Single-year delta (2025->2026: 1.10->1.15, ~4.55%) would give a different DCF result
        # than the 3-year CAGR (~4.77%) - proves the CAGR path actually drove the stored value,
        # not just a lucky coincidence with the single-year figure.
        income_rows = [
            (
                2026,
                1_000_000_000.0,
                100_000_000.0,
                1.15,
                150_000_000.0,
                120_000_000.0,
                10_000_000.0,
                5_000_000.0,
                1_000_000_000.0,
                20_000_000.0,
                False,
            ),
            (
                2025,
                900_000_000.0,
                90_000_000.0,
                1.10,
                140_000_000.0,
                110_000_000.0,
                9_000_000.0,
                4_500_000.0,
                1_000_000_000.0,
                18_000_000.0,
                False,
            ),
            (
                2024,
                800_000_000.0,
                80_000_000.0,
                None,
                130_000_000.0,
                100_000_000.0,
                8_000_000.0,
                4_000_000.0,
                1_000_000_000.0,
                16_000_000.0,
                False,
            ),
            (
                2023,
                700_000_000.0,
                70_000_000.0,
                1.00,
                120_000_000.0,
                90_000_000.0,
                7_000_000.0,
                3_500_000.0,
                1_000_000_000.0,
                14_000_000.0,
                False,
            ),
        ]
        fetchone_results = [
            (68_111_000.0,),  # cash_row2 (cash_and_equivalents)
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            None,  # has_dual_class_sibling - no matching row
            None,  # cross_check_row - no company_info_sec data, no override
            (50.0,),  # price_row (price_daily.close)
            (5_157_000_000.0,),  # balance_row (stockholders_equity)
            (1.0,),  # beta_row (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10)
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yf_row (yfinance_snapshot market_cap/pe_ratio sanity check)
        ]

        result = _run_fetch_incremental("TESTCO", income_rows, fetchone_results)
        row = result[0]

        expected_cagr_pct = ((1.15 / 1.00) ** (1 / 3) - 1) * 100
        single_year_delta_pct = ((1.15 - 1.10) / 1.10) * 100
        assert abs(expected_cagr_pct - single_year_delta_pct) > 0.01  # the two must actually differ

        loader = _make_loader()
        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO",
            fcf=70_000_000.0,
            eps_growth_pct=expected_cagr_pct,
            shares_out=1_000_000_000.0,
            current_price=50.0,
        )
        single_year_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO",
            fcf=70_000_000.0,
            eps_growth_pct=single_year_delta_pct,
            shares_out=1_000_000_000.0,
            current_price=50.0,
        )

        assert row["intrinsic_value_per_share"] == expected_ivps
        assert row["margin_of_safety_pct"] == expected_mos
        assert row["intrinsic_value_per_share"] != single_year_ivps

        # peg_ratio must still use the single-year delta (2025->2026), untouched by the CAGR.
        expected_peg = round(row["pe_ratio"] / single_year_delta_pct, 2)
        assert row["peg_ratio"] == expected_peg

    def test_only_two_fiscal_years_falls_back_to_single_year_delta(self) -> None:
        """With only the pre-existing 2-row window (no rows 3-6 available), the CAGR helper
        must return None and the DCF must fall back to exactly the old single-year-delta
        behavior - no regression for symbols without deep EPS history."""
        income_rows = [
            (
                2026,
                1_000_000_000.0,
                100_000_000.0,
                1.15,
                150_000_000.0,
                120_000_000.0,
                10_000_000.0,
                5_000_000.0,
                1_000_000_000.0,
                20_000_000.0,
                False,
            ),
            (
                2025,
                900_000_000.0,
                90_000_000.0,
                1.10,
                140_000_000.0,
                110_000_000.0,
                9_000_000.0,
                4_500_000.0,
                1_000_000_000.0,
                18_000_000.0,
                False,
            ),
        ]
        fetchone_results = [
            (68_111_000.0,),
            (20_000_000.0, 5_000_000.0, None, None),
            None,
            None,
            (50.0,),
            (5_157_000_000.0,),
            (1.0,),
            (4.5,),
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),
        ]

        result = _run_fetch_incremental("TESTCO", income_rows, fetchone_results)
        row = result[0]

        single_year_delta_pct = ((1.15 - 1.10) / 1.10) * 100
        loader = _make_loader()
        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO",
            fcf=70_000_000.0,
            eps_growth_pct=single_year_delta_pct,
            shares_out=1_000_000_000.0,
            current_price=50.0,
        )
        assert row["intrinsic_value_per_share"] == expected_ivps
        assert row["margin_of_safety_pct"] == expected_mos
