#!/usr/bin/env python3
"""Tests for the "true FCFE via net borrowing" DCF fix (2026-08-25, goal: DCF audit follow-up).

The DCF's FCF base (OCF - CapEx - SBC) implicitly assumes zero net borrowing - a genuine FCFE
should add back net debt issued (or subtract net debt repaid): FCFE = OCF - CapEx - SBC +
Net Borrowing. This pipeline has no debt-issuance/repayment cash-flow data (confirmed via a
schema check of annual_cash_flow - only a blended financing_cash_flow that also mixes in
equity/dividends), so _get_net_borrowing_for_dcf uses the standard practitioner proxy instead:
the year-over-year change in total balance-sheet debt (long_term_debt + short_term_debt +
operating_lease_liability + finance_lease_liability - same components total_debt already
sums), only when the two most recent usable years are genuinely ADJACENT fiscal years (a
safety guard against reading a cross-year XBRL tag switch as a "borrowing" event - see this
file's own CAT/XOM/DKNG tag-switching commentary).

Expected values below are computed independently (plain arithmetic) so this locks in the
methodology, not just mirrors the code.
"""

from typing import Any

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchone stand-in: first call returns the newest usable fiscal year's
    (fiscal_year, *debt_components) row, second call (only reached if the first exists)
    returns the prior fiscal year's debt_components row - matching
    _get_net_borrowing_for_dcf's real query order."""

    def __init__(self, results: list[tuple[Any, ...] | None]) -> None:
        self._results = list(results)
        self._idx = 0
        self.execute_count = 0

    def execute(self, *_args: object, **_kwargs: object) -> None:
        self.execute_count += 1

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._results[self._idx]
        self._idx += 1
        return result


class TestGetNetBorrowingForDcf:
    def test_adjacent_years_positive_net_borrowing(self) -> None:
        """Debt rose from $80M to $100M over 1 fiscal year -> net borrowing = +$20M."""
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, 70_000_000.0, 20_000_000.0, 10_000_000.0, None),  # newest: 2026, sum=100M
                (60_000_000.0, 15_000_000.0, 5_000_000.0, None),  # prior (2025): sum=80M
            ]
        )
        assert loader._get_net_borrowing_for_dcf(cur, "TESTCO") == 20_000_000.0

    def test_adjacent_years_negative_net_borrowing_debt_paydown(self) -> None:
        """Debt fell from $90M to $60M -> net borrowing = -$30M (debt repaid, reduces FCFE)."""
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, 40_000_000.0, 20_000_000.0, None, None),  # newest: 2026, sum=60M
                (70_000_000.0, 20_000_000.0, None, None),  # prior (2025): sum=90M
            ]
        )
        assert loader._get_net_borrowing_for_dcf(cur, "TESTCO") == -30_000_000.0

    def test_none_components_treated_as_zero(self) -> None:
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, None, 10_000_000.0, None, None),  # newest: sum=10M
                (None, 5_000_000.0, None, None),  # prior: sum=5M
            ]
        )
        assert loader._get_net_borrowing_for_dcf(cur, "TESTCO") == 5_000_000.0

    def test_no_newest_row_returns_none_without_second_query(self) -> None:
        """No usable debt data at all -> None, and only 1 query should even fire (the second
        query needs the newest year to know which prior year to look for)."""
        loader = _make_loader()
        cur = _FakeCursor([None])
        assert loader._get_net_borrowing_for_dcf(cur, "TESTCO") is None
        assert cur.execute_count == 1

    def test_no_adjacent_prior_year_returns_none(self) -> None:
        """A newest usable year exists but fiscal_year - 1 has no usable debt data (a real gap,
        e.g. that year's balance sheet wasn't filed/tagged) -> None, not a spurious multi-year
        comparison."""
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, 70_000_000.0, 20_000_000.0, 10_000_000.0, None),
                None,  # fiscal_year=2025 query finds nothing
            ]
        )
        assert loader._get_net_borrowing_for_dcf(cur, "TESTCO") is None

    def test_mismatched_null_component_returns_none_not_a_spurious_delta(self) -> None:
        """AAPL-shaped bug, live-caught before this fix was committed: the newest (current,
        still in-progress) fiscal year has real long_term_debt/short_term_debt but NULL
        operating_lease_liability/finance_lease_liability (not yet tagged), while the prior
        complete year has all four populated. Treating NULL-this-year as "$0 lease debt" vs a
        real prior-year lease figure manufactured a spurious ~-$28B "paydown" that was purely
        a data-completeness gap, not a real deleveraging event. A component's null-ness must
        match between the two years, or the whole comparison must be skipped."""
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, 82_300_000_000.0, 1_997_000_000.0, None, None),  # newest: leases NULL
                (90_678_000_000.0, 7_979_000_000.0, 12_490_000_000.0, 1_230_000_000.0),  # prior: all real
            ]
        )
        assert loader._get_net_borrowing_for_dcf(cur, "AAPL") is None

    def test_zero_net_borrowing_is_a_real_value_not_none(self) -> None:
        """Debt unchanged year-over-year -> net borrowing = 0.0, a real (falsy-but-valid)
        result, not treated the same as "unavailable"."""
        loader = _make_loader()
        cur = _FakeCursor(
            [
                (2026, 50_000_000.0, 10_000_000.0, None, None),  # sum=60M
                (55_000_000.0, 5_000_000.0, None, None),  # sum=60M
            ]
        )
        result = loader._get_net_borrowing_for_dcf(cur, "TESTCO")
        assert result == 0.0
        assert result is not None


