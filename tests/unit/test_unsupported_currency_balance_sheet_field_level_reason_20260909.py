"""Regression test (2026-09-09, goal: "SEC/XBRL missing data under 500" sweep, field-level
follow-up to test_unsupported_currency_balance_sheet_row_level_reason_20260906.py): that fix
only wired _get_unsupported_currency_balance_sheet_symbols() into the row-level "all core
ratios missing" early return in vqg_quality.py's _compute_quality_metrics. A symbol like CRESY
(Assets tagged only under ARS - live-confirmed via real SEC companyfacts JSON) that has SOME
other ratio available (e.g. operating_margin, computed from revenue/operating_income alone,
neither of which needs total_assets/stockholders_equity) never hits that row-level early
return, so its individual roa/asset_turnover/debt_to_assets/gross_profitability/roe/
debt_to_equity/sustainable_growth_rate reasons fell through to the generic
"no_recent_total_assets_reported"/"stockholders_equity_not_reported"/"missing_sec_data"
instead of the real, specific "unsupported_currency_no_fx_rate" cause - same
reason-string-doesn't-match-real-cause bug class as the OCF recategorize loop just above this
new block in vqg_quality.py.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _partial_quality_row(fiscal_year=2024):
    # Index map (see vqg_quality.py's _compute_quality_metrics quality_row[N] reads):
    # 0=stockholders_equity 1=total_liabilities 2=total_assets 3=net_income 4=revenue
    # 5=operating_income 6=current_assets 7=current_liabilities 8=fiscal_year
    row = [None] * 35
    row[3] = 100.0  # net_income
    row[4] = 1000.0  # revenue
    row[5] = 200.0  # operating_income
    row[8] = fiscal_year
    row[19] = 800.0  # gross_profit - keeps gross_profitability's failure about total_assets,
    # not the separate no_gross_profit_concept ("reit_special_entity") branch.
    return row


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, unsupported_currency_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(
        loader,
        "_get_unsupported_currency_balance_sheet_symbols",
        lambda: unsupported_currency_symbols,
        raising=False,
    )
    return loader


class TestUnsupportedCurrencyBalanceSheetFieldLevelReason:
    def test_fpi_shaped_symbol_with_partial_data_gets_specific_field_reasons(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"CRESY"}))

        metrics = loader._compute_quality_metrics("CRESY", _partial_quality_row(), ev_metrics=None)

        # Row-level early return must NOT have fired - operating_margin is real (200/1000).
        assert metrics.get("data_unavailable") is not True

        for field in ("roa", "asset_turnover", "debt_to_assets", "gross_profitability"):
            assert metrics[f"{field}_unavailable_reason"] == "unsupported_currency_no_fx_rate", field

        for field in ("roe", "debt_to_equity", "sustainable_growth_rate"):
            assert metrics[f"{field}_unavailable_reason"] == "unsupported_currency_no_fx_rate", field

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"CRESY"}))

        metrics = loader._compute_quality_metrics("NORMALCO", _partial_quality_row(), ev_metrics=None)

        assert metrics["roa_unavailable_reason"] != "unsupported_currency_no_fx_rate"
        assert metrics["roe_unavailable_reason"] != "unsupported_currency_no_fx_rate"
