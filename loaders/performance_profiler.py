"""Performance profiling for loader system.

Tracks execution times, identifies bottlenecks, and suggests optimizations.
"""

from typing import Dict, List, Tuple, Any
from datetime import datetime, timedelta
import logging
import psycopg2

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Profiles loader performance and identifies optimization opportunities."""

    def __init__(self, conn: Any):
        """Initialize profiler with database connection."""
        self.conn = conn

    def get_slowest_loaders(self, hours: int = 24, top_n: int = 5) -> List[Tuple[str, float, float]]:
        """Get slowest executing loaders."""
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT
                loader_name,
                ROUND(AVG(EXTRACT(epoch FROM (end_time - start_time))), 2) as avg_duration,
                ROUND(MAX(EXTRACT(epoch FROM (end_time - start_time))), 2) as max_duration
            FROM data_loader_runs
            WHERE execution_date > CURRENT_DATE - INTERVAL '{hours} hours'
            AND status = 'SUCCESS'
            GROUP BY loader_name
            ORDER BY AVG(EXTRACT(epoch FROM (end_time - start_time))) DESC
            LIMIT {top_n}
        """)
        return cur.fetchall()

    def get_loader_trends(self, loader_name: str, days: int = 7) -> List[Tuple[str, float]]:
        """Get execution time trend for a specific loader."""
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT
                execution_date::date,
                ROUND(AVG(EXTRACT(epoch FROM (end_time - start_time))), 2) as avg_duration
            FROM data_loader_runs
            WHERE loader_name = '{loader_name}'
            AND execution_date > CURRENT_DATE - INTERVAL '{days} days'
            AND status = 'SUCCESS'
            GROUP BY execution_date::date
            ORDER BY execution_date
        """)
        return cur.fetchall()

    def get_failure_rate(self, loader_name: str = None, hours: int = 24) -> Dict[str, Any]:
        """Get failure rates for loaders."""
        cur = self.conn.cursor()

        if loader_name:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful,
                    COUNT(CASE WHEN status != 'SUCCESS' THEN 1 END) as failed
                FROM data_loader_runs
                WHERE loader_name = '{loader_name}'
                AND execution_date > CURRENT_DATE - INTERVAL '{hours} hours'
            """)
        else:
            cur.execute(f"""
                SELECT
                    loader_name,
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful,
                    ROUND(100.0 * COUNT(CASE WHEN status != 'SUCCESS' THEN 1 END) / COUNT(*), 1) as failure_rate
                FROM data_loader_runs
                WHERE execution_date > CURRENT_DATE - INTERVAL '{hours} hours'
                GROUP BY loader_name
                HAVING COUNT(CASE WHEN status != 'SUCCESS' THEN 1 END) > 0
                ORDER BY failure_rate DESC
            """)

        if loader_name:
            result = cur.fetchone()
            if result:
                total, successful, failed = result
                failure_rate = 100 * failed / total if total > 0 else 0
                return {
                    "loader": loader_name,
                    "total_runs": total,
                    "successful_runs": successful,
                    "failed_runs": failed,
                    "failure_rate_pct": round(failure_rate, 1),
                }
        else:
            return {
                "loaders_with_failures": [
                    {
                        "loader": row[0],
                        "total_runs": row[1],
                        "successful": row[2],
                        "failure_rate_pct": row[3],
                    }
                    for row in cur.fetchall()
                ]
            }

    def get_pipeline_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify bottlenecks in the pipeline."""
        cur = self.conn.cursor()

        # Get slowest loaders
        slowest = self.get_slowest_loaders(hours=24, top_n=10)

        bottlenecks = []
        for loader_name, avg_time, max_time in slowest:
            if avg_time > 60:  # Only flag if > 1 minute
                bottlenecks.append({
                    "loader": loader_name,
                    "avg_duration_seconds": avg_time,
                    "max_duration_seconds": max_time,
                    "severity": "HIGH" if avg_time > 300 else "MEDIUM" if avg_time > 60 else "LOW",
                    "recommendation": self._get_optimization_suggestion(loader_name, avg_time),
                })

        return bottlenecks

    def _get_optimization_suggestion(self, loader_name: str, duration: float) -> str:
        """Get optimization suggestion based on loader and duration."""
        suggestions = {
            "financial_statements": "Parallelize SEC EDGAR fetches per ticker",
            "company_cache": "Batch yfinance requests, use parallel downloads",
            "technical_data_daily": "Cache RSI/MACD calculations, use vectorized operations",
            "trend_template_data": "Parallelize pattern scanning across symbols",
            "stock_scores": "Pre-compute metric normalization, cache weights",
            "buy_sell_daily": "Cache historical signals, only compute deltas",
        }

        for key, suggestion in suggestions.items():
            if key in loader_name.lower():
                return suggestion

        if duration > 300:
            return "Consider parallelization or chunking large datasets"
        elif duration > 60:
            return "Profile for hotspots, consider caching frequent operations"
        else:
            return "Performance is acceptable"

    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report."""
        return {
            "timestamp": datetime.now().isoformat(),
            "slowest_loaders": [
                {
                    "name": name,
                    "avg_duration": avg_dur,
                    "max_duration": max_dur,
                }
                for name, avg_dur, max_dur in self.get_slowest_loaders()
            ],
            "bottlenecks": self.get_pipeline_bottlenecks(),
            "failure_rates": self.get_failure_rate(),
        }

    def log_optimization_opportunities(self):
        """Log identified optimization opportunities."""
        bottlenecks = self.get_pipeline_bottlenecks()

        if bottlenecks:
            logger.info(f"Found {len(bottlenecks)} performance bottlenecks:")
            for bottleneck in bottlenecks:
                logger.info(f"  {bottleneck['loader']} ({bottleneck['severity']})")
                logger.info(f"    Duration: {bottleneck['avg_duration_seconds']:.1f}s avg")
                logger.info(f"    Suggestion: {bottleneck['recommendation']}")
        else:
            logger.info("No major performance bottlenecks detected")

        failures = self.get_failure_rate()
        if failures.get("loaders_with_failures"):
            logger.warning(f"Found {len(failures['loaders_with_failures'])} loaders with failures:")
            for loader_fail in failures["loaders_with_failures"]:
                logger.warning(f"  {loader_fail['loader']}: {loader_fail['failure_rate_pct']}% failure rate")


