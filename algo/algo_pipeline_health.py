#!/usr/bin/env python3

import os
import logging
from datetime import date as _date, datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"  # Data older than SLA
    VERY_STALE = "VERY_STALE"  # Data > 2x SLA old
    MISSING = "MISSING"  # Table empty
    ERROR = "ERROR"  # Query failed

@dataclass
class TableHealth:
    """Health status for a single table."""
    table_name: str
    status: HealthStatus
    row_count: int = 0
    latest_date: Optional[_date] = None
    age_days: int = 0
    sla_days: int = 7
    last_checked: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    @property
    def is_critical(self) -> bool:
        """Check if table is critical for algo execution.

        buy_sell_daily and stock_scores are excluded — they are orchestrator OUTPUTS
        (written by Phase 5/6), not upstream inputs. Treating them as critical halts
        Phase 1 before Phase 5/6 can populate them (circular dependency).

        economic_data is excluded — it stores FRED macro series with no pipeline loader;
        algo_market_exposure.py handles missing rows with safe defaults.
        """
        critical_tables = {
            'stock_symbols', 'price_daily',
            'market_health_daily',
        }
        return self.table_name in critical_tables

    def to_dict(self) -> Dict:
        return {
            'table': self.table_name,
            'status': self.status.value,
            'rows': self.row_count,
            'latest_date': self.latest_date.isoformat() if self.latest_date else None,
            'age_days': self.age_days,
            'sla_days': self.sla_days,
            'is_healthy': self.is_healthy,
            'is_critical': self.is_critical,
            'error': self.error_message
        }

@dataclass
class PipelineStatus:
    """Overall pipeline health status."""
    timestamp: datetime = field(default_factory=datetime.now)
    tables: Dict[str, TableHealth] = field(default_factory=dict)
    is_healthy: bool = True
    critical_alerts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def healthy_count(self) -> int:
        return sum(1 for t in self.tables.values() if t.is_healthy)

    @property
    def total_count(self) -> int:
        return len(self.tables)

    @property
    def coverage_pct(self) -> float:
        if not self.tables:
            return 0.0
        return (self.healthy_count / self.total_count) * 100

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'is_healthy': self.is_healthy,
            'healthy_count': self.healthy_count,
            'total_count': self.total_count,
            'coverage_pct': round(self.coverage_pct, 1),
            'critical_alerts': self.critical_alerts,
            'warnings': self.warnings,
            'tables': {name: t.to_dict() for name, t in self.tables.items()}
        }

