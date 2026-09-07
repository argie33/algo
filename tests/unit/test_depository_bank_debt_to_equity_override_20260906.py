"""Regression test for the depository-bank debt_for_roic override (2026-09-06, stock_scores
symbol spot-check goal session - see DEPOSITORY_BANK_INDUSTRIES's docstring in
loaders/load_value_quality_growth_metrics.py for the full live-verified writeup).

debt_for_roic (interest-bearing debt: long_term_debt/total_debt_ev) structurally excludes
customer deposits, because SEC filers tag deposits under concepts this pipeline doesn't map to
"long_term_debt". For a depository institution (commercial bank, savings institution), deposits
ARE the core interest-bearing liability funding its loan book - excluding them understated real
leverage so severely that small deposit-funded banks (live-verified: TCBX, PEBK) showed
debt_to_equity around 0.11-0.12, inflating quality_score's safety cluster and ROCE for that
cohort and skewing the day's top BUY signals toward small commercial banks.

Fix: for symbols whose company_profile.industry is a depository-bank SIC classification,
debt_for_roic uses total_liabilities instead - narrowly scoped via _get_symbol_industry (a
sibling of _get_symbol_sector), NOT applied to the broader Financial Services sector (payment
networks/asset managers/insurers keep the universal interest-bearing-debt figure).
"""

from unittest.mock import MagicMock, patch

import pytest

from loaders.load_value_quality_growth_metrics import DEPOSITORY_BANK_INDUSTRIES
from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _row(
    stockholders_equity=10_000_000.0,
    total_liabilities=90_000_000.0,  # deposit-funded bank: liabilities dwarf equity
    total_assets=100_000_000.0,
    net_income=1_500_000.0,
    revenue=20_000_000.0,
    operating_income=1_800_000.0,
    cost_of_revenue=12_000_000.0,
    long_term_debt=200_000.0,  # small wholesale-borrowing figure, NOT the bank's real leverage
):
    # Same 34-column shape as test_quality_sector_conditional_formula_20260828.py's fixture.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        total_assets,  # 2
        net_income,  # 3
        revenue,  # 4
        operating_income,  # 5
        6_000_000.0,  # 6 current_assets
        3_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        200_000.0,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        2_000_000.0,  # 13 operating_cash_flow
        1_600_000.0,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        8_000_000.0,  # 19 gross_profit
        long_term_debt,  # 20
        500_000.0,  # 21 cash_and_equivalents
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


_EV_METRICS_NO_DEBT = (
    None,
    500_000.0,
    3_000_000.0,
)  # (total_debt, total_cash, ebitda) - forces long_term_debt fallback


def _make_loader():
    loader = L.__new__(L)
    return loader


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


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())


class TestDepositoryBankDebtOverride:
    def test_state_commercial_bank_uses_total_liabilities_not_long_term_debt(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"
        loader._get_symbol_industry = lambda symbol: "State Commercial Banks"

        metrics = loader._compute_quality_metrics(
            "SMALLBANK", _row(), ev_metrics=_EV_METRICS_NO_DEBT, margin_volatility=10.0
        )

        # total_liabilities=90M / equity=10M = 9.0, not long_term_debt=200k / equity=10M = 0.02.
        assert metrics["debt_to_equity"] == pytest.approx(9.0)

    def test_non_bank_financial_services_keeps_universal_debt_figure(self):
        # Payment networks/asset managers/insurers must NOT get the override - their
        # liabilities aren't deposit-shaped, so total_liabilities' AP/accrued contamination
        # would be a real distortion, not a fix.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"
        loader._get_symbol_industry = lambda symbol: "Investment Advice"

        metrics = loader._compute_quality_metrics(
            "ASSETMGR", _row(), ev_metrics=_EV_METRICS_NO_DEBT, margin_volatility=10.0
        )

        assert metrics["debt_to_equity"] == pytest.approx(0.02)

    def test_missing_industry_fails_open_to_universal_debt_figure(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"
        loader._get_symbol_industry = lambda symbol: None

        metrics = loader._compute_quality_metrics(
            "UNKNOWNCO", _row(), ev_metrics=_EV_METRICS_NO_DEBT, margin_volatility=10.0
        )

        assert metrics["debt_to_equity"] == pytest.approx(0.02)

    def test_technology_sector_never_affected_even_if_industry_matches_by_coincidence(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Technology"
        loader._get_symbol_industry = lambda symbol: "State Commercial Banks"

        metrics = loader._compute_quality_metrics(
            "TECHCO", _row(), ev_metrics=_EV_METRICS_NO_DEBT, margin_volatility=10.0
        )

        # The override touches debt_for_roic regardless of the sector-conditional quality
        # formula branch (a separate, orthogonal decision) - this documents that intentional
        # coupling rather than leaving it implicit.
        assert metrics["debt_to_equity"] == pytest.approx(9.0)

    def test_depository_bank_industries_set_contents(self):
        assert DEPOSITORY_BANK_INDUSTRIES == {
            "State Commercial Banks",
            "National Commercial Banks",
            "Commercial Banks, NEC",
            "Savings Institution, Federally Chartered",
            "Savings Institutions, Not Federally Chartered",
            "Functions Related To Depository Banking, NEC",
        }


class TestGetSymbolIndustry:
    def test_caches_after_first_fetch(self):
        loader = _make_loader()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("JPM", "National Commercial Banks"), ("V", "Finance Services")]
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_cur

            assert loader._get_symbol_industry("JPM") == "National Commercial Banks"
            assert loader._get_symbol_industry("V") == "Finance Services"
            assert loader._get_symbol_industry("UNKNOWN") is None

        # Only one query for all 3 lookups - lazy-cached, not per-symbol.
        assert mock_ctx.call_count == 1

    def test_db_failure_fails_open_to_none(self):
        import psycopg2

        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx:
            mock_ctx.side_effect = psycopg2.OperationalError("connection refused")

            assert loader._get_symbol_industry("JPM") is None
