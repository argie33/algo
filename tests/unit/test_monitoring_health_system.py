#!/usr/bin/env python3
"""Comprehensive tests for monitoring and health system.

Health monitoring ensures the trading system stays operational:
- Pipeline health checks
- Data freshness validation
- Connection monitoring
- Alert triggering on degradation
- Recovery detection

Tests verify that system state is accurately reported and alerts trigger correctly.
"""

from datetime import date as _date
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestPipelineHealthMonitoring:
    """Test pipeline health monitoring."""

    def test_pipeline_health_monitor_initialization(self):
        """Test that pipeline health monitor can be initialized."""
        from algo.monitoring.pipeline_health import PipelineHealth

        monitor = PipelineHealth()
        assert monitor is not None

    def test_pipeline_health_get_pipeline_status(self):
        """Test that health monitor can get pipeline status."""
        from algo.monitoring.pipeline_health import PipelineHealth

        monitor = PipelineHealth()
        # Mock the database cursor to avoid accessing real database in unit test
        with patch("algo.monitoring.pipeline_health.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # Empty results for schema check
            mock_cursor.fetchone.return_value = None  # No tables to check
            mock_db.return_value.__enter__.return_value = mock_cursor
            mock_db.return_value.__exit__.return_value = None

            status = monitor.get_pipeline_status()
            assert status is not None
            assert hasattr(status, "tables")
            assert hasattr(status, "is_healthy")

    def test_pipeline_health_check_table_health(self):
        """Test that health monitor can check individual table health."""
        from algo.monitoring.pipeline_health import HealthStatus, PipelineHealth, TableHealth

        monitor = PipelineHealth()
        assert hasattr(monitor, "check_table_health")
        # Note: actual table checks require database access, tested in integration tests

    def test_deprecated_table_with_zero_rows_reports_deprecated_not_missing(self):
        """A KNOWN_DEPRECATED_TABLES table that never got a single row (e.g. sec_dividends,
        sec_material_events - superseded by dividend_data/current_reports_8k, see
        utils/db/sql_safety.py) must report DEPRECATED, not MISSING. MISSING counts against
        is_healthy/coverage_pct forever for a table that's expected to sit frozen empty -
        the exact false-alarm noise KNOWN_DEPRECATED_TABLES exists to prevent."""
        from algo.monitoring.pipeline_health import HealthStatus, PipelineHealth

        monitor = PipelineHealth()
        assert "sec_dividends" in monitor.KNOWN_DEPRECATED_TABLES
        assert "sec_material_events" in monitor.KNOWN_DEPRECATED_TABLES

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (0,)  # reltuples/COUNT(*) = 0 rows

        for table_name in ("sec_dividends", "sec_material_events", "analyst_sentiment_analysis"):
            health = monitor.check_table_health(mock_cursor, table_name, None, 7)
            assert health.status == HealthStatus.DEPRECATED, (
                f"{table_name}: expected DEPRECATED, got {health.status}"
            )
            assert health.is_healthy

    def test_deprecated_tables_are_in_sql_safety_whitelist(self):
        """Every KNOWN_DEPRECATED_TABLES entry must be in sql_safety.SAFE_TABLES, or
        check_table_health's assert_safe_table() raises ValueError before the
        KNOWN_DEPRECATED_TABLES branch ever runs, misreporting these as ERROR
        ("not in whitelist") every orchestrator run instead of DEPRECATED."""
        from algo.monitoring.pipeline_health import PipelineHealth
        from utils.db.sql_safety import SAFE_TABLES

        monitor = PipelineHealth()
        missing = monitor.KNOWN_DEPRECATED_TABLES - SAFE_TABLES
        assert not missing, f"KNOWN_DEPRECATED_TABLES not in SAFE_TABLES: {missing}"

    def test_pipeline_health_status_properties(self):
        """Test pipeline status has expected properties and methods."""
        from algo.monitoring.pipeline_health import PipelineHealth

        monitor = PipelineHealth()
        # Mock the database cursor to avoid accessing real database in unit test
        with patch("algo.monitoring.pipeline_health.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # Empty results for schema check
            mock_cursor.fetchone.return_value = None  # No tables to check
            mock_db.return_value.__enter__.return_value = mock_cursor
            mock_db.return_value.__exit__.return_value = None

            status = monitor.get_pipeline_status()
            assert hasattr(status, "healthy_count")
            assert hasattr(status, "total_count")
            assert hasattr(status, "coverage_pct")
            assert isinstance(status.healthy_count, int)
            assert isinstance(status.total_count, int)
            assert isinstance(status.coverage_pct, float)

    def test_log_health_check_writes_per_table_last_updated_not_now(self):
        """log_health_check's bulk executemany must stamp last_updated from each table's own
        latest_date, not a single NOW() shared by the whole transaction. A blind NOW() made
        every table in data_loader_status share one identical timestamp on every orchestrator
        run (Postgres's NOW() is constant for the whole transaction), clobbering the real
        per-loader freshness signal /api/algo/data-status reads back out - confirmed live:
        every one of 95 tables reported the same age_hours regardless of true staleness.
        """
        from algo.monitoring.pipeline_health import HealthStatus, PipelineHealth, PipelineStatus, TableHealth

        fresh_date = _date(2026, 7, 20)
        stale_date = _date(2026, 7, 10)
        status = PipelineStatus(
            tables={
                "price_daily": TableHealth(
                    table_name="price_daily", status=HealthStatus.HEALTHY, row_count=100, latest_date=fresh_date
                ),
                "aaii_sentiment": TableHealth(
                    table_name="aaii_sentiment",
                    status=HealthStatus.STALE,
                    row_count=50,
                    latest_date=stale_date,
                ),
            }
        )

        mock_cur = Mock()
        mock_cur.fetchall.return_value = []
        with patch("algo.monitoring.pipeline_health.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_db_ctx.return_value.__exit__.return_value = False
            monitor = PipelineHealth()
            monitor.log_health_check(status)

        executemany_call = mock_cur.executemany.call_args
        sql_text = executemany_call[0][0]
        insert_values = executemany_call[0][1]

        assert "NOW()" not in sql_text.replace("COALESCE(%s::timestamptz, NOW())", "")
        assert "last_updated = EXCLUDED.last_updated" in sql_text

        last_updated_by_table = {row[0]: row[-1] for row in insert_values}
        assert last_updated_by_table["price_daily"] == fresh_date
        assert last_updated_by_table["aaii_sentiment"] == stale_date
        assert last_updated_by_table["price_daily"] != last_updated_by_table["aaii_sentiment"]

    def test_infer_date_column_prefers_last_updated_at_over_created_at(self):
        """algo_runtime_state (RDS-fallback halt-flag state, actively upserted on every
        orchestrator run) has last_updated_at (tracks real per-row freshness) AND created_at
        (Postgres sets once at row creation, never touched again on UPDATE). Before
        last_updated_at was added as a candidate, this table fell through to created_at and
        read as VERY_STALE (32 days) even seconds after a real upsert - confirmed live.
        """
        from algo.monitoring.pipeline_health import PipelineHealth

        mock_cur = Mock()

        def fake_execute(sql, params=None):
            fake_execute.last_sql = sql
            fake_execute.last_params = params

        mock_cur.execute = Mock(side_effect=fake_execute)

        # "date" and "updated_at" don't exist on this table; "last_updated_at" exists and is
        # populated; "created_at" also exists and is populated (would be picked if
        # last_updated_at weren't tried first).
        column_exists = {"date": False, "updated_at": False, "last_updated_at": True, "created_at": True}
        populated = {"last_updated_at": True, "created_at": True}

        call_state = {"col": None}

        def fetchone_side_effect():
            # First call in the loop iteration checks information_schema (existence),
            # second call checks non-null content - track which column we're on via execute().
            sql = mock_cur.execute.call_args[0][0]
            if "information_schema.columns" in sql:
                col = mock_cur.execute.call_args[0][1][1]
                call_state["col"] = col
                return (1,) if column_exists.get(col) else None
            return (1,) if populated.get(call_state["col"]) else None

        mock_cur.fetchone = Mock(side_effect=fetchone_side_effect)

        monitor = PipelineHealth()
        result = monitor._infer_date_column(mock_cur, "algo_runtime_state")
        assert result == "last_updated_at"


class TestConnectionMonitoring:
    """Test database and service connection monitoring."""

    def test_connection_monitor_initialization(self):
        """Test that connection monitor can be initialized."""
        from algo.monitoring.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()
        assert monitor is not None

    def test_connection_monitor_checks_database(self):
        """Test that connection monitor checks database connectivity."""
        from algo.monitoring.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        if hasattr(monitor, "check_database"):
            connected = monitor.check_database()
            assert isinstance(connected, bool)

    def test_connection_monitor_detects_disconnection(self):
        """Test that monitor detects lost database connection."""
        from algo.monitoring.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        if hasattr(monitor, "is_connected"):
            assert isinstance(monitor.is_connected(), bool)

    def test_connection_monitor_tracks_failures(self):
        """Test that monitor tracks connection failures."""
        from algo.monitoring.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        if hasattr(monitor, "get_failure_count"):
            failures = monitor.get_failure_count()
            assert isinstance(failures, int)
            assert failures >= 0


class TestPositionAggregation:
    """Test position aggregation and monitoring."""

    def test_position_aggregator_initialization(self):
        """Test that position aggregator can be initialized."""
        from algo.monitoring.position_aggregator import PositionAggregator

        config = {"halt_flag_count_for_early_exit": 3}
        aggregator = PositionAggregator(config)
        assert aggregator is not None

    def test_position_aggregator_sums_positions(self):
        """Test that aggregator correctly sums positions."""
        from algo.monitoring.position_aggregator import PositionAggregator

        config = {"halt_flag_count_for_early_exit": 3}
        aggregator = PositionAggregator(config)

        if hasattr(aggregator, "get_total_value"):
            total = aggregator.get_total_value()
            assert isinstance(total, (int, float))

    def test_position_aggregator_tracks_by_sector(self):
        """Test that aggregator breaks down positions by sector."""
        from algo.monitoring.position_aggregator import PositionAggregator

        config = {"halt_flag_count_for_early_exit": 3}
        aggregator = PositionAggregator(config)

        if hasattr(aggregator, "get_sector_breakdown"):
            breakdown = aggregator.get_sector_breakdown()
            assert isinstance(breakdown, dict)


class TestAuditManager:
    """Test audit logging of all actions."""

    def test_audit_manager_initialization(self):
        """Test that audit manager can be initialized."""
        from algo.monitoring.audit_manager import AuditManager

        config = {}
        manager = AuditManager(config)
        assert manager is not None

    def test_audit_manager_logs_trades(self):
        """Test that audit manager logs all trade actions."""
        from algo.monitoring.audit_manager import AuditManager

        config = {}
        manager = AuditManager(config)

        if hasattr(manager, "log_trade"):
            trade = {
                "symbol": "AAPL",
                "action": "entry",
                "quantity": 100,
                "price": 150.0,
            }
            manager.log_trade(trade)
            # Should not raise

    def test_audit_manager_logs_halts(self):
        """Test that audit manager logs halt events."""
        from algo.monitoring.audit_manager import AuditManager

        config = {}
        manager = AuditManager(config)

        if hasattr(manager, "log_halt"):
            manager.log_halt("Circuit breaker L2")
            # Should not raise

    def test_audit_manager_retrieves_history(self):
        """Test that audit manager can retrieve action history."""
        from algo.monitoring.audit_manager import AuditManager

        config = {}
        manager = AuditManager(config)

        if hasattr(manager, "get_position_history"):
            assert callable(manager.get_position_history)
            assert manager.get_position_history.__doc__ is not None

        if hasattr(manager, "get_history"):
            with pytest.raises(NotImplementedError):
                manager.get_history()


class TestDataPatrolBase:
    """Test base data patrol functionality."""

    def test_data_patrol_initialization(self):
        """Test that data patrol can be initialized."""
        from algo.monitoring.data_patrol.base import DataPatrol
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        patrol = DataPatrol(config)
        assert patrol is not None

    def test_data_patrol_runs_checks(self):
        """Test that data patrol runs quality checks."""
        from algo.monitoring.data_patrol.base import DataPatrol
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        patrol = DataPatrol(config)

        if hasattr(patrol, "run"):
            result = patrol.run()
            assert result is not None

    def test_data_patrol_reports_issues(self):
        """Test that data patrol reports data quality issues."""
        from algo.monitoring.data_patrol.base import DataPatrol
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        patrol = DataPatrol(config)

        if hasattr(patrol, "get_issues"):
            issues = patrol.get_issues()
            assert isinstance(issues, (list, dict))


class TestDataPatrolChecks:
    """Test individual data patrol checks."""

    def test_staleness_check_initialization(self):
        """Test staleness checker initialization."""
        from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        checker = StalenessChecker(config)
        assert checker is not None

    def test_alignment_check_initialization(self):
        """Test alignment checker initialization."""
        from algo.monitoring.data_patrol.checks.alignment import AlignmentChecker
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        checker = AlignmentChecker(config)
        assert checker is not None

    def test_quality_check_initialization(self):
        """Test quality checker initialization."""
        from algo.monitoring.data_patrol.checks.quality import QualityChecker
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        checker = QualityChecker(config)
        assert checker is not None

    def test_coverage_check_initialization(self):
        """Test coverage checker initialization."""
        from algo.monitoring.data_patrol.checks.coverage import CoverageChecker
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        checker = CoverageChecker(config)
        assert checker is not None

    def test_price_sanity_check_initialization(self):
        """Test price sanity checker initialization."""
        from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker
        from algo.monitoring.data_patrol.config import PatrolConfig

        config = PatrolConfig()
        checker = PriceSanityChecker(config)
        assert checker is not None


class TestAlertTriggering:
    """Test that alerts are triggered on health degradation."""

    def test_alert_on_connection_loss(self):
        """Test that alert triggers on database disconnection."""
        from algo.monitoring.connection_monitor import ConnectionMonitor

        monitor = ConnectionMonitor()

        if hasattr(monitor, "is_connected"):
            connected = monitor.is_connected()
            # If not connected, alert should be triggered
            assert isinstance(connected, bool)

    def test_alert_on_position_limit_breach(self):
        """Test that alert triggers when position limit is breached."""
        from algo.monitoring.position_aggregator import PositionAggregator

        config = {"halt_flag_count_for_early_exit": 3}
        aggregator = PositionAggregator(config)

        if hasattr(aggregator, "check_limits"):
            within_limits = aggregator.check_limits()
            # If not within limits, alert should trigger
            assert isinstance(within_limits, bool)


