"""Regression test (2026-08-18, "no SEC data" audit goal, roic_pct follow-up): roic_pct's
effective_tax_rate computation requires roic_pretax_income > 0 (a real reported pretax loss
makes "effective tax rate" undefined in the usual sense - real filers report all sorts of tax
expense/benefit against a loss from valuation allowances, NOL carrybacks, etc., not a
meaningful rate). When that gate fails, roic_pct was always labeled the generic
"missing_sec_data" reason - identical to what an actual SEC extraction gap gets - even though
we have complete real tax_expense/pretax_income data and the company is simply unprofitable
that year. Same distinction already established for pe_ratio/ev_ebitda/payout_ratio via the
"unprofitable_stock" reason (see their code in load_value_quality_growth_metrics.py).

Fixed by tracking roic_pct_unprofitable = (roic_pretax_income is not None and
roic_pretax_income <= 0) and using it in the final reason assignment, same precedence as
"implausible_ratio" (garbage-value bound still wins if it also fires).
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


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeCursorReturning:
    def __init__(self, row):
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return self._row


class _FakeDatabaseContextReturning:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return _FakeCursorReturning(self._row)

    def __exit__(self, *exc):
        return False


def _make_loader_with_fallback_row(monkeypatch, fallback_row):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContextReturning(fallback_row))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    revenue=None,
    operating_income=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        interest_expense,  # 10 interest_expense
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
        income_tax_expense,  # 22
        pretax_income,  # 23
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


class TestRoicPctUnprofitableStockReason:
    def test_real_pretax_loss_reports_unprofitable_stock(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=-3_000_000.0,
            income_tax_expense=-1_000_000.0,
            pretax_income=-5_000_000.0,
        )

        metrics = loader._compute_quality_metrics("LOSSCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "unprofitable_stock"

    def test_genuinely_missing_tax_data_still_reports_missing_sec_data(self, monkeypatch):
        # Control: no tax/pretax data anywhere (not a loss-year suppression) must keep the
        # original "missing_sec_data" reason, not be swept into "unprofitable_stock".
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=10_000_000.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"

    def test_profitable_company_still_computes_roic_pct(self, monkeypatch):
        # Control: a real, profitable, in-bounds case must be unaffected by this change.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=40_000_000.0,
            income_tax_expense=8_000_000.0,
            pretax_income=32_000_000.0,
        )

        metrics = loader._compute_quality_metrics("PROFITCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None

    def test_real_tax_benefit_in_profitable_year_computes_roic_pct(self, monkeypatch):
        # FIXED 2026-08-18: a real, SEC-reported net tax BENEFIT in a profitable year (implied
        # rate -20%, well within the same +/-60% magnitude bound already used for the positive
        # side) used to be rejected outright by the old [0.0, 0.60] bound - live-confirmed on
        # META (FY2026: $21.75B pretax income, $5.02B tax benefit, rate -23.1%) and 2,698 other
        # annual_income_statement rows universe-wide. Must now compute a real roic_pct instead
        # of being marked unavailable.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=120_000_000.0,
            income_tax_expense=-20_000_000.0,
            pretax_income=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("TAXBENEFITCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None

    def test_implausible_negative_tax_rate_reports_implausible_ratio(self, monkeypatch):
        # A profitable year (pretax_income>0, so NOT the unprofitable_stock path) whose implied
        # tax rate (-200%) is still an implausible magnitude - the same "near-zero pretax
        # income distorts NOPAT worse than marking unavailable" reasoning as the +0.60 ceiling,
        # just on the negative side. Must stay unavailable, tagged "implausible_ratio" (not the
        # generic "missing_sec_data" a real SEC extraction gap would get).
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=6_000_000.0,
            income_tax_expense=-10_000_000.0,
            pretax_income=5_000_000.0,
        )

        metrics = loader._compute_quality_metrics("EXTREMETAXCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "implausible_ratio"

    def test_anchor_has_tax_pretax_but_no_operating_income_or_interest_expense_rescues_from_history(self, monkeypatch):
        # FIX 2026-08-18 (live: ABCB/Ameris Bancorp, 828 universe symbols): the fallback
        # search below only ran when the anchor year ITSELF lacked income_tax_expense or
        # pretax_income. Banks (and other filers that never tag OperatingIncomeLoss) commonly
        # have an anchor year with real tax+pretax data but NEITHER operating_income NOR
        # interest_expense - the fallback query never fired, leaving roic_pct permanently
        # unavailable even though an older 10-K has a fully self-consistent row. Must now
        # search history and compute a real roic_pct.
        # 5th element (net_income) added 2026-08-18 alongside the never-tagged-pretax-income
        # roic_pct fallback - unused here (pretax_income is present) but required so the
        # tuple index doesn't go out of range.
        fallback_row = (
            7_000_000.0,
            28_000_000.0,
            None,
            12_000_000.0,
            21_000_000.0,
        )  # tax, pretax, op_income, interest_expense, net_income
        loader = _make_loader_with_fallback_row(monkeypatch, fallback_row)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=None,
            income_tax_expense=8_000_000.0,
            pretax_income=32_000_000.0,
            interest_expense=None,
        )

        metrics = loader._compute_quality_metrics("BANKCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None
