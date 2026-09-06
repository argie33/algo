"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): sec_valuations_
yield_dcf.py's avg_fcf_fallback rescue only ever substituted a POSITIVE multi-year average for a
None fcf_base (latest year's capex not yet tagged) - a real, computed but NEGATIVE multi-year
average left fcf_base (and therefore dcf_fcf_base) None entirely, mislabeling a genuine cash-burn
company as `missing_cash_flow_data` ("Missing SEC/XBRL data") instead of `negative_free_cash_flow`
("Legitimate / not applicable"). Live-confirmed AQB/APMD/OGEN and 130+ more universe symbols: real
OCF/capex on file for 2+ of the last 3 fiscal years, all negative, only the LATEST year's capex not
yet re-tagged - the cash-flow data was never missing, just consistently negative.

Fix: when the single-year fcf_base is None (not merely negative), adopt avg_fcf_fallback
regardless of sign - only a real negative single-year fcf_base still requires a POSITIVE average
to be rescued (the original 2026-08-18 behavior, unchanged).
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestDcfFcfNegativeAvgFallbackReason:
    def test_none_fcf_base_with_negative_avg_fallback_reports_negative_not_missing(self):
        loader = _make_loader()
        # capex=None -> single-year fcf_base is None (latest year's capex not yet tagged).
        # avg_fcf_fallback is real but negative (genuine multi-year cash burn).
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext"):
            result = loader._compute_yield_and_dcf_fields(
                "AQB",
                current_price=10.0,
                market_cap=500_000_000.0,
                ttm_eps=None,
                ttm_revenue=None,
                ocf=-8_739_656.0,
                capex=None,
                prior_year_eps=None,
                dividends_paid=None,
                total_debt=None,
                total_cash=None,
                ebitda=None,
                avg_fcf_fallback=-19_000_000.0,
                beta=None,
                risk_free_rate=None,
                entity_shares_out=50_000_000.0,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["dcf_fcf_unavailable_reason"] == "negative_free_cash_flow"

    def test_none_fcf_base_with_none_avg_fallback_still_reports_missing(self):
        loader = _make_loader()
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value.fetchone.return_value = (2834,)
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

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"

    def test_real_negative_fcf_base_not_rescued_by_negative_avg(self):
        """A real, already-computed negative single-year fcf_base must still only be rescued by
        a POSITIVE average - preserves the original 2026-08-18 behavior unchanged."""
        loader = _make_loader()
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext"):
            result = loader._compute_yield_and_dcf_fields(
                "XYZ",
                current_price=10.0,
                market_cap=500_000_000.0,
                ttm_eps=None,
                ttm_revenue=None,
                ocf=-1_000_000.0,
                capex=500_000.0,
                prior_year_eps=None,
                dividends_paid=None,
                total_debt=None,
                total_cash=None,
                ebitda=None,
                avg_fcf_fallback=-2_000_000.0,
                beta=None,
                risk_free_rate=None,
                entity_shares_out=50_000_000.0,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["dcf_fcf_unavailable_reason"] == "negative_free_cash_flow"
