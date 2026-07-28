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
from unittest.mock import MagicMock, patch

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
            patch.object(mds, "get_loader_failed", return_value=False),
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

        stock_scores is computed once per trading day (signals pipeline, 4:05 PM
        ET) - same cadence as algo_signals/growth_metrics/etc, whose thresholds
        were already relaxed to 24h/36h/48h to avoid a false CRITICAL every
        single morning before that day's run. stock_scores' own thresholds were
        never migrated to match (confirmed live 2026-07-28: a completely normal
        10.9h age read '[OK]' in check_system_health.py but 'CRITICAL' here) -
        fixed to the same 1440/2160/2880 minute bounds. A "genuinely stuck"
        scenario now means missing more than a full extra trading day's run.
        """
        def fake_age(table_name):
            return 45 * 60 if table_name == "stock_scores" else 60  # 45h: past stale(36h), short of dead(48h)

        tuesday = date(2026, 7, 28)
        assert tuesday.weekday() == 1

        with (
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "get_table_age_minutes", side_effect=fake_age),
            patch.object(mds, "get_loader_failed", return_value=False),
        ):
            mock_date.today.return_value = tuesday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            results = mds.check_all_tables()

        assert results["stock_scores"]["level"] == "critical"

    def test_buy_sell_daily_is_monitored_and_gets_weekend_gap_relaxation(self):
        """buy_sell_daily was missing from THRESHOLDS entirely - the one table
        whose staleness triggers a live "[PHASE 7 CRITICAL HALT]" in the
        orchestrator (algo/orchestrator/phase7_signal_generation.py) was invisible
        to the dedicated staleness tool. Same once-per-trading-day cadence as
        algo_signals: a ~2.2-day-old Friday row on a Sunday check must read 'ok'.
        """
        def fake_age(table_name):
            return 2.2 * 1440 if table_name == "buy_sell_daily" else 60

        sunday = date(2026, 7, 26)
        assert sunday.weekday() == 6

        with (
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "get_table_age_minutes", side_effect=fake_age),
            patch.object(mds, "get_loader_failed", return_value=False),
        ):
            mock_date.today.return_value = sunday
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            results = mds.check_all_tables()

        assert "buy_sell_daily" in results
        assert results["buy_sell_daily"]["level"] == "ok"


class TestUpsertTablesUseUpdatedAtNotCreatedAt:
    """growth_metrics/quality_metrics/value_metrics are UPSERT tables (ON CONFLICT
    DO UPDATE in load_value_quality_growth_metrics.py) whose SET clause bumps
    `updated_at` on every write but never touches `created_at` - created_at is
    INSERT-only, frozen at whenever a symbol was FIRST ever loaded. Using
    created_at here produced false CRITICAL/DEAD alarms on tables the loader was
    actually updating daily (confirmed live 2026-07-28: growth_metrics/
    quality_metrics showed 2.7d DEAD via created_at while updated_at showed
    4823/5508 rows freshly upserted the day before).
    """

    def test_growth_quality_value_metrics_query_updated_at(self):
        for table in ("growth_metrics", "quality_metrics", "value_metrics"):
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (42.0,)
            mock_db_ctx = MagicMock()
            mock_db_ctx.__enter__.return_value = mock_cursor

            with patch.object(mds, "DatabaseContext", return_value=mock_db_ctx):
                mds.get_table_age_minutes(table)

            executed_sql = mock_cursor.execute.call_args[0][0]
            assert "MAX(updated_at)" in executed_sql, (
                f"{table}: staleness query must use updated_at (bumped on every "
                f"UPSERT), not created_at (frozen at first insert) - got: {executed_sql}"
            )
            assert "MAX(created_at)" not in executed_sql
