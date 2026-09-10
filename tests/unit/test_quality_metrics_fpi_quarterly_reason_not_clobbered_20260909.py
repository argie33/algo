"""Regression test: the row-level "all core ratios None" early return in
_compute_quality_metrics must not clobber an already-correct, specific quarterly-derived
reason (e.g. "foreign_private_issuer_no_quarterly_filings") with the unrelated
balance-sheet-focused row_level_reason (e.g. the generic "missing_sec_data" default).

Live-confirmed 2026-09-09 (goal session: "under 500" SEC/XBRL missing-data push): AIIR,
BIOT, GIXI, IMC, PSQL, RPGL, VRXA, WATR (all is_foreign_private_issuer=True with <4 real
quarters of quarterly_income_statement history) had their quarterly_growth_momentum/
earnings_growth_4q_avg/consecutive_positive_quarters/etc. unavailable_reason overwritten
from the specific "foreign_private_issuer_no_quarterly_filings" (correctly set by
_compute_quarterly_metrics) to the generic row-level reason, because
_unavailable_marker("quality_metrics", ...) blankets every _SHARED_TREND_FIELDS reason
unconditionally - miscategorizing a real, permanent FPI exemption ("Legitimate / not
applicable" in /api/scores/coverage) as "Missing SEC/XBRL data" in both quality_metrics and
growth_metrics (via _mirror_shared_trend_fields, which copies this same clobbered reason).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _empty_quality_row(fiscal_year=2024):
    # 34-column shape (index 33 = prior_year_gross_profit) - everything None except
    # fiscal_year, so every one of the 7 core ratios comes out None and the row-level early
    # return fires.
    row = [None] * 34
    row[8] = fiscal_year
    return row


class _FakeCursor:
    def __init__(self, is_fpi):
        self._is_fpi = is_fpi
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "is_foreign_private_issuer" in self._last_query:
            return (self._is_fpi,)
        return None


class _FakeDatabaseContext:
    def __init__(self, is_fpi):
        self._is_fpi = is_fpi

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._is_fpi)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, is_fpi):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(is_fpi))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestQualityMetricsFpiQuarterlyReasonNotClobbered:
    def test_fpi_symbol_keeps_specific_quarterly_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, is_fpi=True)

        metrics = loader._compute_quality_metrics("FPICO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        # Row-level reason (no gate matched -> generic default) still applies to the
        # balance-sheet-derived ratios, which are genuinely unrelated to quarterly history.
        assert metrics["roe_unavailable_reason"] == "missing_sec_data"
        assert metrics["debt_to_equity_unavailable_reason"] == "missing_sec_data"
        # But the quarterly-derived fields keep their own specific, correct reason instead.
        assert metrics["quarterly_growth_momentum_unavailable_reason"] == "foreign_private_issuer_no_quarterly_filings"
        assert metrics["earnings_growth_4q_avg_unavailable_reason"] == "foreign_private_issuer_no_quarterly_filings"
        assert (
            metrics["consecutive_positive_quarters_unavailable_reason"] == "foreign_private_issuer_no_quarterly_filings"
        )
        assert metrics["eps_growth_stability_unavailable_reason"] == "foreign_private_issuer_no_quarterly_filings"

    def test_domestic_symbol_keeps_insufficient_quarterly_history_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, is_fpi=False)

        metrics = loader._compute_quality_metrics("DOMESTICCO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["roe_unavailable_reason"] == "missing_sec_data"
        # Domestic filer with <4 quarters gets "insufficient_quarterly_history" (a real,
        # temporary gap), not clobbered by the row-level balance-sheet reason either.
        assert metrics["quarterly_growth_momentum_unavailable_reason"] == "insufficient_quarterly_history"
        assert metrics["consecutive_positive_quarters_unavailable_reason"] == "insufficient_quarterly_history"
