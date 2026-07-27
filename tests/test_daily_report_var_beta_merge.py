#!/usr/bin/env python3
"""Regression test for a live bug in DailyFinanceReport._fetch_risk (algo/reporting/daily_report.py):

The method only ever queried algo_performance_daily (sharpe/sortino/drawdown/calmar) and never
queried algo_risk_daily, the table VaR/beta are actually written to by
ValueAtRisk.generate_daily_risk_report() in Phase 9 (algo/risk/var.py). As a result
risk.get("var_95_pct") and risk.get("beta") were always None regardless of how fresh the real
data in algo_risk_daily was - the daily report always printed "VaR N/A | Beta N/A", and
_check_thresholds() permanently logged "VaR 95% not yet available - check
algo_performance_metrics pipeline" (pointing at a dead table with no writer since 2026-06-30),
so the VaR > 2% risk alert could never fire. This test locks in that _fetch_risk now merges
both tables.
"""

from datetime import date

from algo.reporting.daily_report import DailyFinanceReport


class _FakeCursor:
    def __init__(self, perf_row, risk_row):
        self._perf_row = perf_row
        self._risk_row = risk_row
        self._last_query = None

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "algo_performance_daily" in self._last_query:
            return self._perf_row
        if "algo_risk_daily" in self._last_query:
            return self._risk_row
        raise AssertionError(f"Unexpected query: {self._last_query}")


def _report() -> DailyFinanceReport:
    return object.__new__(DailyFinanceReport)


class TestFetchRiskMergesVarAndBeta:
    def test_merges_var_and_beta_from_algo_risk_daily(self):
        cur = _FakeCursor(
            perf_row=(1.5, 1.8, -12.3, 1.1),
            risk_row=(1.85, 1.234),
        )
        result = DailyFinanceReport._fetch_risk(_report(), cur, date(2026, 7, 27))

        assert result["sharpe_ytd"] == 1.5
        assert result["var_95_pct"] == 1.85
        assert result["beta"] == 1.234

    def test_var_and_beta_present_even_when_performance_row_missing(self):
        cur = _FakeCursor(perf_row=None, risk_row=(1.85, 1.234))
        result = DailyFinanceReport._fetch_risk(_report(), cur, date(2026, 7, 27))

        assert result.get("data_unavailable") is not True
        assert result["var_95_pct"] == 1.85
        assert result["beta"] == 1.234
        assert result.get("sharpe_ytd") is None

    def test_data_unavailable_when_both_tables_empty(self):
        cur = _FakeCursor(perf_row=None, risk_row=None)
        result = DailyFinanceReport._fetch_risk(_report(), cur, date(2026, 7, 27))

        assert result["data_unavailable"] is True
        assert result["reason"] == "no_performance_metrics_available"
