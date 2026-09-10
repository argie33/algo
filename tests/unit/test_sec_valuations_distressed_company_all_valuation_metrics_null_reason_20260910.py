"""Regression test (2026-09-10, goal: "under 300" push, all_valuation_metrics_null
investigation): load_sec_valuations.py's "all_valuation_metrics_null" whole-row fallback was
only ever recategorized for the blank-check-SPAC case, not for a real, non-shell operating
company whose PE/PB/PS/FCF-yield are all legitimately undefined because it's genuinely
distressed (net_income and stockholders_equity both negative).

Live-confirmed AQB (AquaBounty Technologies, SIC "Fishing, Hunting and Trapping", 10 real
annual filings), BCAB (BioAtla, real clinical-stage biotech, 7 annual filings), and TREO
(real filer, 7 annual filings) all hit "all_valuation_metrics_null" with net_income deeply
negative and stockholders_equity negative - a real business fact (burning cash into negative
book value), not a SEC/XBRL data gap, same "Legitimate / not applicable" class as the
blank-check case just recategorizes differently.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, row) -> None:
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _FakeDatabaseContext:
    def __init__(self, row) -> None:
        self._row = row

    def __enter__(self):
        return _FakeCursor(self._row)

    def __exit__(self, *exc):
        return False


class TestSecValuationsDistressedCompanyAllValuationMetricsNullReason:
    def test_negative_net_income_and_equity_reports_negative_book_value(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(
            mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext((-18_490_487.0, -2_126_431.0))
        )
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_distressed_company_all_valuation_metrics_null_reason("AQB", result)

        assert result["reason"] == "negative_book_value"

    def test_positive_net_income_keeps_generic_reason(self, monkeypatch):
        # Currency-blocked filers (BBAR/LOMA/TBBB-style) report POSITIVE net_income in their
        # own local currency - must never be swept into "distressed" just because market_cap
        # came out null for an unrelated (currency) reason.
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext((364_815_580_000.0, None)))
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_distressed_company_all_valuation_metrics_null_reason("BBAR", result)

        assert result["reason"] == "all_valuation_metrics_null"

    def test_negative_net_income_but_positive_equity_keeps_generic_reason(self, monkeypatch):
        # Only one of the two signals is negative - not enough to safely recategorize
        # (double-confirmation discipline, same as the rest of this file's structural checks).
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext((-15_842_407.0, 5_117_527.0)))
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_distressed_company_all_valuation_metrics_null_reason("GV", result)

        assert result["reason"] == "all_valuation_metrics_null"

    def test_no_row_keeps_generic_reason(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(None))
        loader = _make_loader()
        result: dict = {"reason": "all_valuation_metrics_null"}

        loader._recategorize_distressed_company_all_valuation_metrics_null_reason("NODATA", result)

        assert result["reason"] == "all_valuation_metrics_null"

    def test_does_not_touch_a_different_already_specific_reason(self, monkeypatch):
        import loaders.load_sec_valuations as mod

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext((-1.0, -1.0)))
        loader = _make_loader()
        result: dict = {"reason": "shares_outstanding_scale_mismatch"}

        loader._recategorize_distressed_company_all_valuation_metrics_null_reason("SOMESYM", result)

        assert result["reason"] == "shares_outstanding_scale_mismatch"
