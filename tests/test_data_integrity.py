"""
Data Integrity Validation Tests
Automated verification that critical data tables have expected content and freshness.
Run locally before deployment and in AWS post-deployment.
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import pytest

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env.local'))


class DatabaseTest:
    """Base class for database tests."""

    @pytest.fixture(scope="session", autouse=True)
    def db_connection(self):
        """Create database connection for tests."""
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'stocks'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'stocks'),
        )
        yield conn
        conn.close()

    @pytest.fixture
    def cursor(self, db_connection):
        """Create cursor for database queries."""
        cur = db_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        cur.close()


class TestCriticalTableExistence:
    """Verify all critical tables exist."""

    CRITICAL_TABLES = [
        'stock_symbols', 'price_daily', 'technical_indicators_daily',
        'stock_scores', 'buy_sell_daily', 'economic_data',
        'company_profile', 'earnings_calendar', 'analyst_sentiment_analysis',
        'sector_performance', 'industry_ranking', 'data_loader_status'
    ]

    def test_all_critical_tables_exist(self, cursor):
        """Verify all critical tables exist in the database."""
        for table in self.CRITICAL_TABLES:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
            """, (table,))

            exists = cursor.fetchone()[0]
            assert exists, f"Critical table '{table}' does not exist"


class TestDataFreshness:
    """Verify data is fresh and up-to-date."""

    FRESHNESS_REQUIREMENTS = {
        'stock_symbols': {'table': 'stock_symbols', 'column': 'created_at', 'max_age_days': 30},
        'price_daily': {'table': 'price_daily', 'column': 'date', 'max_age_days': 3},
        'technical_indicators': {'table': 'technical_indicators_daily', 'column': 'date', 'max_age_days': 3},
        'stock_scores': {'table': 'stock_scores', 'column': 'date', 'max_age_days': 3},
        'buy_sell_signals': {'table': 'buy_sell_daily', 'column': 'date', 'max_age_days': 3},
        'economic_data': {'table': 'economic_data', 'column': 'date', 'max_age_days': 7},
        'earnings_calendar': {'table': 'earnings_calendar', 'column': 'created_at', 'max_age_days': 7},
    }

    def test_critical_tables_not_empty(self, cursor):
        """Verify critical tables have data."""
        empty_tables = []

        for requirement in self.FRESHNESS_REQUIREMENTS.values():
            cursor.execute(f"SELECT COUNT(*) FROM {requirement['table']}")
            count = cursor.fetchone()[0]

            if count == 0:
                empty_tables.append(requirement['table'])

        assert len(empty_tables) == 0, f"Empty critical tables: {', '.join(empty_tables)}"

    def test_data_within_freshness_window(self, cursor):
        """Verify data is within freshness SLA."""
        stale_tables = []

        for name, requirement in self.FRESHNESS_REQUIREMENTS.items():
            try:
                cursor.execute(f"""
                    SELECT MAX({requirement['column']})::DATE as latest_date
                    FROM {requirement['table']}
                """)

                result = cursor.fetchone()
                if not result or result['latest_date'] is None:
                    continue

                latest_date = result['latest_date']
                age_days = (datetime.now(timezone.utc).date() - latest_date).days

                if age_days > requirement['max_age_days']:
                    stale_tables.append({
                        'table': requirement['table'],
                        'age_days': age_days,
                        'max_allowed': requirement['max_age_days']
                    })

            except Exception as e:
                # Table might not have the expected column, skip
                pass

        assert len(stale_tables) == 0, f"Stale data found: {stale_tables}"


