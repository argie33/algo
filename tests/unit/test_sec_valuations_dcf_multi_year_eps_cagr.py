"""Tests for the 2026-08-25 multi-year EPS CAGR fix to load_sec_valuations.py (goal: "finance
best practices" methodology audit, deferred item #2 from that session's original DCF fix).

The DCF's growth driver was a bare TTM-vs-prior-year EPS delta - noisy for any symbol whose
single prior year had a one-off blip (impairment, tax item, etc), the same "one bad year
distorts the whole figure" problem already solved for FCF via the 3-year avg_fcf_fallback.
_compute_multi_year_eps_cagr computes a CAGR from the newest/oldest usable EPS in the
already-fetched (now LIMIT-6, was LIMIT-2) income_rows list, used by _compute_valuations as the
DCF's growth driver in place of the single-year delta - but only for the DCF; peg_ratio's own
growth_rate deliberately stays single-year (see that calculation's own comment in the source).
"""

from typing import Any

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


def _row(fiscal_year: int, eps: float | None) -> tuple[Any, ...]:
    """Minimal income_rows-shaped tuple - _compute_multi_year_eps_cagr only reads index 0
    (fiscal_year) and index 3 (earnings_per_share), same positions as the real query."""
    return (fiscal_year, None, None, eps)


class TestComputeMultiYearEpsCagr:
    def test_three_year_gap_computes_cagr(self) -> None:
        loader = _make_loader()
        # 1.00 -> 1.15 over 3 fiscal years: (1.15/1.00)**(1/3) - 1
        income_rows = [_row(2026, 1.15), _row(2025, 1.10), _row(2024, None), _row(2023, 1.00)]
        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        assert cagr is not None
        assert abs(cagr - (((1.15 / 1.00) ** (1 / 3) - 1) * 100)) < 1e-9

    def test_two_year_gap_returns_none_identical_to_single_year_delta(self) -> None:
        """A 2-fiscal-year-apart CAGR is arithmetically identical to the existing single-year
        delta - not informative enough to justify a second growth-rate concept, so this must
        fall back (None) rather than silently duplicate it."""
        loader = _make_loader()
        income_rows = [_row(2026, 1.15), _row(2024, 1.00)]
        assert loader._compute_multi_year_eps_cagr(income_rows) is None

    def test_fewer_than_two_usable_years_returns_none(self) -> None:
        loader = _make_loader()
        assert loader._compute_multi_year_eps_cagr([_row(2026, 1.15)]) is None
        assert loader._compute_multi_year_eps_cagr([]) is None

    def test_null_eps_rows_skipped(self) -> None:
        loader = _make_loader()
        income_rows = [
            _row(2026, None),  # tier-1 stub row, no EPS tagged yet
            _row(2025, 1.15),
            _row(2024, None),
            _row(2022, 1.00),
        ]
        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        # newest usable = 2025 (not 2026, which has no EPS), oldest usable = 2022 -> 3 years apart
        assert cagr is not None
        assert abs(cagr - (((1.15 / 1.00) ** (1 / 3) - 1) * 100)) < 1e-9

    def test_non_positive_endpoint_excluded(self) -> None:
        """CAGR isn't meaningful across a sign change - same requirement PEG's own growth_rate
        already imposes on prior_year_eps/ttm_eps."""
        loader = _make_loader()
        income_rows = [_row(2026, 1.15), _row(2025, -0.50), _row(2024, 1.05), _row(2023, 1.00)]
        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        # -0.50 dropped -> newest usable=2026 (1.15), oldest usable=2023 (1.00), 3 years apart
        assert cagr is not None
        assert abs(cagr - (((1.15 / 1.00) ** (1 / 3) - 1) * 100)) < 1e-9

    def test_zero_eps_excluded(self) -> None:
        loader = _make_loader()
        income_rows = [_row(2026, 1.15), _row(2025, 0.0), _row(2023, 1.00)]
        cagr = loader._compute_multi_year_eps_cagr(income_rows)
        assert cagr is not None
        assert abs(cagr - (((1.15 / 1.00) ** (1 / 3) - 1) * 100)) < 1e-9


class TestDcfPrefersMultiYearCagrOverSingleYearDelta:
    def _base_kwargs(self) -> dict:
        return {
            "symbol": "TESTCO",
            "current_price": 5.0,
            "shares_out": 10.0,
            "ttm_eps": 1.1,
            "ttm_revenue": 200.0,
            "book_value": 50.0,
            "ocf": 100.0,
            "capex": 0.0,
            "prior_year_eps": 1.0,  # single-year delta = 10%
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_dcf_uses_cagr_when_supplied(self) -> None:
        loader = _make_loader()
        no_cagr_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["dcf_eps_cagr_pct"] = 50.0  # deliberately far from the 10% single-year delta
        cagr_result = loader._compute_valuations(**kwargs)

        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=50.0, shares_out=10.0, current_price=5.0
        )
        assert cagr_result["intrinsic_value_per_share"] == expected_ivps
        assert cagr_result["margin_of_safety_pct"] == expected_mos
        assert cagr_result["intrinsic_value_per_share"] != no_cagr_result["intrinsic_value_per_share"]

    def test_peg_ratio_unaffected_by_dcf_cagr(self) -> None:
        """peg_ratio must keep using the single-year delta (10%) regardless of what the DCF's
        dcf_eps_cagr_pct says - PEG is a conventionally single-year-forward metric and this fix
        deliberately doesn't touch it."""
        loader = _make_loader()
        no_cagr_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["dcf_eps_cagr_pct"] = 50.0
        cagr_result = loader._compute_valuations(**kwargs)

        assert cagr_result["peg_ratio"] == no_cagr_result["peg_ratio"]
        assert cagr_result["peg_ratio"] == round(cagr_result["pe_ratio"] / 10.0, 2)

    def test_missing_cagr_falls_back_to_single_year_delta(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["dcf_eps_cagr_pct"] = None
        result = loader._compute_valuations(**kwargs)

        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=10.0, shares_out=10.0, current_price=5.0
        )
        assert result["intrinsic_value_per_share"] == expected_ivps
        assert result["margin_of_safety_pct"] == expected_mos
