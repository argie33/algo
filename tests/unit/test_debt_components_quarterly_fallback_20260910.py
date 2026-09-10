"""Regression test (2026-09-10, "under 500" SEC/XBRL missing-data push,
total_debt_not_itemized bucket): _fetch_total_debt_components_fallback
(loaders/helpers/vqg_quality_debt_fallback.py) only ever searched annual_balance_sheet - a
filer with real debt tagged ONLY in its quarterly 10-Q filings (never in any
annual_balance_sheet row) fell all the way through to "missing_sec_data"/
"total_debt_not_itemized" even though real, recent debt data exists. Live-confirmed 3
universe symbols with zero debt-component data anywhere in annual_balance_sheet but a real
recent quarterly figure: KWM ($1.8M long_term_debt, FY2025 Q4), NUR ($5.8M, FY2026 Q1), VOXR
($6.7M, FY2025 Q4).
"""

from loaders.helpers.vqg_quality_debt_fallback import DebtComponentsFallbackMixin


class _FakeCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        return self._fetchone_result


class _FakeDatabaseContext:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result
        self.cursor = None

    def __enter__(self):
        self.cursor = _FakeCursor(self._fetchone_result)
        return self.cursor

    def __exit__(self, *exc):
        return False


class _FakeLoader(DebtComponentsFallbackMixin):
    """Real DebtComponentsFallbackMixin, stubbed _nan_to_none/_fetch_annual_fallback_row -
    same minimal-loader pattern as the annual-tier test in
    test_debt_to_equity_zero_equity_and_debt_components_fallback_20260910.py, but this test
    targets the quarterly tier directly so the annual helper is forced to return nothing.
    """

    def __init__(self, annual_result=None):
        self._annual_result = annual_result

    @staticmethod
    def _nan_to_none(value):
        return value

    def _fetch_annual_fallback_row(self, table, columns, extra_where, symbol):
        assert table == "annual_balance_sheet"
        return self._annual_result


def _patch_db(monkeypatch, fetchone_result):
    # The quarterly tier resolves DatabaseContext via a local
    # `import loaders.load_value_quality_growth_metrics as _vqg_mod` (see that method's own
    # docstring for why) - patch it there, the SAME seam every other test in this file's
    # sibling test files already patches for the annual tiers.
    import loaders.load_value_quality_growth_metrics as mod

    fake_db = _FakeDatabaseContext(fetchone_result)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: fake_db)
    return fake_db


class TestDebtComponentsQuarterlyFallback:
    def test_quarterly_fallback_sums_components_when_annual_is_empty(self, monkeypatch):
        # long_term_debt real, other 3 components untagged - same shape as live KWM.
        fake_db = _patch_db(monkeypatch, fetchone_result=(1_808_311.18, None, None, None))
        loader = _FakeLoader(annual_result=None)

        result = loader._fetch_total_debt_components_fallback("KWM")

        assert result == 1_808_311.18
        assert "quarterly_balance_sheet" in fake_db.cursor.last_query
        assert "fiscal_quarter DESC" in fake_db.cursor.last_query

    def test_quarterly_fallback_reached_when_annual_row_is_all_null(self, monkeypatch):
        # Annual row exists but every debt component in it is NULL (shouldn't normally
        # happen given the fallback's own NOT NULL where-clause, but the code defends
        # against it) - must still fall through to the quarterly tier, not return 0.
        _patch_db(monkeypatch, fetchone_result=(None, 5_834_318.62, None, None))
        loader = _FakeLoader(annual_result=(None, None, None, None))

        result = loader._fetch_total_debt_components_fallback("NUR")

        assert result == 5_834_318.62

    def test_returns_none_when_quarterly_also_empty(self, monkeypatch):
        _patch_db(monkeypatch, fetchone_result=None)
        loader = _FakeLoader(annual_result=None)

        result = loader._fetch_total_debt_components_fallback("NODEBTANYWHERE")

        assert result is None

    def test_annual_tier_wins_and_quarterly_database_context_never_touched(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        def _fail_if_called(*a, **kw):
            raise AssertionError("quarterly fallback's DatabaseContext should not be reached")

        monkeypatch.setattr(mod, "DatabaseContext", _fail_if_called)
        loader = _FakeLoader(annual_result=(100_000_000.0, None, None, None))

        result = loader._fetch_total_debt_components_fallback("HASANNUALDATA")

        assert result == 100_000_000.0
