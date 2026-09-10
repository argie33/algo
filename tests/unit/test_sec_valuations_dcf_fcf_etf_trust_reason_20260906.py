"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to test_sec_valuations_dcf_fcf_reit_reason_20260905.py): sec_valuations.
dcf_fcf_unavailable_reason never distinguished a physical commodity/currency/crypto trust
(GLD/GLDM/IAU/BITW/CPER/USCI-class - see vqg_symbol_gates.
_get_etf_trust_no_stockholders_equity_symbols's docstring) - which structurally never tags a
CapitalExpenditures concept either (it holds bullion/currency/crypto/futures, not PP&E) - from
a generic missing-cash-flow-data gap. Same real business-model fact already recognized for
quality_metrics' own "etf_trust_no_gaap_financials" label throughout vqg_quality.py, and the
same "SecValuationYieldDcfMixin has no access to the gate helper's class hierarchy" shape as
the sibling REIT/RIC fixes - fixed via a small inline etf_symbols/annual_balance_sheet query
instead (SecValuationsLoader doesn't mix in vqg_symbol_gates.SymbolGateMixin).

Live-confirmed 2 active-universe symbols (CPER, USCI) hitting this exact shape.
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _SicAndEtfTrustCursor:
    """Query-aware fake cursor - first query is the sic_code lookup, second (only reached
    when sic_code isn't REIT/insurance) is the etf_trust existence check."""

    def __init__(self, sic_code, is_etf_trust):
        self._sic_code = sic_code
        self._is_etf_trust = is_etf_trust
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "sic_code" in self.last_query:
            return (self._sic_code,)
        if self.last_query and "etf_symbols" in self.last_query:
            return (1,) if self._is_etf_trust else None
        return None

    def fetchall(self):
        return []


def _call(loader, symbol, sic_code, is_etf_trust):
    with patch("loaders.helpers.sec_valuations_yield_dcf.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = _SicAndEtfTrustCursor(sic_code, is_etf_trust)
        return loader._compute_yield_and_dcf_fields(
            symbol,
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
            entity_shares_out=50_000_000.0,
            stock_based_compensation=None,
            dcf_eps_cagr_pct=None,
            equity_risk_premium=None,
            net_borrowing=None,
            common_stock_repurchased=None,
        )


class TestSecValuationsDcfFcfEtfTrustReason:
    def test_etf_trust_symbol_reports_etf_trust_no_gaap_financials_reason(self):
        loader = _make_loader()
        result = _call(loader, "CPER", sic_code=None, is_etf_trust=True)

        assert result["dcf_fcf_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_reit_sic_code_takes_priority_over_etf_trust_check(self):
        # A REIT-coded symbol must never even reach the etf_trust query (checked first, more
        # specific) - is_etf_trust=True here would fail the test if the ordering were wrong.
        loader = _make_loader()
        result = _call(loader, "MFA", sic_code=6798, is_etf_trust=True)

        assert result["dcf_fcf_unavailable_reason"] == "reit_special_entity"

    def test_non_etf_trust_symbol_keeps_generic_reason(self):
        loader = _make_loader()
        result = _call(loader, "ACTU", sic_code=2834, is_etf_trust=False)

        assert result["dcf_fcf_unavailable_reason"] == "missing_cash_flow_data"