class PipelineHealth:
    """Monitor and report on data pipeline health."""

    # Define critical tables and their SLA requirements.
    # market_health_daily and price_daily use sla_days=5 so that a 3-day holiday
    # weekend (e.g. Memorial Day Friday → Tuesday = 4 calendar days) or a 4-day
    # Thanksgiving break (Wednesday → Monday = 5 days) does not trigger a VERY_STALE
    # critical halt in Phase 1. Phase 1's explicit staleness check uses trading-day-
    # aware comparison; PipelineHealth is a secondary check and should not over-block.
    CRITICAL_TABLES = {
        'stock_symbols': {'date_column': 'created_at', 'sla_days': 30},
        'price_daily': {'date_column': 'date', 'sla_days': 5},
        'buy_sell_daily': {'date_column': 'date', 'sla_days': 5},
        'stock_scores': {'date_column': 'updated_at', 'sla_days': 5},
        'economic_data': {'date_column': 'date', 'sla_days': 7},
        'market_health_daily': {'date_column': 'date', 'sla_days': 5},
        'analyst_sentiment_analysis': {'date_column': 'updated_at', 'sla_days': 7},
        'earnings_calendar': {'date_column': 'created_at', 'sla_days': 30},
    }

    def check_table_health(self, cur, table_name: str, date_column: str, sla_days: int) -> TableHealth:
        """Check health of a single table."""
        health = TableHealth(
            table_name=table_name,
            status=HealthStatus.ERROR,
            sla_days=sla_days
        )

        try:
            safe_table = assert_safe_table(table_name)
            safe_date_col = assert_safe_column(date_column)

            # Use pg_class.reltuples for O(1) approximate row count instead of
            # COUNT(*) full scan. reltuples is updated by ANALYZE and is accurate
            # enough to detect empty vs populated tables without blocking I/O.
            cur.execute(
                "SELECT GREATEST(reltuples, 0)::BIGINT FROM pg_class WHERE relname = %s LIMIT 1",
                (table_name,)
            )
            result = cur.fetchone()
            health.row_count = int(result[0]) if result else 0

            if health.row_count == 0:
                health.status = HealthStatus.MISSING
                health.error_message = "Table is empty"
                return health

            # Use ORDER BY + LIMIT 1 instead of MAX() — forces an index scan and
            # avoids sequential scans when PostgreSQL statistics are stale (reltuples=0
            # on t4g.micro after bulk inserts). MAX() with stale stats can take 30s+.
            cur.execute(f"SELECT {safe_date_col}::DATE FROM {safe_table} ORDER BY {safe_date_col} DESC LIMIT 1")
            result = cur.fetchone()
            latest_date = result[0] if result else None

            if not latest_date:
                health.status = HealthStatus.MISSING
                health.error_message = f"No {date_column} values found"
                return health

            if isinstance(latest_date, datetime):
                latest_date = latest_date.date()

            health.latest_date = latest_date
            health.age_days = (_date.today() - latest_date).days

            # Determine status based on SLA
            if health.age_days > (sla_days * 2):
                health.status = HealthStatus.VERY_STALE
            elif health.age_days > sla_days:
                health.status = HealthStatus.STALE
            else:
                health.status = HealthStatus.HEALTHY

        except Exception as e:
            health.status = HealthStatus.ERROR
            health.error_message = str(e)

        return health

    def get_pipeline_status(self) -> PipelineStatus:
        """Get complete pipeline health status."""
        status = PipelineStatus()

        try:
            with DatabaseContext('read') as cur:
                # Set statement timeout for health checks (fail fast)
                stmt_timeout_ms = int(os.getenv('DB_STATEMENT_TIMEOUT_MS', 30000))
                cur.execute(f"SET statement_timeout = {stmt_timeout_ms}")

                for table_name, config in self.CRITICAL_TABLES.items():
                    try:
                        health = self.check_table_health(
                            cur,
                            table_name,
                            config['date_column'],
                            config['sla_days']
                        )
                        status.tables[table_name] = health

                        # Alert on critical issues
                        if health.is_critical:
                            if health.status == HealthStatus.MISSING:
                                status.critical_alerts.append(
                                    f"CRITICAL: {table_name} is empty - no trades can execute"
                                )
                            elif health.status == HealthStatus.VERY_STALE:
                                status.critical_alerts.append(
                                    f"CRITICAL: {table_name} is very stale ({health.age_days} days old)"
                                )
                            elif health.status == HealthStatus.STALE:
                                status.warnings.append(
                                    f"WARNING: {table_name} is stale ({health.age_days} days old)"
                                )
                    except Exception as e:
                        logger.error(f"Error checking {table_name}: {e}")
                        status.tables[table_name] = TableHealth(
                            table_name=table_name,
                            status=HealthStatus.ERROR,
                            error_message=str(e)
                        )
        except Exception as e:
            logger.error(f"Cannot check pipeline status: {e}")
            status.is_healthy = False
            status.critical_alerts.append(f"Database connection failed: {e}")
            return status

        # Overall health determination
        has_critical_issues = any(
            not t.is_healthy and t.is_critical
            for t in status.tables.values()
        )
        status.is_healthy = not has_critical_issues and len(status.critical_alerts) == 0

        return status

    def log_health_check(self, status: PipelineStatus):
        """Log pipeline health to database for historical tracking."""
        try:
            with DatabaseContext('write') as cur:
                for table_health in status.tables.values():
                    cur.execute(
                        """
                        INSERT INTO data_loader_status
                        (table_name, status, row_count, latest_date, age_days, last_updated)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (table_name)
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            row_count = EXCLUDED.row_count,
                            latest_date = EXCLUDED.latest_date,
                            age_days = EXCLUDED.age_days,
                            last_updated = NOW()
                        """,
                        (
                            table_health.table_name,
                            table_health.status.value,
                            table_health.row_count,
                            table_health.latest_date,
                            table_health.age_days
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to log health check: {e}")

    def assert_pipeline_ready(self) -> bool:
        """Check if pipeline is ready for trading.
        Raises exception if critical data is missing/stale.
        """
        status = self.get_pipeline_status()

        if status.critical_alerts:
            error_msg = "Pipeline not ready for trading:\n" + "\n".join(status.critical_alerts)
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        return True

if __name__ == '__main__':
    import json
    health = PipelineHealth()
    status = health.get_pipeline_status()
    logger.info(json.dumps(status.to_dict(), indent=2, default=str))
