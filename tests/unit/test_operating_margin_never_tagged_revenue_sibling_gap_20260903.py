"""Regression test: operating_margin_unavailable_reason must also treat a symbol from the
broader _get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols()/
_get_blank_check_symbols() gate as "no_revenue_reported" when operating_income_for_margin is
never tagged at all - not just fall through to generic "missing_sec_data" when
_get_no_tax_concept_symbols() (the REIT/tonnage-tax reit_special_entity gate) doesn't match.

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction, sibling-left-behind bug class -
same shape as gross_margin/roic_pct/roce_pct's fix earlier this session): operating_margin's
total_assets fallback only ever runs when operating_income_for_margin is non-None, so a symbol
with operating_income_for_margin NEVER tagged in any fiscal year falls straight to
reit_special_entity-or-generic. _get_no_tax_concept_symbols() is scoped to filers that never tag
pretax_income/income_tax_expense (REITs/tonnage-tax shipping) - it doesn't match passive
commodity/crypto trusts that DO tag real tax lines but structurally have zero revenue and zero
operating_income. Live-confirmed 23 of 98 universe operating_margin "missing_sec_data" rows
(AAAU, BDRY, BWET, DRUG - genuinely zero operating_income AND zero revenue in every fiscal year
on file) are this exact population.
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
    no_tax_concept_symbols=frozenset(),
    operating_income_available_elsewhere=frozenset(),
    blank_check_symbols=frozenset(),
    no_recent_revenue_symbols=frozenset(),
    never_tagged_revenue_symbols=frozenset(),
):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_no_tax_concept_symbols", lambda: no_tax_concept_symbols)
    monkeypatch.setattr(
        loader, "_get_operating_income_available_elsewhere_symbols", lambda: operating_income_available_elsewhere
    )
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
    monkeypatch.setattr(loader, "_get_no_recent_revenue_symbols", lambda: no_recent_revenue_symbols)
    monkeypatch.setattr(loader, "_get_never_tagged_revenue_symbols", lambda: never_tagged_revenue_symbols)
    return loader


def _quality_row(revenue=None, total_assets=700_000_000.0):
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = revenue
    row[5] = None  # operating_income - never tagged
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[23] = None  # pretax_income - never tagged, so no EBIT-approximation fallback either
    return row


class TestOperatingMarginNeverTaggedRevenueSiblingGap:
    def test_never_tagged_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("TRUST", row, ev_metrics=None)

        assert metrics["operating_margin"] is None
        assert metrics["operating_margin_unavailable_reason"] == "no_revenue_reported"

    def test_no_recent_revenue_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("TRUST", row, ev_metrics=None)

        assert metrics["operating_margin"] is None
        assert metrics["operating_margin_unavailable_reason"] == "no_revenue_reported"

    def test_no_tax_concept_symbol_still_prefers_reit_special_entity(self, monkeypatch):
        # A REIT-shaped symbol in BOTH gates must keep the more specific reit_special_entity
        # label (checked first in the chain), not be overridden by the newer no_revenue branch.
        loader = _make_loader(
            monkeypatch,
            no_tax_concept_symbols=frozenset({"REIT"}),
            never_tagged_revenue_symbols=frozenset({"REIT"}),
        )
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("REIT", row, ev_metrics=None)

        assert metrics["operating_margin_unavailable_reason"] == "reit_special_entity"

    def test_symbol_in_no_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"TRUST"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("OTHER", row, ev_metrics=None)

        assert metrics["operating_margin_unavailable_reason"] == "missing_sec_data"