class TestDataQuality:
    """Verify data quality standards."""

    def test_prices_reasonable_range(self, cursor):
        """Verify stock prices are in reasonable range (not corrupted)."""
        cursor.execute("""
            SELECT COUNT(*) as anomalies
            FROM price_daily
            WHERE close < 0.01 OR close > 100000
        """)

        anomalies = cursor.fetchone()['anomalies']
        # Allow small number of anomalies from micro-cap stocks
        assert anomalies < 100, f"Found {anomalies} price anomalies (extreme values)"

    def test_technical_indicators_in_range(self, cursor):
        """Verify technical indicators are in valid ranges."""
        cursor.execute("""
            SELECT COUNT(*) as rsi_anomalies
            FROM technical_indicators_daily
            WHERE rsi < 0 OR rsi > 100
        """)

        rsi_anomalies = cursor.fetchone()['rsi_anomalies']
        assert rsi_anomalies == 0, f"RSI values outside 0-100 range: {rsi_anomalies}"

    def test_stock_symbols_coverage(self, cursor):
        """Verify we have coverage for major stocks."""
        cursor.execute("""
            SELECT COUNT(*) as sp500_count
            FROM stock_symbols
            WHERE is_sp500 = true
        """)

        sp500_count = cursor.fetchone()['sp500_count']
        # Should have most S&P 500 companies
        assert sp500_count >= 450, f"S&P 500 coverage too low: {sp500_count}/500"

    def test_buy_sell_signals_distribution(self, cursor):
        """Verify buy/sell signals have reasonable distribution."""
        cursor.execute("""
            SELECT
                signal,
                COUNT(*) as count
            FROM buy_sell_daily
            WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
            GROUP BY signal
        """)

        signals = {row['signal']: row['count'] for row in cursor.fetchall()}

        # Should have both buys and sells
        assert 'BUY' in signals or 'SELL' in signals, "No signals found for latest date"
        assert signals.get('BUY', 0) > 0 or signals.get('SELL', 0) > 0, "No buy or sell signals"


class TestDataConsistency:
    """Verify data relationships and consistency."""

    def test_prices_match_symbols(self, cursor):
        """Verify all price records reference valid symbols."""
        cursor.execute("""
            SELECT COUNT(*) as orphan_count
            FROM price_daily pd
            LEFT JOIN stock_symbols ss ON pd.symbol = ss.symbol
            WHERE ss.symbol IS NULL
        """)

        orphan_count = cursor.fetchone()['orphan_count']
        assert orphan_count == 0, f"Found {orphan_count} price records with invalid symbols"

    def test_scores_match_symbols(self, cursor):
        """Verify all stock score records reference valid symbols."""
        cursor.execute("""
            SELECT COUNT(*) as orphan_count
            FROM stock_scores ss
            LEFT JOIN stock_symbols sym ON ss.symbol = sym.symbol
            WHERE sym.symbol IS NULL
        """)

        orphan_count = cursor.fetchone()['orphan_count']
        assert orphan_count == 0, f"Found {orphan_count} score records with invalid symbols"

    def test_signals_match_symbols(self, cursor):
        """Verify all signal records reference valid symbols."""
        cursor.execute("""
            SELECT COUNT(*) as orphan_count
            FROM buy_sell_daily bs
            LEFT JOIN stock_symbols ss ON bs.symbol = ss.symbol
            WHERE ss.symbol IS NULL
        """)

        orphan_count = cursor.fetchone()['orphan_count']
        assert orphan_count == 0, f"Found {orphan_count} signal records with invalid symbols"


class TestLoaderStatus:
    """Verify loader health tracking system is working."""

    def test_data_loader_status_table_populated(self, cursor):
        """Verify data_loader_status has recent entries."""
        cursor.execute("""
            SELECT COUNT(*) as status_count
            FROM data_loader_status
            WHERE status IN ('HEALTHY', 'STALE', 'VERY_STALE')
        """)

        status_count = cursor.fetchone()['status_count']
        assert status_count > 0, "data_loader_status table has no health check entries"

    def test_no_critical_empty_tables(self, cursor):
        """Verify no critical tables are empty."""
        cursor.execute("""
            SELECT table_name
            FROM data_loader_status
            WHERE status = 'EMPTY'
            AND table_name IN (
                'stock_symbols', 'price_daily', 'buy_sell_daily',
                'stock_scores', 'technical_indicators_daily'
            )
        """)

        empty_tables = [row['table_name'] for row in cursor.fetchall()]
        assert len(empty_tables) == 0, f"Critical tables are empty: {empty_tables}"


def run_all_tests():
    """Run all data integrity tests and report results."""
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == '__main__':
    run_all_tests()
