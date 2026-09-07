"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): live DB scan
found 170 of 384 universe symbols carrying dcf_fcf_unavailable_reason='missing_cash_flow_data'
(CASH, TRN, and siblings) actually have a real, positive fcf_base - proven by their own real,
non-NULL fcf_yield, computed from that same fcf_base before any net-borrowing adjustment. The
cash-flow data was never missing; the DCF-only net-borrowing near-cancellation guard
(DCF_NET_BORROWING_MIN_RETAINED_FRACTION, see sec_valuations_dcf.py's IMMR-evidence docstring)
nulled dcf_fcf_base anyway, and the ground-truth reason block used to test only
`dcf_fcf_base is None`, which can't distinguish "never computable" from "computed then
deliberately rejected" - mislabeling a real business fact as a SEC/XBRL data gap and inflating
the coverage report's headline "Missing SEC/XBRL data" count.

sec_valuations_yield_dcf.py now tracks `dcf_fcf_nulled_by_net_borrowing` separately and reports
the distinct reason 'dcf_fcf_nulled_by_net_borrowing_distortion' (mapped to "Implausible /
rejected value" in coverage_category_rules.py, not "Missing SEC/XBRL data") for exactly this
case.
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestDcfFcfNetBorrowingDistortionReason:
    def test_real_fcf_base_nulled_by_net_borrowing_reports_distortion_reason(self):
        loader = _make_loader()
        # fcf_base = ocf - capex - sbc = 100 - 0 - 0 = 100 (real, positive - proven below by a
        # real fcf_yield). net_borrowing=-90 retains only 10% of fcf_base (100 + (-90) = 10),
        # below DCF_NET_BORROWING_MIN_RETAINED_FRACTION (0.15) and within
        # DCF_NET_BORROWING_MAX_FCF_MULTIPLE (10x) - the exact near-cancellation shape.
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            result = loader._compute_yield_and_dcf_fields(
                "CASH",
                current_price=10.0,
                market_cap=1_000_000.0,
                ttm_eps=None,
                ttm_revenue=None,
                ocf=100_000.0,
                capex=0.0,
                prior_year_eps=None,
                dividends_paid=None,
                total_debt=None,
                total_cash=None,
                ebitda=None,
                avg_fcf_fallback=None,
                beta=None,
                risk_free_rate=None,
                entity_shares_out=1_000_000.0,
                stock_based_compensation=0.0,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=-90_000.0,
                common_stock_repurchased=None,
            )
            # A real, positive fcf_base must never require a DB round-trip for the sic-code
            # REIT/insurance lookup - that branch is only reachable when fcf_base itself was
            # None, which this case (fcf_base=100) never hits.
            mock_db_ctx.assert_not_called()

        assert result["fcf_yield"] is not None and result["fcf_yield"] > 0
        assert result["intrinsic_value_per_share"] is None
        assert result["dcf_fcf_unavailable_reason"] == "dcf_fcf_nulled_by_net_borrowing_distortion"

    def test_genuinely_missing_cash_flow_still_reports_generic_reason(self):
        loader = _make_loader()
        # entity_shares_out is real (not None) here so this exercises the sic_code/
        # missing_cash_flow_data branch specifically - entity_shares_out=None would instead
        # hit the earlier shares_outstanding_unavailable_reason branch (see the sibling test
        # module's other coverage for that case), never reaching the code under test here.
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            # (2834,) for the SIC-code lookup (a real, non-REIT/insurance code), then None
            # for the etf_trust existence check (2026-09-06 addition) - not an etf_symbols
            # ticker, so this must still fall through to the generic reason.
            mock_db_ctx.return_value.__enter__.return_value.fetchone.side_effect = [(2834,), None]
            result = loader._compute_yield_and_dcf_fields(
                "ACTU",
                current_price=10.0,
                market_cap=500_000_000.0,
                ttm_eps=None,
                ttm_revenue=None,
                ocf=None,
                capex=None,
                prior_year_eps=None,
                dividends_paid=None,
                total_debt=None,
                total_cash=None,
                ebitda=None,
                avg_fcf_fallback=None,
                beta=None,
                risk_free_rate=None,
                entity_shares_out=1_000_000.0,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["fcf_yield"] is None
        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"
