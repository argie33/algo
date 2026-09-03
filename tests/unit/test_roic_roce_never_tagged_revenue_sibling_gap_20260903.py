"""Regression test: roic_pct/roce_pct_unavailable_reason must also treat a symbol from the
broader _get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols() gate as
"no_revenue_reported", not just a symbol caught by the narrower SIC-code
_get_blank_check_symbols() check (roic_pct) or fall through to generic entirely (roce_pct, which
had no no_revenue_reported branch at all before this fix).

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction, sibling-left-behind bug class -
same shape as gross_margin's fix earlier this session, see
test_gross_margin_never_tagged_revenue_sibling_gap_20260903.py): live-confirmed 39 of 217 (roic_pct)
and 26 of 189 (roce_pct) universe "missing_sec_data" rows are non-blank-check, genuinely-no-revenue
symbols - dominated by commodity/crypto trusts (GLD, GLDM, GLTR, IAUM, AAAU, BTCO) that
structurally report no revenue by their trust/ETF nature, the same "no operating business" fact
blank-check SPACs represent, just not SIC-classified as one.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


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


def _make_loader(
    monkeypatch,
    blank_check_symbols=frozenset(),
    no_recent_revenue_symbols=frozenset(),
    never_tagged_revenue_symbols=frozenset(),
):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
    monkeypatch.setattr(loader, "_get_no_recent_revenue_symbols", lambda: no_recent_revenue_symbols)
    monkeypatch.setattr(loader, "_get_never_tagged_revenue_symbols", lambda: never_tagged_revenue_symbols)
    return loader


def _quality_row(stockholders_equity=250_000_000.0, long_term_debt=None, cash_and_equivalents=5_000_000.0):
    # Same 34-column shape as test_blank_check_spac_no_revenue_reason.py's fixture. Real
    # stockholders_equity/debt inputs present so this doesn't fall to an earlier structural
    # gate (stockholders_equity_not_reported/total_debt_not_itemized) before reaching the
    # no_revenue_reported branch under test. operating_income/tax fields left None so BOTH
    # roic_pct (needs effective_tax_rate) and roce_pct (needs roic_operating_income) genuinely
    # fail to compute, same as the real commodity/crypto-trust population this fix targets.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
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
        long_term_debt,  # 20
        cash_and_equivalents,  # 21
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


class TestRoicRoceNeverTaggedRevenueSiblingGap:
    def test_roic_pct_never_tagged_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(long_term_debt=80_000_000.0)

        metrics = loader._compute_quality_metrics("TRUST", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "no_revenue_reported"

    def test_roic_pct_no_recent_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(long_term_debt=80_000_000.0)

        metrics = loader._compute_quality_metrics("TRUST", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "no_revenue_reported"

    def test_roce_pct_never_tagged_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(long_term_debt=80_000_000.0)

        metrics = loader._compute_quality_metrics("TRUST", row, ev_metrics=None)

        assert metrics["roce_pct"] is None
        assert metrics["roce_pct_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_in_no_gate_keeps_generic_reason(self, monkeypatch):
        # Sanity check: a symbol in none of the three revenue-gap sets stays "missing_sec_data",
        # not silently reclassified as no-revenue.
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(long_term_debt=80_000_000.0)

        metrics = loader._compute_quality_metrics("OTHER", row, ev_metrics=None)

        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"
        assert metrics["roce_pct_unavailable_reason"] == "missing_sec_data"
