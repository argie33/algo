"""Regression test: operating_margin/interest_coverage must distinguish
"operating_income_not_itemized" (a real filer that never itemizes a distinct operating income
subtotal) from the generic "missing_sec_data" fallback.

Bug (confirmed live 2026-09-03): neither operating_margin_unavailable_reason nor
interest_coverage_unavailable_reason had any gate for this case - every existing check upstream
of the generic fallback (implausible_ratio, reit_special_entity, operating_income_absent_from_
anchor_year, no_revenue_reported) is scoped to a different root cause. Live-confirmed 43
active-universe symbols were mislabeled "missing_sec_data" for this reason.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def test_no_recent_and_never_tagged_operating_income_methods_exist() -> None:
    assert hasattr(ValueQualityGrowthMetricsLoader, "_get_no_recent_operating_income_symbols")
    assert hasattr(ValueQualityGrowthMetricsLoader, "_get_never_tagged_operating_income_symbols")


def test_never_tagged_operating_income_queries_annual_income_statement(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class _FakeCursor:
        def execute(self, sql: str, params: object = None) -> None:
            captured["sql"] = sql

        def fetchall(self) -> list[tuple[str]]:
            return [("SIMPLEFILER",)]

    class _FakeDatabaseContext:
        def __call__(self, role: str) -> "_FakeDatabaseContext":
            return self

        def __enter__(self) -> _FakeCursor:
            return _FakeCursor()

        def __exit__(self, *exc: object) -> None:
            return None

    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())

    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    result = loader._get_never_tagged_operating_income_symbols()

    assert result == frozenset({"SIMPLEFILER"})
    assert "annual_income_statement" in captured["sql"]
    assert "operating_income" in captured["sql"]
