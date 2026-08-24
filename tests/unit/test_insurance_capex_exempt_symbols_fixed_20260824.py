"""Regression test for the 2026-08-24 fix (goal: "Margin of Safety (DCF) / Cash flow data
unavailable" audit): a small set of insurers (CRBG, FG, GNW, JXN, LNC, PRU, AFL, CNO, AFG,
AXS, CB, EG, GBLI, HG, HMN, KG, RNR, SPNT, AGO, ORI, OSG) never tag any capex-related XBRL
concept in their entire filing history - live-confirmed via real companyfacts JSON: no
PP&E-family concept, no REIT-family concept
(test_reit_capex_concepts_fixed_20260824.py), no insurer investment-real-estate concept
(PaymentsToAcquireRealEstateAndRealEstateJointVentures /
PaymentsToAcquireRealEstateHeldForInvestment).

Unlike depository institutions (test_bank_capex_structural_gap_fixed_20260822.py),
insurance SIC codes are NOT uniformly capex-less - ALL (Allstate) and HIG (Hartford) both
report real, material "PaymentsToAcquirePropertyPlantAndEquipment" ($267M/$215M FY2023) - so
this fix uses a small, individually-verified symbol allowlist
(INSURANCE_CAPEX_EXEMPT_SYMBOLS) rather than a SIC-code allowlist. Wired into both
load_sec_valuations.py's fetch_incremental (fcf_yield/avg_fcf_fallback) and
sec_base.py's free_cash_flow derivation, same two call sites the bank fix touched.
"""

from loaders.load_sec_valuations import SecValuationsLoader


class TestInsuranceCapexExemptSymbols:
    def test_confirmed_structurally_capex_less_insurers_are_covered(self) -> None:
        symbols = SecValuationsLoader.INSURANCE_CAPEX_EXEMPT_SYMBOLS
        for real_symbol in ("AFL", "PRU", "AGO", "CB", "AXS"):
            assert real_symbol in symbols

    def test_insurers_with_real_capex_are_excluded(self) -> None:
        """ALL (Allstate) and HIG (Hartford) both tag real, material
        "PaymentsToAcquirePropertyPlantAndEquipment" and must not be swept into this
        allowlist - doing so would fabricate a $0 capex for a filer with real spending."""
        symbols = SecValuationsLoader.INSURANCE_CAPEX_EXEMPT_SYMBOLS
        assert "ALL" not in symbols
        assert "HIG" not in symbols

    def test_depository_institution_sic_codes_untouched(self) -> None:
        """This fix must not widen the bank SIC-code allowlist - insurance stays a
        separate, symbol-based mechanism."""
        assert 6311 not in SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES
        assert 6798 not in SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES


class TestFcfYieldComputesForCapexExemptInsurerGivenZeroCapex:
    """A capex-exempt insurer's coerced-to-0 capex must flow through _compute_valuations
    exactly like the bank case (test_bank_capex_structural_gap_fixed_20260822.py) - locks in
    that AFL-shaped inputs (real OCF, capex coerced to 0) produce a real fcf_yield."""

    def test_insurer_shaped_inputs_produce_real_fcf_yield(self) -> None:
        loader = SecValuationsLoader.__new__(SecValuationsLoader)
        result = loader._compute_valuations(
            symbol="AFL",
            current_price=110.0,
            shares_out=580_000_000.0,
            ttm_eps=7.0,
            ttm_revenue=18_800_000_000.0,
            book_value=25_000_000_000.0,
            ocf=2_555_000_000.0,  # real AFL FY2025 operating cash flow
            capex=0,  # coerced from None by the fetch_incremental fix under test
            prior_year_eps=6.5,
            dividends_paid=1_198_000_000.0,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["fcf_yield"] is not None
        assert result["fcf_yield"] > 0
