"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up):
total_debt_unavailable_reason/total_cash_unavailable_reason had no ETF/trust fallback, unlike
fcf_margin/fcf_yield's sibling chains elsewhere in this file which already check
_get_etf_trust_no_stockholders_equity_symbols(). That gate requires real annual_balance_sheet
history first (to distinguish a weird-shaped trust filing from an ETF simply too new to have
filed anything yet) - but total_debt/total_cash's absence for a UIT/index-tracking ETF isn't a
function of listing age at all, so requiring balance-sheet history excluded exactly the ETFs
that need it most.

Live-confirmed: SPY (listed 1993, 8,458 real trading days, ZERO annual_balance_sheet rows ever),
IGV (~5 years listed), and BKDV (~1.75 years listed) all fell through to generic
"missing_sec_data" for both total_debt and total_cash. Fixed via a new, unconditional
_get_etf_symbols() gate (bare etf_symbols membership, no balance-sheet-history precondition)
checked as the last fallback before the generic reason.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _NoMatchCursor:
    """Every gate query this loader may run returns empty - no symbol matches anything,
    including the new etf_symbols check."""

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _EtfSymbolCursor:
    """Serves a real match only to the bare `SELECT symbol FROM etf_symbols` query (matched by
    its distinctive shape: no WHERE/JOIN, unlike every other gate query in this file), empty for
    everything else."""

    def __init__(self, symbol):
        self._symbol = symbol
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM etf_symbols" in self._last_query and "WHERE" not in self._last_query:
            return [(self._symbol,)]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _quality_row():
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[11] = 10_000_000.0  # shares_outstanding
    return row


class TestTotalDebtCashEtfTrustZeroBalanceSheet:
    def _loader(self, monkeypatch, cursor):
        import loaders.load_value_quality_growth_metrics as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(cursor))
        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_spy_style_etf_reports_etf_trust_reason_for_total_debt(self, monkeypatch):
        loader = self._loader(monkeypatch, _EtfSymbolCursor("SPY"))
        ev_metrics = (None, None, 0.0, None)

        metrics = loader._compute_quality_metrics("SPY", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_spy_style_etf_reports_etf_trust_reason_for_total_cash(self, monkeypatch):
        loader = self._loader(monkeypatch, _EtfSymbolCursor("SPY"))
        ev_metrics = (None, None, 0.0, None)

        metrics = loader._compute_quality_metrics("SPY", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_cash"] is None
        assert metrics["total_cash_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_sec_valuations_reason_still_wins_over_etf_fallback(self, monkeypatch):
        # A real, specific sec_valuations.reason must keep priority over the new ETF fallback,
        # same precedence rule as every other sibling chain in this file.
        loader = self._loader(monkeypatch, _EtfSymbolCursor("SPY"))
        ev_metrics = (None, None, None, "income_statement_revenue_and_eps_null")

        metrics = loader._compute_quality_metrics("SPY", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt_unavailable_reason"] == "income_statement_revenue_and_eps_null"
        assert metrics["total_cash_unavailable_reason"] == "income_statement_revenue_and_eps_null"

    def test_non_etf_no_match_still_falls_back_to_generic_reason(self, monkeypatch):
        loader = self._loader(monkeypatch, _NoMatchCursor())
        ev_metrics = (None, None, 0.0, None)

        metrics = loader._compute_quality_metrics("AMBIGCO", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt_unavailable_reason"] == "missing_sec_data"
        assert metrics["total_cash_unavailable_reason"] == "missing_sec_data"