class TestNetBorrowingWiredIntoDcfOnly:
    """net_borrowing must adjust the DCF's fcf_base but never fcf_yield (same "DCF gets a
    smoothed/adjusted figure, fcf_yield stays on the latest year's raw number" split
    avg_fcf_fallback/dcf_eps_cagr_pct already use)."""

    def _base_kwargs(self) -> dict[str, Any]:
        return {
            "symbol": "TESTCO",
            "current_price": 5.0,
            "shares_out": 10.0,
            "ttm_eps": 1.0,
            "ttm_revenue": 200.0,
            "book_value": 50.0,
            "ocf": 100.0,
            "capex": 0.0,
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_positive_net_borrowing_raises_intrinsic_value_not_fcf_yield(self) -> None:
        loader = _make_loader()
        no_nb_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["net_borrowing"] = 30.0  # DCF fcf: 100 + 30 = 130, not 100
        nb_result = loader._compute_valuations(**kwargs)

        # fcf_yield stays on the raw latest-year fcf (100), completely unaffected.
        assert nb_result["fcf_yield"] == no_nb_result["fcf_yield"]

        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=130.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        assert nb_result["intrinsic_value_per_share"] == expected_ivps
        assert nb_result["margin_of_safety_pct"] == expected_mos
        assert nb_result["intrinsic_value_per_share"] > no_nb_result["intrinsic_value_per_share"]

    def test_negative_net_borrowing_lowers_intrinsic_value(self) -> None:
        loader = _make_loader()
        no_nb_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["net_borrowing"] = -40.0  # DCF fcf: 100 - 40 = 60
        nb_result = loader._compute_valuations(**kwargs)

        assert nb_result["intrinsic_value_per_share"] < no_nb_result["intrinsic_value_per_share"]

    def test_default_none_matches_pre_fix_behavior_exactly(self) -> None:
        loader = _make_loader()
        result = loader._compute_valuations(**self._base_kwargs())
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38

    def test_net_borrowing_pushing_fcf_negative_leaves_dcf_none_not_a_crash(self) -> None:
        """A large enough debt paydown that it flips DCF-basis FCF negative must gracefully
        null the DCF (same guard as any other negative-fcf case), not crash."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["net_borrowing"] = -150.0  # DCF fcf: 100 - 150 = -50
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] is None
        assert result["margin_of_safety_pct"] is None
        # Other ratios must still compute normally.
        assert result["pe_ratio"] == 5.0

    def test_implausibly_large_net_borrowing_relative_to_fcf_ignored_not_applied(self) -> None:
        """BWXT-shaped bug, live-caught before this fix was committed: a real symbol's
        net_borrowing computed to ~50x its own OCF scale, tracing back to a pre-existing
        data-quality outlier in operating_lease_liability (not something this feature caused,
        but something it would otherwise blindly amplify into an even more absurd DCF result).
        DCF_NET_BORROWING_MAX_FCF_MULTIPLE (10x) must silently skip the adjustment rather than
        apply it - fcf_base=100.0, net_borrowing=2000.0 is 20x, over the bound."""
        loader = _make_loader()
        no_nb_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["net_borrowing"] = 2000.0
        nb_result = loader._compute_valuations(**kwargs)

        assert nb_result["intrinsic_value_per_share"] == no_nb_result["intrinsic_value_per_share"]
        assert nb_result["margin_of_safety_pct"] == no_nb_result["margin_of_safety_pct"]

    def test_near_total_cancellation_nulls_dcf_not_a_misleading_near_zero_value(self) -> None:
        """IMMR-shaped bug, live-caught 2026-09-04 (goal: "implausible values" audit): a real,
        healthy fcf_base ($32.102M, fcf_yield=12.92%) combined with a single large
        debt-repayment year's net_borrowing (-$32.098M, well within the 10x ceiling) leaves a
        candidate dcf_fcf_base of just $4,000 - still positive, so it slips past the DCF's own
        `fcf <= 0` gate, but that near-zero base compounds through the whole forecast into an
        intrinsic_value_per_share that rounds to $0.00 (a misleading "worthless" signal, not an
        honest "no DCF available" one). DCF_NET_BORROWING_MIN_RETAINED_FRACTION must null the
        DCF here instead - same treatment as a full negative flip."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["ocf"] = 32_102_000.0
        kwargs["capex"] = 0.0
        kwargs["net_borrowing"] = -32_098_000.0  # fcf_base=32.102M, candidate=$4,000
        result = loader._compute_valuations(**kwargs)

        assert result["intrinsic_value_per_share"] is None
        assert result["margin_of_safety_pct"] is None

    def test_net_borrowing_at_exactly_the_bound_is_still_applied(self) -> None:
        """Exactly DCF_NET_BORROWING_MAX_FCF_MULTIPLE x fcf_base (the boundary itself, <=) must
        still be applied, not rejected - fcf_base=100.0, net_borrowing=1000.0 is exactly 10x."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["net_borrowing"] = 1000.0
        result = loader._compute_valuations(**kwargs)

        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=1100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        assert result["intrinsic_value_per_share"] == expected_ivps
        assert result["margin_of_safety_pct"] == expected_mos
