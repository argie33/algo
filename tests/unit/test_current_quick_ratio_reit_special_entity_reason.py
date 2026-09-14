"""Regression test: current_ratio/quick_ratio_unavailable_reason must distinguish REITs/banks
(unclassified balance sheet - AssetsCurrent/LiabilitiesCurrent is a different accounting model,
not a data gap) from a genuine SEC extraction gap.

Found live 2026-08-17 (goal: "no SEC data" audit, TRNO dashboard screenshot): the frontend
(StockScoreAccordion.jsx) already defines a "reit_special_entity" reason string with copy
explaining the accounting difference, but the backend never populated it - every REIT/bank/
insurer got the generic "missing_sec_data" ("SEC data not available") instead, which reads as a
loader bug even though the data literally doesn't exist for these filers. A prior commit
(b04b64722) claimed this fix in its message but landed unrelated code instead (a git race in
this heavily concurrent repo - see sec_cik_lookup_gap_browse_edgar_fallback_20260817 memory), so
the bug was still live. Live-verified against this DB: of 1185 quality_metrics rows with
current_ratio_unavailable_reason='missing_sec_data', the overwhelming majority (REIT/bank/
insurer/broker-dealer SIC codes, cross-checked against never-reported-current_assets history)
are this structural case, not a real extraction gap.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(current_assets=None, current_liabilities=None):
    # Same 33-column shape as test_quality_metrics_ratio_garbage_value_bound.py's fixture.
    return (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        400_000_000.0,  # 4 revenue
        30_000_000.0,  # 5 operating_income
        current_assets,  # 6
        current_liabilities,  # 7
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
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
    )


class _FakeCursor:
    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        # _get_unclassified_balance_sheet_symbols()'s history check - only reached when both
        # current_assets/current_liabilities are absent (see the `and` short-circuit in
        # _compute_quality_metrics), i.e. only by the "both fields absent" test below. Report
        # TRNO as having never reported current_assets in its 3 most recent fiscal years on file.
        if "HAVING COUNT(current_assets) = 0" in self._last_query:
            return [("TRNO",)]
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


class TestReitBankUnclassifiedBalanceSheet:
    def test_both_fields_absent_gets_special_entity_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=None, current_liabilities=None)

        metrics = loader._compute_quality_metrics("TRNO", row, ev_metrics=None)

        assert metrics["current_ratio"] is None
        assert metrics["current_ratio_unavailable_reason"] == "reit_special_entity"
        assert metrics["quick_ratio"] is None
        assert metrics["quick_ratio_unavailable_reason"] == "reit_special_entity"

    def test_only_one_field_absent_keeps_generic_reason(self, monkeypatch):
        # Only one of the pair missing (real extraction/timing gap, not a structural
        # accounting difference - a genuinely unclassified balance sheet lacks BOTH).
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=150_000_000.0, current_liabilities=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["current_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["quick_ratio_unavailable_reason"] == "missing_sec_data"

    def test_normal_ratio_still_computes_and_reason_is_none(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=150_000_000.0, current_liabilities=100_000_000.0)

        metrics = loader._compute_quality_metrics("TRNO", row, ev_metrics=None)

        assert metrics["current_ratio"] == 1.5
        assert metrics["current_ratio_unavailable_reason"] is None
        assert metrics["quick_ratio_unavailable_reason"] is None

    def test_classification_query_checks_recent_years_not_all_history(self, monkeypatch):
        # FIXED 2026-08-18: the old query was `GROUP BY symbol HAVING COUNT(current_assets) = 0`
        # with no windowing - a company that reported a classified balance sheet years ago and
        # switched to unclassified since (e.g. ENVA: classified FY2013-2014, unclassified every
        # year FY2015-2026) never satisfied "zero ever", so it fell through to the generic
        # "missing_sec_data" label instead of "reit_special_entity". The fixed query must window
        # to each symbol's most recent fiscal years via ROW_NUMBER()/rn <= 3, not scan all history.
        import loaders.load_value_quality_growth_metrics as mod

        captured = {}

        class _CapturingCursor(_FakeCursor):
            def execute(self, query, params=None):
                captured["query"] = query
                super().execute(query, params)

        class _CapturingDatabaseContext:
            def __enter__(self):
                return _CapturingCursor()

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _CapturingDatabaseContext())
        fresh_loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        fresh_loader._get_unclassified_balance_sheet_symbols()

        assert "ROW_NUMBER()" in captured["query"]
        assert "rn <= 3" in captured["query"]
