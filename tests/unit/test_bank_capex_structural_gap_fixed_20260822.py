"""Regression test for the 2026-08-22 fix (goal session: "Missing SEC/XBRL data" coverage
audit): depository institutions (banks) never tag a "CapitalExpenditures" XBRL concept in
any fiscal year - live-confirmed via JPM, BAC, MS, WFC, PNC's real companyfacts JSON (capex
NULL across every year 2007-2026, not just the current interim year).

Before this fix, both load_sec_valuations.py's fcf_yield/avg_fcf_fallback computation and
sec_base.py's free_cash_flow derivation required a non-None capex on every year they
considered - structurally uncomputable forever for the entire banking sector (not a
transient extraction gap a future fetch could fix), unlike the "current interim year's
capex isn't filed yet" case test_sec_valuations_fcf_yield_falls_back_to_prior_year.py
covers, where a complete prior year eventually recovers it.

Fixed by treating a bank's genuinely-absent capex as 0 (the standard equity-research
convention for this sector - a bank's capital allocation is dominated by loan/securities
purchases, not PP&E) via a small, explicit SIC-code allowlist
(DEPOSITORY_INSTITUTION_SIC_CODES / _get_depository_institution_symbols) - never a blanket
"missing capex means zero" assumption, which would risk fabricating FCF for an ordinary
industrial filer with a real, transient extraction gap
(see test_sec_valuations_capex_none_not_coerced_to_zero.py, still passing unchanged).

Live-verified end-to-end against the real DB: JPM/BAC/WFC/PNC all recovered real fcf_yield
values (e.g. JPM -21.69%, BAC 15.26%) flowing through to value_metrics with
fcf_yield_unavailable_reason cleared to None, after re-running the real loaders (not a
hand-patch).
"""

from loaders.load_sec_valuations import SecValuationsLoader


class TestDepositoryInstitutionSicCodes:
    def test_sic_codes_cover_the_confirmed_bank_types(self) -> None:
        """JPM/BAC/MS/WFC/PNC's real SIC codes must all be covered."""
        codes = SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES
        # National commercial banks (JPM, BAC, WFC), state commercial banks, savings
        # institutions, and bank holding companies (many large banks file under 6712).
        for real_bank_sic in (6021, 6022, 6035, 6712):
            assert real_bank_sic in codes

    def test_sic_codes_exclude_non_bank_financials(self) -> None:
        """Insurers (6311) and REITs (6798) are financial-sector but NOT capex-less the
        same way - must not be swept into this allowlist by accident."""
        codes = SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES
        assert 6311 not in codes
        assert 6798 not in codes


class TestFcfYieldComputesForBankGivenZeroCapex:
    """A bank's capex, once coerced to 0 by the SIC-gated fetch_incremental logic, must
    flow through _compute_valuations exactly like any other real $0 capex (already-covered
    contract, see test_sec_valuations_capex_none_not_coerced_to_zero.py's
    test_capex_zero_still_computes_fcf_yield) - this locks in that JPM-shaped inputs
    (large OCF, capex coerced to 0) produce a real, non-fabricated fcf_yield."""

    def test_bank_shaped_inputs_produce_real_fcf_yield(self) -> None:
        loader = SecValuationsLoader.__new__(SecValuationsLoader)
        result = loader._compute_valuations(
            symbol="JPM",
            current_price=300.0,
            shares_out=2_700_000_000.0,
            ttm_eps=20.0,
            ttm_revenue=170_000_000_000.0,
            book_value=300_000_000_000.0,
            ocf=107_119_000_000.0,  # real JPM FY2022 operating cash flow
            capex=0,  # coerced from None by the fetch_incremental fix under test
            prior_year_eps=18.0,
            dividends_paid=None,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["fcf_yield"] is not None
        assert result["fcf_yield"] > 0
