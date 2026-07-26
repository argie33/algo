"""Regression test: stock_scores/algo_trades/algo_positions must get the same
weekend/holiday gap-shifted staleness thresholds as the other once-per-trading-day
tables, not the raw (non-shifted) thresholds.

Bug: these three tables were omitted from the gap-adjustment whitelist in
check_all_tables(), so every weekend/holiday the monitor reported them
CRITICAL/STALE purely from the Friday->Monday calendar gap - even though nothing
was actually wrong - and told operators to "FIX IMMEDIATELY". Confirmed live
2026-07-26 (a Sunday): all three flagged STALE/CRITICAL with real, correctly-
loaded Friday data.
"""

from datetime import date
from unittest.mock import patch

from scripts import monitor_data_staleness as mds


class TestWeekendGapCoversAllOnceDailyTables:
    def test_stock_scores_algo_trades_positions_fresh_across_weekend_gap(self):
        """Simulate a Sunday check: last write was Friday (~2.2 days ago for
        algo_trades, ~15h for stock_scores, ~21h for algo_positions - the exact
        real-world ages observed live). None of these should read as stale/
        critical once the weekend gap is accounted for.
        """
        ages_by_table = {
            "stock_scores": 15.3 * 60,
            "algo_trades": 2.2 * 1440,
            "algo_positions": 21.3 * 60,
        }

        def fake_age(table_name):
            return ages_by_table.get(table_name)

        # A Sunday; Friday (2 days back) is the last trading day, so spans_gap=True
        # and gap_minutes = 2 * 1440.
        sunday = date(2026, 7, 26)
        assert sunday.weekday() == 6

        with (
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "get_table_age_minutes", side_effect=fake_age),
        ):
            mock_date.today.return_value = sunday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            results = mds.check_all_tables()

        for table in ("stock_scores", "algo_trades", "algo_positions"):
            assert results[table]["level"] == "ok", (
                f"{table} should be 'ok' across a weekend gap, got {results[table]}"
            )

    def test_stock_scores_still_flags_critical_on_a_real_gap(self):
        """Sanity check the fix doesn't just always return 'ok': a genuinely
        stale stock_scores (e.g. 3 days old with no weekend gap involved,
        Tuesday check with Monday as the last trading day) must still alert.
        """
        def fake_age(table_name):
            return 600 if table_name == "stock_scores" else 60  # 10h: past stale(8h), short of critical(24h)

        tuesday = date(2026, 7, 28)
        assert tuesday.weekday() == 1

        with (
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "get_table_age_minutes", side_effect=fake_age),
        ):
            mock_date.today.return_value = tuesday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            results = mds.check_all_tables()

        assert results["stock_scores"]["level"] == "critical"
