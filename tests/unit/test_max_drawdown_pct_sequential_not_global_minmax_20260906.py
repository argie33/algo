"""Regression test: algo_portfolio_snapshots.max_drawdown_pct must be computed as a
sequential running-peak drawdown, not a global MAX/MIN over unordered history.

Bug (found 2026-09-06, real-money-readiness audit):
_broker_snapshot_drawdown_metrics used `SELECT MAX(total_portfolio_value) as peak,
MIN(total_portfolio_value) as trough FROM algo_portfolio_snapshots` with no time-
ordering at all. A real max drawdown requires the trough to occur AFTER the peak (an
actual decline FROM that peak) - taking the global all-time max and global all-time min
independently of when they occurred means an account whose all-time minimum happened
BEFORE its all-time maximum (e.g. a small starting balance that has only grown since)
reports a large PHANTOM drawdown that never happened. This value is persisted to
algo_portfolio_snapshots.max_drawdown_pct and consumed by dashboard/panels/portfolio.py
as a real risk metric.

Fixed: a window-function query that computes, in chronological (snapshot_date) order,
the running peak up to each row, then takes the max of (running_peak - value) /
running_peak across all rows - the correct sequential definition, matching the
already-verified-correct algorithm in utils/metrics_calculator.py's
calculate_max_drawdown.

Source inspection rather than a full mocked DB call: matches this repo's existing
precedent (e.g. test_phase6_raise_stop_syncs_broker_before_write_20260824.py) for this
exact file/class of SQL-correctness change.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "infrastructure" / "reconciliation_broker_snapshot.py").read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(re.split(r"(?<!['\"])#", line, maxsplit=1)[0] for line in text.splitlines())


def _drawdown_method() -> str:
    start = SOURCE.index("def _broker_snapshot_drawdown_metrics")
    end = SOURCE.index("def ", start + 10)
    return _strip_comments(SOURCE[start:end])


class TestMaxDrawdownIsSequentialNotGlobalMinMax:
    def test_does_not_use_unordered_global_min_max(self):
        method = _drawdown_method()
        assert "MIN(total_portfolio_value)" not in method, (
            "max drawdown must not be derived from a global MIN(total_portfolio_value) - "
            "that value can occur BEFORE the global max, producing a phantom drawdown that "
            "never actually happened."
        )

    def test_uses_a_running_peak_window_function_ordered_by_snapshot_date(self):
        method = _drawdown_method()
        assert "OVER (" in method
        assert "ORDER BY snapshot_date" in method
        assert "running_peak" in method

    def test_drawdown_formula_is_relative_to_running_peak(self):
        method = _drawdown_method()
        assert "(running_peak - total_portfolio_value) / running_peak" in method

    def test_both_drawdown_queries_bound_by_reconcile_date(self):
        """Guards against the sibling stray-future-dated-snapshot bug class
        (test_no_unbounded_portfolio_snapshot_queries.py) - a leftover future-dated
        simulation row must not inflate the peak used here either."""
        method = _drawdown_method()
        assert method.count("snapshot_date <= %s") >= 2
