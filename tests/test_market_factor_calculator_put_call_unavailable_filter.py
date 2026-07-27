#!/usr/bin/env python3
"""Regression test for a live data-integrity bug in MarketFactorCalculator.put_call_ratio()
(algo/risk/market_factor_calculator.py):

The query selected the most recent row with put_call_ratio IS NOT NULL, without excluding
rows flagged put_call_ratio_data_unavailable=True. 8 historical rows (2026-07-02 to
2026-07-14) had a non-NULL put_call_ratio (a stale 2.0531 repeated across every one of them)
left over from a failed fetch, even though data_unavailable=True correctly flagged them as
bad (confirmed live in the dev DB and cleaned up in the same fix). Any eval_date landing on
or after one of those dates with no later real reading (e.g. a backtest evaluating
2026-07-14) would silently score real position-sizing input off that fabricated value
instead of raising the documented fail-fast error. This test locks in that the query now
excludes data_unavailable rows even when the ratio column itself is non-NULL.
"""

from datetime import date

import pytest

from algo.risk.market_factor_calculator import MarketFactorCalculator


class _FakeCursor:
    """Mimics psycopg2: the real SQL text decides which rows are visible."""

    def __init__(self, table):
        self._table = table
        self._pending: list = []

    def execute(self, query, params=None):
        if "put_call_ratio_data_unavailable IS NOT TRUE" in query:
            eval_date = params[0]
            rows = [
                r
                for r in self._table
                if r["date"] <= eval_date and r["put_call_ratio"] is not None and not r["unavailable"]
            ]
            rows.sort(key=lambda r: r["date"], reverse=True)
            self._pending = [{"put_call_ratio": rows[0]["put_call_ratio"]}] if rows else []
        elif "COUNT(*)" in query and "date <=" not in query:
            self._pending = [(sum(1 for r in self._table if r["put_call_ratio"] is not None),)]
        elif "COUNT(*)" in query:
            eval_date = params[0]
            self._pending = [(sum(1 for r in self._table if r["date"] <= eval_date),)]
        else:
            raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        return self._pending[0] if self._pending else None


def _corrupted_table():
    return [
        {"date": date(2026, 7, 10), "put_call_ratio": 2.0531, "unavailable": True},
        {"date": date(2026, 7, 14), "put_call_ratio": 2.0531, "unavailable": True},
        {"date": date(2026, 7, 16), "put_call_ratio": 0.95, "unavailable": False},
    ]


class TestPutCallRatioExcludesUnavailableRows:
    def test_raises_instead_of_using_fabricated_value_from_flagged_row(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor(_corrupted_table())

        with pytest.raises(RuntimeError, match="No put/call ratio data available"):
            calc.put_call_ratio(date(2026, 7, 14), cur)

    def test_uses_real_value_when_a_valid_row_exists(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor(_corrupted_table())

        result = calc.put_call_ratio(date(2026, 7, 16), cur)

        assert result["value"] == 0.95
