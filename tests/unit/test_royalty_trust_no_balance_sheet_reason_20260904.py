"""Regression test: total_debt/debt_to_equity/interest_coverage/cash/FCF-derived
quality_metrics fields for pure oil/gas grantor royalty trusts (NRT/MTR/CRT/PBT/SBR/SJT) must
report "reit_special_entity", not the generic "missing_sec_data"/"total_debt_not_itemized"/
"no_recent_cash_reported"/"interest_expense_not_itemized" reasons.

Found live 2026-09-04 (goal session: "Missing SEC/XBRL data" headline reduction sweep): these 6
symbols already get "reit_special_entity" for current_ratio/quick_ratio/gross_margin/
gross_profitability (their unclassified-balance-sheet structure is recognized there), but the
debt/cash/interest/FCF-derived fields fell through to generic reasons instead - the same
structural gap (a grantor trust distributing royalty proceeds has no debt, cash, or operating-
income concept in the traditional GAAP-operating-company sense), just not recognized on those
fields. See ValueQualityGrowthMetricsLoader._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS's own
docstring for the full evidence trail (live company_info_sec SIC 6792/6795 check, and why this
is a small hand-curated set rather than a SIC-code rule - SIC 6792/6795 also covers real
operating companies like RGLD/SSRM/TFPM/TPL that must not be swept in).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_current_quick_ratio_reit_special_entity_reason.py's fixture.
    base = [
        None,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    ]
    return tuple(base)


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoyaltyTrustNoBalanceSheetReason:
    def test_trust_symbol_gets_reit_special_entity_for_debt_and_cash_fields(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        metrics = loader._compute_quality_metrics("PBT", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "reit_special_entity"
        assert metrics["total_cash"] is None
        assert metrics["total_cash_unavailable_reason"] == "reit_special_entity"
        assert metrics["free_cash_flow_unavailable_reason"] == "reit_special_entity"
        assert metrics["operating_cash_flow_unavailable_reason"] == "reit_special_entity"

    def test_non_trust_symbol_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["total_debt_unavailable_reason"] != "reit_special_entity"
        assert metrics["total_cash_unavailable_reason"] != "reit_special_entity"

    def test_trust_symbol_with_real_debt_value_is_untouched(self, monkeypatch):
        # A trust symbol that DOES have a real value for a field (shouldn't happen for these 6
        # in practice, but the override must not clobber real data if it ever does) keeps it.
        loader = _make_loader(monkeypatch)
        metrics = loader._compute_quality_metrics("PBT", _quality_row(), ev_metrics=(5_000_000.0, None, None, None))

        assert metrics["total_debt"] == 5_000_000.0
        assert metrics.get("total_debt_unavailable_reason") is None

    def test_trust_symbol_gets_reit_special_entity_for_asset_turnover(self, monkeypatch):
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up):
        # asset_turnover (revenue/total_assets) was never added to _trust_recategorize_fields
        # despite this fixture's revenue=None already producing a "missing_sec_data"-shaped
        # fallback that fits _trust_source_reasons - same half-wired-fix pattern as the RIC
        # recategorization loop's own sibling fix.
        loader = _make_loader(monkeypatch)
        metrics = loader._compute_quality_metrics("PBT", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "reit_special_entity"
