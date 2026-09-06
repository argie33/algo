"""Regression test (2026-09-05, goal: "implausible values" sweep follow-up):
sec_valuations.dcf_fcf_unavailable_reason never distinguished a REIT (SIC 6798) or insurance
carrier (SIC 6311/6321/6331/6351/6361/6399) - which structurally never tags a meaningful capex
figure the way an operating company does - from a generic missing-cash-flow-data gap. Same
real business-model fact already recognized for quality_metrics' own "reit_special_entity"
label throughout vqg_quality.py, and the same "SecValuationYieldDcfMixin has no access to the
gate helper's class hierarchy" shape as the sibling RIC fix
(test_sec_valuations_dcf_fcf_ric_reason_20260905.py) - fixed via a small inline SIC-code query
instead.

Live-confirmed 27 universe symbols (MFA/SKT/SELF and siblings, all SIC 6798) hitting this exact
shape.
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _SicCodeCursor:
    def __init__(self, sic_code):
        self._sic_code = sic_code
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "sic_code" in self.last_query:
            return (self._sic_code,)
        return None

    def fetchall(self):
        return []


class TestSecValuationsDcfFcfReitReason:
    def test_reit_symbol_reports_reit_special_entity_reason(self):
        loader = _make_loader()
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _SicCodeCursor(sic_code=6798)
            result = loader._compute_yield_and_dcf_fields(
                "MFA",
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
                entity_shares_out=None,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["dcf_fcf_unavailable_reason"] == "reit_special_entity"

    def test_insurance_symbol_reports_reit_special_entity_reason(self):
        loader = _make_loader()
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _SicCodeCursor(sic_code=6331)
            result = loader._compute_yield_and_dcf_fields(
                "MCY",
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
                entity_shares_out=None,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["dcf_fcf_unavailable_reason"] == "reit_special_entity"

    def test_non_reit_symbol_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _SicCodeCursor(sic_code=2834)
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
                entity_shares_out=None,
                stock_based_compensation=None,
                dcf_eps_cagr_pct=None,
                equity_risk_premium=None,
                net_borrowing=None,
                common_stock_repurchased=None,
            )

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"
