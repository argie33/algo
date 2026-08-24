"""Regression test (real-money-readiness goal session, 2026-08-24): verify_loaders_health.py's
row-count check used a lifetime COUNT(*) floor (min_rows=10000) for buy_sell_daily, which is
sparse/event-driven (a symbol only gets a row on a day it actually triggers a BUY/SELL
breakout/breakdown, ~118-302 rows/day observed) - it grows slowly and organically regardless
of whether the loader is healthy right now, so this check DEGRADED-flagged the loader for
weeks purely from the table not having existed/been reset long enough, with zero connection to
real health (live-confirmed: 9118 lifetime rows, self-resolving in ~4-5 more trading days
purely from time passing - see verify_loaders_health_buy_sell_daily_min_rows_self_resolving
memory). Fixed via an opt-in min_rows_recency_days/min_rows_recency_threshold pair that
switches the check to "rows written in the last N days" - a real signal about current health -
instead of the lifetime bucket. Every other loader is unaffected (both keys default to None,
falling back to the original lifetime-count query unchanged).
"""

from datetime import date
from unittest.mock import MagicMock

from scripts.verify_loaders_health import LOADERS, verify_loader


class TestBuySellDailyRecencyWindowConfig:
    def test_recency_window_keys_present(self):
        config = LOADERS["load_buy_sell_daily.py"]
        assert config.get("min_rows_recency_days") == 5
        assert config.get("min_rows_recency_threshold") == 50

    def test_other_loaders_unaffected_by_default(self):
        """Sanity check: a loader with no min_rows_recency_days must keep using the
        original lifetime-count query shape."""
        config = LOADERS["load_prices.py"]
        assert config.get("min_rows_recency_days") is None


class TestVerifyLoaderUsesRecencyWindowWhenConfigured:
    def _config(self):
        return {
            "output_table": "buy_sell_daily",
            "date_column": "date",
            "min_rows": 10000,
            "min_rows_recency_days": 5,
            "min_rows_recency_threshold": 50,
            "critical": True,
        }

    def test_healthy_recent_count_issues_no_low_row_count_issue(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (True,),  # table exists
            (150,),  # recency-window row count - healthy
            (date.today(),),  # MAX(date) - fresh
        ]
        cur.fetchall.return_value = []  # no columns to NULL-check, keep this test focused
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_loader(conn, "load_buy_sell_daily.py", self._config())

        assert not any("row count" in issue.lower() for issue in result["issues"])
        recency_queries = [
            c.args[0] for c in cur.execute.call_args_list if "COUNT(*)" in c.args[0] and "buy_sell_daily" in c.args[0]
        ]
        assert any("INTERVAL '5 days'" in q for q in recency_queries), (
            f"expected a recency-windowed COUNT(*) query, got: {recency_queries}"
        )
        assert not any(q.strip() == "SELECT COUNT(*) FROM buy_sell_daily" for q in recency_queries), (
            "must not also issue the old unscoped lifetime COUNT(*) query"
        )

    def test_genuinely_broken_loader_still_flagged(self):
        """A loader producing near-zero output for 5 straight sessions must still be
        caught - this isn't just weakening the check to silence noise."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (True,),  # table exists
            (2,),  # recency-window row count - genuinely broken
            (date.today(),),  # MAX(date) - fresh (loader ran, just produced almost nothing)
        ]
        cur.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_loader(conn, "load_buy_sell_daily.py", self._config())

        assert any("low recent row count" in issue.lower() for issue in result["issues"]), result["issues"]
