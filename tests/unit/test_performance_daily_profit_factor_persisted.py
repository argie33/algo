"""Regression test: algo_performance_daily.profit_factor was never written.

BUG FOUND 2026-08-24 (real-money-readiness goal, log-driven sweep): generate_daily_report()'s
INSERT INTO algo_performance_daily never included the profit_factor column at all, despite
daily_report.py already reading and displaying it (with a graceful "N/A" fallback for exactly
this always-NULL case) and reconciliation_analytics.py already implementing the equivalent
dollar-based calculation elsewhere for a different table. Live-confirmed: profit_factor was
NULL on every existing row, even ones with plenty of win/loss data to compute it from.

Fix: compute a percentage-based profit factor (gross win% / gross loss%, using the same
avg_win_pct/avg_loss_pct/win_count/loss_count already returned by win_rate()) and persist it -
matching reconciliation_analytics.py's own documented convention of leaving it None (not a
fabricated 0.0) when there are no losing trades yet to divide by.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.reporting.performance import LivePerformance


def _mock_db_context():
    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


def _run_report(win_count, loss_count, avg_win_pct, avg_loss_pct):
    perf = LivePerformance.__new__(LivePerformance)
    mock_ctx, mock_cur = _mock_db_context()

    wr = {
        "win_rate_pct": 53.19,
        "avg_win_r": 1.9,
        "avg_loss_r": -1.0,
        "win_count": win_count,
        "loss_count": loss_count,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
    }

    with (
        patch.object(perf, "rolling_sharpe", return_value=1.5),
        patch.object(perf, "rolling_sortino", return_value=1.8),
        patch.object(perf, "calmar_ratio", return_value=2.0),
        patch.object(perf, "win_rate", return_value=wr),
        patch.object(perf, "expectancy", return_value=0.3),
        patch.object(perf, "max_drawdown", return_value=-5.0),
        patch.object(perf, "total_pnl", return_value=276.52),
        patch.object(perf, "backtest_vs_live_comparison", return_value=None),
        patch("algo.reporting.performance.DatabaseContext", return_value=mock_ctx),
    ):
        perf.generate_daily_report(report_date=date(2026, 8, 24))

    return mock_cur


class TestProfitFactorPersisted:
    def test_profit_factor_computed_and_included_in_insert(self):
        # 25 wins @ avg +5.21%, 22 losses @ avg -2.73% (real values from a live row).
        mock_cur = _run_report(win_count=25, loss_count=22, avg_win_pct=5.21, avg_loss_pct=-2.73)

        assert mock_cur.execute.called
        sql, params = mock_cur.execute.call_args[0]
        assert "profit_factor" in sql

        expected = round((25 * 5.21) / abs(22 * -2.73), 3)
        assert params[-1] == expected, f"expected profit_factor={expected}, got {params[-1]}"

    def test_profit_factor_none_when_no_losing_trades(self):
        # No losses to divide by - must stay None (undefined), not a fabricated 0.0.
        mock_cur = _run_report(win_count=10, loss_count=0, avg_win_pct=3.0, avg_loss_pct=0.0)

        sql, params = mock_cur.execute.call_args[0]
        assert "profit_factor" in sql
        assert params[-1] is None
