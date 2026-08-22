#!/usr/bin/env python3
"""Regression test for a live data-integrity bug in MarketFactorCalculator.put_call_ratio()
(algo/risk/market_factor_calculator.py):

The query selected the most recent row with put_call_ratio IS NOT NULL, without excluding
rows flagged put_call_ratio_data_unavailable=True. 8 historical rows (2026-07-02 to
2026-07-14) had a non-NULL put_call_ratio (a stale 2.0531 repeated across every one of them)
left over from a failed fetch, even though data_unavailable=True correctly flagged them as
bad (confirmed live in the dev DB and cleaned up in the same fix). Any eval_date landing on
or after one of those dates with no later real reading (e.g. a backtest evaluating
2026-07-14) would silently score real position-sizing input off that fabricated value.

Fixed: put_call_ratio is optional enrichment. Returns explicit data_unavailable marker
instead of raising RuntimeError. The query still excludes data_unavailable rows even when
the ratio column is non-NULL (preventing fabricated values).

UPDATED 2026-08-22 (goal: exposure-model integrity review): put_call_ratio() now z-scores
the current reading against its own real historical distribution instead of a fixed
threshold calibrated for a different metric (see put_call_ratio()'s own docstring) - two
queries now (current-value validity check, then a history fetch for z-scoring), both still
excluding data_unavailable-flagged rows the same way.
"""

from datetime import date

import pytest

from algo.risk.market_factor_calculator import MarketFactorCalculator


class _FakeCursor:
    """Mimics psycopg2: the real SQL text decides which rows are visible.

    put_call_ratio() issues two queries against the same underlying table: a single-row
    "current value" check (ORDER BY date DESC LIMIT 1), then - only if that value passes
    its own sanity check - a "history" fetch (same filters plus a BETWEEN 0.2 AND 3.0
    range guard, LIMIT 500) used for z-scoring. Both must exclude
    put_call_ratio_data_unavailable=True rows even when the ratio column itself is non-NULL.
    """

    def __init__(self, table):
        self._table = table
        self._pending_one: tuple | None = None
        self._pending_all: list = []

    def execute(self, query, params=None):
        if "put_call_ratio_data_unavailable IS NOT TRUE" not in query:
            raise AssertionError(f"Unexpected query (missing unavailable-exclusion filter): {query}")
        eval_date = params[0]
        visible = [
            r
            for r in self._table
            if r["date"] <= eval_date and r["put_call_ratio"] is not None and not r["unavailable"]
        ]
        visible.sort(key=lambda r: r["date"], reverse=True)
        if "BETWEEN 0.2 AND 3.0" in query:
            in_range = [r for r in visible if 0.2 <= r["put_call_ratio"] <= 3.0][:500]
            self._pending_all = [(r["put_call_ratio"],) for r in in_range]
        else:
            self._pending_one = (visible[0]["put_call_ratio"],) if visible else None

    def fetchone(self):
        return self._pending_one

    def fetchall(self):
        return self._pending_all


def _corrupted_table():
    """3 flagged-bad rows (stale fabricated value, dated on/before 2026-07-14) plus 20
    real, varied, valid readings dated exactly on the "current" date (2026-07-16) - enough
    real history to exercise z-scoring for that date, while leaving 2026-07-14 with only
    the corrupted rows visible (preserving the original regression's intent: that date must
    have NO valid data once the flagged-bad rows are correctly excluded).
    """
    base = date(2026, 7, 16)
    real_history = [{"date": base, "put_call_ratio": 0.8 + 0.05 * (i % 5), "unavailable": False} for i in range(1, 21)]
    return [
        {"date": date(2026, 7, 10), "put_call_ratio": 2.0531, "unavailable": True},
        {"date": date(2026, 7, 14), "put_call_ratio": 2.0531, "unavailable": True},
        {"date": base, "put_call_ratio": 0.95, "unavailable": False},
        *real_history,
    ]


class TestPutCallRatioExcludesUnavailableRows:
    def test_returns_data_unavailable_marker_instead_of_using_fabricated_value_from_flagged_row(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor(_corrupted_table())

        result = calc.put_call_ratio(date(2026, 7, 14), cur)

        # Put/call ratio is optional enrichment - returns explicit unavailable marker instead of raising
        assert result.get("data_unavailable") is True
        assert "reason" in result

    def test_uses_real_value_and_zscores_against_own_history_when_valid_rows_exist(self):
        calc = MarketFactorCalculator()
        cur = _FakeCursor(_corrupted_table())

        result = calc.put_call_ratio(date(2026, 7, 16), cur)

        assert result["value"] == 0.95
        assert not result.get("data_unavailable")
        assert "score" in result
        assert "z" in result

    def test_flagged_rows_excluded_from_zscore_history_too(self):
        # The two data_unavailable=True rows carry a real-looking 2.0531 value that would
        # badly skew the z-score baseline if they leaked into the history query the same
        # way they used to leak into the single-value query pre-fix.
        calc = MarketFactorCalculator()
        cur = _FakeCursor(_corrupted_table())

        calc.put_call_ratio(date(2026, 7, 16), cur)

        assert all(v != (2.0531,) for v in cur._pending_all)