class PerformanceMonitor:
    """Tracks performance metrics over time."""

    def __init__(self, conn: Any):
        """Initialize monitor with database connection."""
        self.conn = conn
        self.profiler = PerformanceProfiler(conn)

    def get_daily_summary(self, date_str: str = None) -> Dict[str, Any]:
        """Get performance summary for a specific date."""
        cur = self.conn.cursor()

        if not date_str:
            date_str = datetime.now().date().isoformat()

        cur.execute(f"""
            SELECT
                COUNT(*) as total_executions,
                COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful,
                ROUND(AVG(EXTRACT(epoch FROM (end_time - start_time))), 2) as avg_duration,
                ROUND(MIN(EXTRACT(epoch FROM (end_time - start_time))), 2) as min_duration,
                ROUND(MAX(EXTRACT(epoch FROM (end_time - start_time))), 2) as max_duration
            FROM data_loader_runs
            WHERE execution_date::date = '{date_str}'
        """)

        result = cur.fetchone()
        if result:
            total, successful, avg_dur, min_dur, max_dur = result
            return {
                "date": date_str,
                "total_executions": total,
                "successful_runs": successful,
                "failure_rate_pct": round(100 * (total - successful) / total, 1) if total > 0 else 0,
                "avg_duration_seconds": avg_dur,
                "min_duration_seconds": min_dur,
                "max_duration_seconds": max_dur,
            }

        return None

    def get_weekly_trends(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get performance trends over N days."""
        cur = self.conn.cursor()
        cur.execute(f"""
            SELECT
                execution_date::date,
                COUNT(*) as total_executions,
                COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as successful,
                ROUND(AVG(EXTRACT(epoch FROM (end_time - start_time))), 2) as avg_duration
            FROM data_loader_runs
            WHERE execution_date > CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY execution_date::date
            ORDER BY execution_date DESC
        """)

        return [
            {
                "date": str(row[0]),
                "total_executions": row[1],
                "successful_runs": row[2],
                "avg_duration_seconds": row[3],
            }
            for row in cur.fetchall()
        ]
