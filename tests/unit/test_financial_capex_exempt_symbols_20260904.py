"""Regression test for a 2026-09-04 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, capex_never_tagged_in_recent_filings follow-up): a small set of mortgage REITs and
consumer/specialty finance companies (NAVI, OMF, DX, ARR, ORC, CIM, RWT, MFIN, CHMI) never
tag any capex-related XBRL concept in their entire filing history - live-confirmed via real
companyfacts JSON: no PaymentsToAcquirePropertyPlantAndEquipment/
PaymentsToAcquireProductiveAssets/PaymentsForCapitalImprovements anywhere.

Mirrors INSURANCE_CAPEX_EXEMPT_SYMBOLS (test_insurance_capex_exempt_symbols_fixed_20260824.py)
exactly - a symbol allowlist, not a SIC-code allowlist, because SIC 6798 also covers ordinary
equity REITs (AVB, EQR) that DO tag real, material capex.
"""

from loaders.load_sec_valuations import SecValuationsLoader


class TestFinancialCapexExemptSymbols:
    def test_confirmed_structurally_capex_less_symbols_are_covered(self) -> None:
        symbols = SecValuationsLoader.FINANCIAL_CAPEX_EXEMPT_SYMBOLS
        for real_symbol in ("NAVI", "OMF", "DX", "ARR", "ORC", "CIM", "RWT", "MFIN", "CHMI"):
            assert real_symbol in symbols

    def test_ordinary_equity_reits_are_excluded(self) -> None:
        """AVB (AvalonBay) and EQR (Equity Residential) are equity REITs that own and
        maintain real physical apartment buildings - real, material capex - and must never
        be swept into this allowlist just because they share SIC 6798 with the mortgage
        REITs above."""
        symbols = SecValuationsLoader.FINANCIAL_CAPEX_EXEMPT_SYMBOLS
        assert "AVB" not in symbols
        assert "EQR" not in symbols

    def test_depository_institution_sic_codes_untouched(self) -> None:
        """This fix must not widen the bank SIC-code allowlist - mortgage REIT/consumer
        finance stays a separate, symbol-based mechanism, same as insurance."""
        assert 6798 not in SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES
        assert 6141 not in SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES


class TestFcfYieldComputesForCapexExemptFinancialGivenZeroCapex:
    """A capex-exempt mortgage REIT/finance company's coerced-to-0 capex must flow through
    _compute_valuations exactly like the bank/insurance cases - locks in that NAVI-shaped
    inputs (real OCF, capex coerced to 0) produce a real fcf_yield."""

    def test_navi_shaped_inputs_produce_real_fcf_yield(self) -> None:
        loader = SecValuationsLoader.__new__(SecValuationsLoader)
        result = loader._compute_valuations(
            symbol="NAVI",
            current_price=15.0,
            shares_out=80_000_000.0,
            ttm_eps=1.5,
            ttm_revenue=1_000_000_000.0,
            book_value=1_500_000_000.0,
            ocf=441_000_000.0,  # real NAVI FY2025 operating cash flow
            capex=0,  # coerced from None by the fetch_incremental fix under test
            prior_year_eps=1.2,
            dividends_paid=50_000_000.0,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["fcf_yield"] is not None
        assert result["fcf_yield"] > 0
