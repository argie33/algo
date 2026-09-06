"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, implausible-value
continuation): _compute_margin_volatility's own reason vocabulary ("implausible_ratio"/
"insufficient_history") is entirely different from the ETF-trust/RIC/blank-check
recategorization loops inside _compute_quality_metrics (which only match reasons like
"stockholders_equity_not_reported"/"missing_sec_data") - margin_volatility is computed one
level up, in load_value_quality_growth_metrics.py's fetch_incremental, specifically because it
needs the multi-year income_rows history _compute_quality_metrics doesn't have. Live-confirmed
via FXF/FXY (Invesco CurrencyShares trusts): revenue is $0 for most fiscal years but real/tiny
for 2-3 others, and an older year's tiny-revenue-vs-loss ratio trips the |margin|>1000 guard -
fewer than 3 usable years survive AND at least one was implausible, so "implausible_ratio"
fires even though a currency trust has no "margin" concept to be volatile in.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestMarginVolatilityRecategorization:
    def test_etf_trust_symbol_implausible_ratio_recategorized(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset({"FXF"}))
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset())

        result = loader._recategorize_margin_volatility_reason("FXF", "implausible_ratio")

        assert result == "etf_trust_no_gaap_financials"

    def test_etf_trust_symbol_insufficient_history_recategorized(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset({"GLDM"}))
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset())

        result = loader._recategorize_margin_volatility_reason("GLDM", "insufficient_history")

        assert result == "etf_trust_no_gaap_financials"

    def test_ric_symbol_recategorized(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset({"GGN"}))
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset())

        result = loader._recategorize_margin_volatility_reason("GGN", "insufficient_history")

        assert result == "registered_investment_company_no_xbrl"

    def test_blank_check_symbol_recategorized(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset({"SPAC1"}))

        result = loader._recategorize_margin_volatility_reason("SPAC1", "insufficient_history")

        assert result == "no_revenue_reported"

    def test_real_operating_company_keeps_implausible_ratio(self, monkeypatch):
        """IMDX-shaped: a genuinely near-zero-revenue biotech's real, wild margin swings must
        stay "implausible_ratio" - the reason is correct and meaningful, not a data gap."""
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset())

        result = loader._recategorize_margin_volatility_reason("IMDX", "implausible_ratio")

        assert result == "implausible_ratio"

    def test_none_reason_passes_through_unchanged(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset({"FXF"}))
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
        monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: frozenset())

        result = loader._recategorize_margin_volatility_reason("FXF", None)

        assert result is None
