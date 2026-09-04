"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, live static-outlier check): total_cash/cash_per_share_unavailable_reason never checked
cash_and_equivalents against its own no-data gate, unlike every other balance-sheet-input field
in this file (current_assets/current_liabilities/total_assets/net_income/etc. all have one).

Live-confirmed FDXF (FedEx Freight Holding Company, a real, large, recently-spun-off S&P 500-
flagged filer) has real total_assets ($6.88B FY2026/$5.02B FY2025) but NULL
cash_and_equivalents across its entire filing history - a genuine "never tagged" gap. The
existing sec_valuations.reason reuse doesn't cover this case: a never-tagged cash concept
doesn't fail the rest of the sec_valuations row, so sec_valuations.reason stays empty and this
fell straight through to generic "missing_sec_data".
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _NoMatchCursor:
    """Every _get_no_recent_cash_symbols()/_get_never_tagged_cash_symbols() query (and every
    other gate query this loader may run) returns empty - no symbol matches."""

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _CashNeverTaggedCursor:
    """Serves a real match only to the two cash-specific gate queries (matched by their
    distinctive SELECT column), empty for everything else."""

    def __init__(self, symbol):
        self._symbol = symbol
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "cash_and_equivalents" in self._last_query:
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


class TestTotalCashNoRecentCashReported:
    def _loader(self, monkeypatch, cursor):
        import loaders.load_value_quality_growth_metrics as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(cursor))
        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_fdxf_style_never_tagged_cash_reports_specific_reason(self, monkeypatch):
        # sec_valuations row exists and resolves fine (no sec_valuations_reason) - only cash
        # itself is the genuine, never-tagged gap.
        loader = self._loader(monkeypatch, _CashNeverTaggedCursor("FDXF"))
        ev_metrics = (300_000_000.0, None, 0.0, None)

        metrics = loader._compute_quality_metrics("FDXF", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_cash"] is None
        assert metrics["total_cash_unavailable_reason"] == "no_recent_cash_reported"
        assert metrics["cash_per_share"] is None
        assert metrics["cash_per_share_unavailable_reason"] == "no_recent_cash_reported"

    def test_sec_valuations_reason_still_wins_when_present(self, monkeypatch):
        # A real, specific sec_valuations.reason must keep priority over the new cash gate.
        loader = self._loader(monkeypatch, _CashNeverTaggedCursor("FDXF"))
        ev_metrics = (None, None, None, "income_statement_revenue_and_eps_null")

        metrics = loader._compute_quality_metrics("FDXF", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_cash_unavailable_reason"] == "income_statement_revenue_and_eps_null"

    def test_no_match_falls_back_to_generic_reason(self, monkeypatch):
        loader = self._loader(monkeypatch, _NoMatchCursor())
        ev_metrics = (300_000_000.0, None, 0.0, None)

        metrics = loader._compute_quality_metrics("AMBIGCO", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_cash_unavailable_reason"] == "missing_sec_data"
        assert metrics["cash_per_share_unavailable_reason"] == "missing_sec_data"
