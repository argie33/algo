"""Regression test for the 2026-08-16 fix: 7 tables (market_exposure_daily,
etf_price_daily, algo_portfolio_snapshots, algo_risk_daily, algo_performance_daily,
signal_quality_scores, trend_template_data) were missing from PipelineHealth.CRITICAL_TABLES
entirely, so every health sweep fell through to the 7-day default SLA and silently
overwrote a documented earlier one-time DB fix (stale_threshold_days=1) back to 7 on every
run - live-confirmed 2026-08-16 via direct DB query before this fix.

Guards against the same 7 tables (or a future addition) silently falling back out of
CRITICAL_TABLES/TRADING_DAY_CADENCE_TABLES, and against algo_portfolio_snapshots' date
column (snapshot_date) dropping back out of utils/db/sql_safety.py's SAFE_COLUMNS - both
of which the sweep failed on when live-verifying this fix (the first with no visible error
at all, the second with "Unknown column 'snapshot_date' (not in whitelist)").
"""

from algo.monitoring.pipeline_health import PipelineHealth
from utils.db.sql_safety import SAFE_COLUMNS

PREVIOUSLY_MISSING_TABLES = {
    "market_exposure_daily",
    "etf_price_daily",
    "algo_portfolio_snapshots",
    "algo_risk_daily",
    "algo_performance_daily",
    "signal_quality_scores",
    "trend_template_data",
}


class TestPipelineHealthCriticalTablesCompleteness:
    def test_previously_missing_tables_are_in_critical_tables_with_sla_1(self):
        for table in PREVIOUSLY_MISSING_TABLES:
            assert table in PipelineHealth.CRITICAL_TABLES, f"{table} missing from CRITICAL_TABLES"
            assert PipelineHealth.CRITICAL_TABLES[table]["sla_days"] == 1, (
                f"{table} sla_days should match freshness_config.py's canonical max_age_days=1"
            )

    def test_previously_missing_tables_are_trading_day_cadence(self):
        for table in PREVIOUSLY_MISSING_TABLES:
            assert table in PipelineHealth.TRADING_DAY_CADENCE_TABLES, (
                f"{table} needs weekend-gap adjustment - it's only written when the "
                "orchestrator actually runs, which only happens on trading days"
            )

    def test_algo_portfolio_snapshots_date_column_is_queryable(self):
        date_column = PipelineHealth.CRITICAL_TABLES["algo_portfolio_snapshots"]["date_column"]
        assert date_column in SAFE_COLUMNS, (
            f"'{date_column}' must be in SAFE_COLUMNS or check_table_health() raises "
            "'Unknown column ... (not in whitelist)' for algo_portfolio_snapshots"
        )


class TestStockScoresSlaMatchesRealCadence:
    """Regression test for the 2026-08-24 fix ("scores stale but loader health OK"
    goal session): stock_scores sat at sla_days=5 in CRITICAL_TABLES since this table
    was first added, 5x looser than utils/validation/freshness_config.py's canonical
    max_age_days=1 and phase1_data_freshness.py's real ~1-trading-day requirement.

    log_health_check() writes this sweep's HEALTHY/STALE verdict straight to
    data_loader_status.status, which lambda/api/routes/algo_handlers/monitoring.py's
    loader_health check (`/api/algo/freshness/extended`) trusts with no independent
    age check - so a real 2-4 day stock_scores staleness (correctly flagged STALE by
    the dashboard SCORES panel's check_data_freshness(warning_days=1)) still wrote
    status='HEALTHY' here, making the Loader Health panel report "all healthy" while
    SCORES showed "STALE" for days. Same bug class as the 2026-08-16 fix for
    market_exposure_daily/market_health_daily/algo_risk_daily above.
    """

    def test_stock_scores_sla_matches_freshness_config(self):
        assert PipelineHealth.CRITICAL_TABLES["stock_scores"]["sla_days"] == 1, (
            "stock_scores sla_days should match freshness_config.py's canonical max_age_days=1"
        )

    def test_stock_scores_is_trading_day_cadence(self):
        assert "stock_scores" in PipelineHealth.TRADING_DAY_CADENCE_TABLES, (
            "stock_scores needs weekend-gap adjustment now that its sla_days is tight (1) - "
            "it's only computed from price_daily/technical_data_daily, both already trading-day cadence"
        )
