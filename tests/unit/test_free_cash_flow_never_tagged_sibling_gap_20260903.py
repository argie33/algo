"""Regression test: free_cash_flow is missing a _get_never_tagged_X_symbols() full-history
sibling to its _get_no_recent_free_cash_flow_symbols() gate.

Bug (confirmed live 2026-09-03): every other "no_recent_X" gate in this file
(interest_expense/debt_components/revenue/total_assets/current_assets/current_liabilities/
net_income/total_liabilities/stockholders_equity/pretax_income) has a broader, full-history
"_get_never_tagged_X_symbols()" sibling that additionally catches recent IPOs/SPAC-mergers with
fewer than 3 consecutive real fiscal years - a filer too new for the 3-year window but which
still genuinely never tags the concept. free_cash_flow lacked this sibling entirely, so those
symbols' fcf_yield/fcf_margin/fcf_to_net_income/free_cash_flow reasons fell through to the
generic "missing_sec_data" instead of the specific "no_recent_free_cash_flow_reported". Adding
_get_never_tagged_free_cash_flow_symbols() and OR-ing it into all four call sites recovers 48
live-confirmed universe symbols.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def test_never_tagged_free_cash_flow_symbols_method_exists() -> None:
    assert hasattr(ValueQualityGrowthMetricsLoader, "_get_never_tagged_free_cash_flow_symbols")


def test_never_tagged_free_cash_flow_symbols_queries_annual_cash_flow(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class _FakeCursor:
        def execute(self, sql: str, params: object = None) -> None:
            captured["sql"] = sql

        def fetchall(self) -> list[tuple[str]]:
            return [("NEWIPO",)]

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
    result = loader._get_never_tagged_free_cash_flow_symbols()

    assert result == frozenset({"NEWIPO"})
    assert "annual_cash_flow" in captured["sql"]
    assert "free_cash_flow" in captured["sql"]
    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): `fiscal_year > 0`
    # replaces `data_unavailable = FALSE` so a symbol whose entire fiscal-year history is marked
    # unavailable isn't invisible to this gate - see
    # test_never_tagged_gates_all_unavailable_history_20260905.py for the full rationale.
    assert "fiscal_year > 0" in captured["sql"]
