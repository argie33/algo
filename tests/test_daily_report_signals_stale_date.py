#!/usr/bin/env python3
"""Regression test for a live bug in DailyFinanceReport._fetch_signals (algo/reporting/daily_report.py):

buy_sell_daily for trading day D is only published after D's EOD close (same lag Phase 7
accounts for via latest_buysell_date in phase7_signal_generation.py). _fetch_signals queried
buy_sell_daily WHERE date = report_date literally, which showed 0 candidates for the entire
trading day, every day, until that evening's loader run landed - even when Phase 7 had
correctly found and qualified real candidates from the latest available prior date (e.g.
Friday's data on a Monday run). Live-reproduced 2026-08-10: a Monday morning run had 0 rows
in buy_sell_daily dated that Monday but 571 BUY rows dated the prior Friday, and Phase 7
correctly qualified 19 signals from that Friday data - yet the report printed
"Today: 0 BUY signals -> 19 tier-passed -> 0 entries", looking like a broken pipeline. This
test locks in that _fetch_signals resolves to the latest buy_sell_daily date at or before
report_date, same as Phase 7 does.
"""

import json
from datetime import date

from algo.reporting.daily_report import DailyFinanceReport


class _FakeCursor:
    def __init__(self, max_date_row, buy_count_row, tier_row, entries_row):
        self._max_date_row = max_date_row
        self._buy_count_row = buy_count_row
        self._tier_row = tier_row
        self._entries_row = entries_row
        self._last_query = None

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        q = self._last_query
        if "MAX(date)" in q:
            return self._max_date_row
        if "buy_sell_daily" in q:
            return self._buy_count_row
        if "algo_signals" in q:
            return self._tier_row
        if "algo_trades" in q:
            return self._entries_row
        raise AssertionError(f"Unexpected query: {q}")


def _report() -> DailyFinanceReport:
    return object.__new__(DailyFinanceReport)


class TestFetchSignalsUsesLatestAvailableDate:
    def test_falls_back_to_latest_prior_date_when_report_date_has_no_rows(self):
        report_date = date(2026, 8, 10)  # Monday
        friday = date(2026, 8, 7)
        cur = _FakeCursor(
            max_date_row=(friday,),
            buy_count_row=(571,),
            tier_row=(19,),
            entries_row=(0,),
        )
        result = DailyFinanceReport._fetch_signals(_report(), cur, report_date)

        assert result["candidates_today"] == 571
        assert result["candidates_date"] == str(friday)
        assert result["passed_tiers"] == 19
        assert result["entries_today"] == 0

    def test_uses_report_date_directly_when_it_has_rows(self):
        report_date = date(2026, 8, 6)
        cur = _FakeCursor(
            max_date_row=(report_date,),
            buy_count_row=(600,),
            tier_row=(25,),
            entries_row=(3,),
        )
        result = DailyFinanceReport._fetch_signals(_report(), cur, report_date)

        assert result["candidates_today"] == 600
        assert result["candidates_date"] == str(report_date)

    def test_zero_candidates_when_table_entirely_empty(self):
        report_date = date(2026, 8, 10)
        cur = _FakeCursor(
            max_date_row=(None,),
            buy_count_row=(0,),
            tier_row=(0,),
            entries_row=(0,),
        )
        result = DailyFinanceReport._fetch_signals(_report(), cur, report_date)

        assert result["candidates_today"] == 0
        assert result["candidates_date"] == str(report_date)

    def test_result_is_json_serializable(self):
        """Live-reproduced 2026-08-10: phase9_reconciliation.py's _generate_daily_report()
        does json.dumps(report) on the whole report dict (signals sub-dict included) for
        the execution log. A raw date object in candidates_date raised
        'TypeError: Object of type date is not JSON serializable', halting the orchestrator
        (triggered_by=phase9_reconciliation_governance) on the very next live run after
        this field was added.
        """
        report_date = date(2026, 8, 10)
        friday = date(2026, 8, 7)
        cur = _FakeCursor(
            max_date_row=(friday,),
            buy_count_row=(571,),
            tier_row=(19,),
            entries_row=(0,),
        )
        result = DailyFinanceReport._fetch_signals(_report(), cur, report_date)

        json.dumps(result)  # must not raise
