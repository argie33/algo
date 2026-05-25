"""
Loader Health Tracker
Track data loader execution status and update data_loader_status table.
Provides visibility into which loaders are working and data freshness.
"""

import os
import psycopg2.extras
from config.credential_helper import get_db_config
from datetime import datetime, timezone, timedelta
import logging
from algo.algo_sql_safety import assert_safe_table, assert_safe_column

logger = logging.getLogger(__name__)


class LoaderHealthTracker:
    """Track loader execution status and data freshness."""

    TABLE_CONFIGS = {
        'stock_symbols': {'frequency': 'daily', 'role': 'symbols', 'threshold': 1},
        'price_daily': {'frequency': 'daily', 'role': 'prices', 'threshold': 3},
        'price_weekly': {'frequency': 'weekly', 'role': 'prices', 'threshold': 7},
        'technical_indicators_daily': {'frequency': 'daily', 'role': 'indicators', 'threshold': 3},
        'stock_scores': {'frequency': 'daily', 'role': 'scores', 'threshold': 3},
        'buy_sell_daily': {'frequency': 'daily', 'role': 'signals', 'threshold': 3},
        'economic_data': {'frequency': 'daily', 'role': 'economic', 'threshold': 7},
        'fear_greed_index': {'frequency': 'daily', 'role': 'sentiment', 'threshold': 7},
        'naaim': {'frequency': 'daily', 'role': 'sentiment', 'threshold': 7},
        'aaii_sentiment': {'frequency': 'daily', 'role': 'sentiment', 'threshold': 7},
        'analyst_sentiment_analysis': {'frequency': 'daily', 'role': 'analyst', 'threshold': 7},
        'analyst_upgrade_downgrade': {'frequency': 'daily', 'role': 'analyst', 'threshold': 7},
        'earnings_calendar': {'frequency': 'daily', 'role': 'earnings', 'threshold': 7},
        'company_profile': {'frequency': 'weekly', 'role': 'fundamentals', 'threshold': 14},
        'sector_performance': {'frequency': 'daily', 'role': 'sectors', 'threshold': 3},
        'industry_ranking': {'frequency': 'daily', 'role': 'industries', 'threshold': 3},
    }

    def __init__(self):
        """Initialize database connection."""
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to PostgreSQL database."""
        try:
            self.conn = psycopg2.connect(
                host=get_db_config()['host'],
                port=int(os.getenv('DB_PORT', 5432)),
                user=get_db_config()['user'],
                password=os.getenv('DB_PASSWORD', ''),
                database=get_db_config()['database'],
            )
            self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            logger.info("✓ Connected to database")
        except Exception as e:
            logger.info(f"✗ Database connection failed: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def check_table_health(self, table_name):
        """
        Check the health of a single table.
        Returns dict with latest_date, row_count, age_days, status.
        """
        try:
            assert_safe_table(table_name)
            self.cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
            """, (table_name,))

            if not self.cur.fetchone()[0]:
                return {
                    'table_name': table_name,
                    'latest_date': None,
                    'row_count': 0,
                    'age_days': None,
                    'status': 'MISSING',
                    'error_message': f'Table {table_name} does not exist'
                }

            # Try common date column names
            date_columns = ['date', 'created_at', 'updated_at', 'last_run', 'action_date', 'earnings_date']
            latest_date = None
            date_col_used = None

            for date_col in date_columns:
                try:
                    assert_safe_column(date_col)
                    self.cur.execute(f"""
                        SELECT MAX({date_col}::DATE) FROM {table_name}
                    """)
                    latest_date = self.cur.fetchone()[0]
                    if latest_date:
                        date_col_used = date_col
                        break
                except (psycopg2.Error, ValueError, TypeError):
                    continue

            self.cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = self.cur.fetchone()[0] if self.cur.fetchone() else 0

            # Calculate age in days
            if latest_date:
                age_days = (datetime.now(timezone.utc).date() - latest_date).days
            else:
                age_days = None

            # Determine status
            if row_count == 0:
                status = 'EMPTY'
            elif latest_date is None:
                status = 'EMPTY'
            else:
                threshold = self.TABLE_CONFIGS.get(table_name, {}).get('threshold', 7)
                if age_days <= threshold:
                    status = 'HEALTHY'
                elif age_days <= threshold * 2:
                    status = 'STALE'
                else:
                    status = 'VERY_STALE'

            return {
                'table_name': table_name,
                'latest_date': latest_date,
                'row_count': row_count,
                'age_days': age_days,
                'status': status,
                'error_message': None,
                'date_column': date_col_used
            }

        except Exception as e:
            return {
                'table_name': table_name,
                'latest_date': None,
                'row_count': 0,
                'age_days': None,
                'status': 'ERROR',
                'error_message': str(e)
            }

    def update_loader_status(self, health_check):
        """Update data_loader_status table with health check results."""
        try:
            config = self.TABLE_CONFIGS.get(health_check['table_name'], {})

            self.cur.execute("""
                INSERT INTO data_loader_status
                (table_name, frequency, role, latest_date, age_days, row_count,
                 stale_threshold_days, status, last_updated, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (table_name) DO UPDATE SET
                    latest_date = EXCLUDED.latest_date,
                    age_days = EXCLUDED.age_days,
                    row_count = EXCLUDED.row_count,
                    status = EXCLUDED.status,
                    last_updated = EXCLUDED.last_updated,
                    error_message = EXCLUDED.error_message
            """, (
                health_check['table_name'],
                config.get('frequency', 'unknown'),
                config.get('role', 'unknown'),
                health_check['latest_date'],
                health_check['age_days'],
                health_check['row_count'],
                config.get('threshold', 7),
                health_check['status'],
                datetime.now(timezone.utc),
                health_check['error_message']
            ))
            self.conn.commit()
        except Exception as e:
            logger.info(f"✗ Failed to update status for {health_check['table_name']}: {e}")
            if self.conn:
                self.conn.rollback()

    def run_health_check(self, verbose=True):
        """Run health check on all critical tables."""
        if not self.conn:
            self.connect()

        results = []
        status_summary = {'HEALTHY': 0, 'STALE': 0, 'VERY_STALE': 0, 'EMPTY': 0, 'MISSING': 0, 'ERROR': 0}

        for table_name in self.TABLE_CONFIGS.keys():
            health = self.check_table_health(table_name)
            results.append(health)
            self.update_loader_status(health)

            status = health['status']
            status_summary[status] = status_summary.get(status, 0) + 1

            if verbose:
                symbol = '✓' if status == 'HEALTHY' else '⚠' if status in ('STALE', 'VERY_STALE') else '✗'
                age = f"{health['age_days']}d" if health['age_days'] is not None else "N/A"
                rows = f"{health['row_count']:,}"
                logger.info(f"{symbol} {table_name:40} | {status:12} | Age: {age:6} | Rows: {rows}")

        if verbose:
            logger.info("\n" + "="*80)
            logger.info(f"Summary: {status_summary['HEALTHY']} healthy, {status_summary['STALE']} stale, "
                  f"{status_summary['EMPTY']} empty, {status_summary['ERROR']} errors")

        return results, status_summary


def main():
    """Main entry point."""
    tracker = LoaderHealthTracker()
    try:
        tracker.connect()
        results, summary = tracker.run_health_check(verbose=True)

        # Exit with error code if any critical tables are empty or missing
        if summary['EMPTY'] > 0 or summary['MISSING'] > 0:
            logger.info("\n⚠ WARNING: Critical tables are empty or missing!")
            return 1

        return 0
    finally:
        tracker.disconnect()


if __name__ == '__main__':
    import sys
    sys.exit(main())
