"""Regression test for a 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero" sweep,
capex_never_tagged_in_recent_filings/missing_cash_flow_data continuation): a much larger batch
(216 symbols) than the hand-picked FINANCIAL_CAPEX_EXEMPT_SYMBOLS/INSURANCE_CAPEX_EXEMPT_SYMBOLS
lists, verified programmatically against live data.sec.gov/api/xbrl/companyfacts data across the
full capex-concept family (PP&E purchase/addition variants, the REIT real-estate-acquisition
family, PaymentsForCapitalImprovements, oil & gas capex concepts, CapitalExpenditures) - every
symbol below either never tagged any of those concepts in its full filing history, or last
tagged one in a stale (pre-2023) fiscal year. Foreign private issuers (different taxonomy),
closed-end funds/commodity ETFs/SPAC shells, and equity REITs confirmed to hold real physical
property (ALX, SKT, NLOP, SELF, IOR, MKZR) were deliberately excluded from this batch - see
LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS's own docstring in loaders/load_sec_valuations.py.

Mirrors test_financial_capex_exempt_symbols_20260904.py's structure.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_sec_valuations import SecValuationsLoader


class TestLargeBatchCapexExemptSymbols:
    def test_sample_of_verified_symbols_are_covered(self) -> None:
        symbols = SecValuationsLoader.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
        for real_symbol in (
            "APO",
            "ARES",
            "KKR",
            "AGNC",
            "IVR",
            "MFA",
            "MITT",
            "PMT",
            "RITM",
            "RC",
            "BXMT",
            "SUNS",
            "EARN",
            "SYF",
            "VOYA",
            "GOOD",
            "ADIL",
            "ACTU",
            "VKTX",
        ):
            assert real_symbol in symbols

    def test_physical_property_equity_reits_are_excluded(self) -> None:
        """ALX (Alexander's), SKT (Tanger), NLOP, SELF, IOR, MKZR were live-spot-checked and
        found to have real capex under a concept this batch's scan didn't cover - unlike the
        mortgage/commercial-finance REITs above, whose business model has no physical
        property to improve at all."""
        symbols = SecValuationsLoader.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
        for excluded in ("ALX", "SKT", "NLOP", "SELF", "IOR", "MKZR", "AVB", "EQR"):
            assert excluded not in symbols

    def test_foreign_private_issuers_are_excluded(self) -> None:
        """This scan only checked us-gaap concepts - IFRS filers (foreign private issuers)
        use different concept names it can't see, so they're left for a narrower,
        individually-verified fix instead of being guessed at here."""
        symbols = SecValuationsLoader.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
        for fpi in ("MFC", "CRESY", "BBAR", "IRS", "CEPU", "CPAC"):
            assert fpi not in symbols

    def test_no_duplicate_membership_with_existing_allowlists(self) -> None:
        """This batch must not re-list a symbol already covered by an existing, independently
        verified allowlist - duplication would just be noise."""
        large_batch = SecValuationsLoader.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
        existing = (
            SecValuationsLoader.INSURANCE_CAPEX_EXEMPT_SYMBOLS | SecValuationsLoader.FINANCIAL_CAPEX_EXEMPT_SYMBOLS
        )
        assert large_batch.isdisjoint(existing)

    def test_sec_base_mirror_matches_load_sec_valuations(self) -> None:
        """loaders/helpers/sec_base.py's _LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS must stay in sync
        with load_sec_valuations.py's LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS - same duplication
        convention already relied on for _FINANCIAL_CAPEX_EXEMPT_SYMBOLS/
        _INSURANCE_CAPEX_EXEMPT_SYMBOLS."""
        assert (
            SecEdgarStatementLoader._LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
            == SecValuationsLoader.LARGE_BATCH_CAPEX_EXEMPT_SYMBOLS
        )


class TestFcfYieldComputesForLargeBatchCapexExemptGivenZeroCapex:
    """A large-batch capex-exempt symbol's coerced-to-0 capex must flow through
    _compute_valuations exactly like the bank/insurance/financial cases."""

    def test_apo_shaped_inputs_produce_real_fcf_yield(self) -> None:
        loader = SecValuationsLoader.__new__(SecValuationsLoader)
        result = loader._compute_valuations(
            symbol="APO",
            current_price=150.0,
            shares_out=600_000_000.0,
            ttm_eps=5.0,
            ttm_revenue=20_000_000_000.0,
            book_value=15_000_000_000.0,
            ocf=7_246_000_000.0,  # real APO FY2025 operating cash flow
            capex=0,  # coerced from None by the fetch_incremental fix under test
            prior_year_eps=4.0,
            dividends_paid=1_201_000_000.0,
            total_debt=None,
            total_cash=None,
            ebitda=None,
        )

        assert result["fcf_yield"] is not None
        assert result["fcf_yield"] > 0
