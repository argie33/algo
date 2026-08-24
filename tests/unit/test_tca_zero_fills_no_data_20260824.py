"""Regression test for a live-findable bug in TCAEngine.daily_report()/monthly_summary()
(algo/trading/tca.py): both ran a bare `COUNT(*) ... FROM algo_tca WHERE ...` with no GROUP BY,
which always returns exactly one row even when zero fills match (fill_count=0, every other
aggregate - AVG/MIN/MAX/SUM over zero rows - NULL). Both functions guarded their intended
"no data" early-return on `row is None or len(row) < 1`, which can never be true for that kind
of query - so a completely normal day/month with zero trade fills instead fell through to the
NULL-field checks below and raised a misleading "[TCA CRITICAL] ... Cannot compute TCA metrics
without valid execution data" (daily_report) or a TypeError from `Decimal(None)` wrapped into
"monthly summary generation failed" (monthly_summary), instead of the graceful
{"status": "no_data"} result both were clearly written to produce.

Fixed by checking `fill_count == 0` directly instead of the unreachable row-shape check.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.trading.tca import TCAEngine


class _FakeCursor:
    """COUNT(*) aggregate with no GROUP BY: exactly one row every time, all non-count
    aggregates NULL when zero rows matched - the real Postgres behavior this bug missed."""

    def __init__(self, rows):
        self._rows = list(rows)

    def execute(self, query, *args, **kwargs):
        pass

    def fetchone(self):
        return self._rows.pop(0)


def _make_engine():
    return TCAEngine(config={})


def test_daily_report_zero_fills_returns_no_data_not_critical_error():
    zero_fill_row = (0, None, None, None, None, None)
    fake_cursor = _FakeCursor([zero_fill_row])
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    engine = _make_engine()
    with patch("algo.trading.tca.DatabaseContext", return_value=fake_ctx):
        result = engine.daily_report(report_date=date(2026, 8, 24))

    assert result == {"report_date": date(2026, 8, 24), "fill_count": 0, "status": "no_data"}


def test_monthly_summary_zero_fills_returns_no_data_not_type_error():
    zero_fill_row = (0, None, None, None, None, None)
    fake_cursor = _FakeCursor([zero_fill_row])
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    engine = _make_engine()
    with patch("algo.trading.tca.DatabaseContext", return_value=fake_ctx):
        result = engine.monthly_summary(2026, 8)

    assert result == {"period": "2026-08", "fill_count": 0, "status": "no_data"}


def test_daily_report_with_fills_still_computes_normally():
    row = (3, 12.5, -5.0, 40.0, 98.0, 250.0)
    high_slippage_row = (1,)
    worst_symbol_row = ("AAPL", 40.0)
    fake_cursor = _FakeCursor([row, high_slippage_row, worst_symbol_row])
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    engine = _make_engine()
    with patch("algo.trading.tca.DatabaseContext", return_value=fake_ctx):
        result = engine.daily_report(report_date=date(2026, 8, 24))

    assert result["fill_count"] == 3
    assert result["status"] == "warning"
    assert result["worst_symbol"] == "AAPL"
