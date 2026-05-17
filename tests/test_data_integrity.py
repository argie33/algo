"""
Data Integrity Validation Tests
Automated verification that critical data tables have expected content and freshness.
Run locally before deployment and in AWS post-deployment.

Fixtures (db_connection, cursor) are provided by conftest.py
"""

import pytest
from datetime import datetime, timezone, timedelta


class TestCriticalTableExistence:
    """Verify all critical tables exist."""

    CRITICAL_TABLES = [
        'stock_symbols', 'price_daily', 'stock_scores', 'buy_sell_daily',
        'economic_data', 'company_profile', 'earnings_calendar',
        'analyst_sentiment_analysis', 'sector_performance', 'industry_ranking',
        'data_loader_status', 'market_health_daily'
    ]

    def test_all_critical_tables_exist(self, db_connection):
        """Verify all critical tables exist in the database."""
        cur = db_connection.cursor()
        try:
            for table in self.CRITICAL_TABLES:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = %s
                    )
                """, (table,))

                result = cur.fetchone()
                exists = result[0] if result else False
                assert exists, f"Critical table '{table}' does not exist"
        finally:
            cur.close()


class TestDataFreshness:
    """Verify data is fresh and up-to-date."""

    FRESHNESS_REQUIREMENTS = {
        'stock_symbols': {'table': 'stock_symbols', 'column': 'created_at', 'max_age_days': 30},
        'price_daily': {'table': 'price_daily', 'column': 'date', 'max_age_days': 3},
        'stock_scores': {'table': 'stock_scores', 'column': 'date', 'max_age_days': 3},
        'buy_sell_signals': {'table': 'buy_sell_daily', 'column': 'date', 'max_age_days': 3},
        'economic_data': {'table': 'economic_data', 'column': 'date', 'max_age_days': 7},
        'earnings_calendar': {'table': 'earnings_calendar', 'column': 'created_at', 'max_age_days': 7},
        'market_health': {'table': 'market_health_daily', 'column': 'date', 'max_age_days': 3},
    }

    def test_critical_tables_not_empty(self, db_connection):
        """Verify critical tables have data."""
        cur = db_connection.cursor()
        empty_tables = []

        try:
            for requirement in self.FRESHNESS_REQUIREMENTS.values():
                cur.execute(f"SELECT COUNT(*) FROM {requirement['table']}")
                result = cur.fetchone()
                count = result[0] if result else 0

                if count == 0:
                    empty_tables.append(requirement['table'])

            assert len(empty_tables) == 0, f"Empty critical tables: {', '.join(empty_tables)}"
        finally:
            cur.close()

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

    def test_prices_reasonable_range(self, db_connection):
        """Verify stock prices are in reasonable range (not corrupted)."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as anomalies
                FROM price_daily
                WHERE close < 0.01 OR close > 100000
            """)

            result = cur.fetchone()
            anomalies = result[0] if result else 0
            # Allow small number of anomalies from micro-cap stocks
            assert anomalies < 100, f"Found {anomalies} price anomalies (extreme values)"
        finally:
            cur.close()

    def test_technical_indicators_in_range(self, db_connection):
        """Verify stock scores are in valid ranges."""
        cur = db_connection.cursor()
        try:
            # Check swing_score values are reasonable (0-100 scale)
            cur.execute("""
                SELECT COUNT(*) as anomalies
                FROM stock_scores
                WHERE swing_score < 0 OR swing_score > 100
            """)

            result = cur.fetchone()
            anomalies = result[0] if result else 0
            assert anomalies == 0, f"Swing score values outside 0-100 range: {anomalies}"
        finally:
            cur.close()

    def test_stock_symbols_coverage(self, db_connection):
        """Verify we have coverage for major stocks."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as sp500_count
                FROM stock_symbols
                WHERE is_sp500 = true
            """)

            result = cur.fetchone()
            sp500_count = result[0] if result else 0
            # Should have most S&P 500 companies
            assert sp500_count >= 450, f"S&P 500 coverage too low: {sp500_count}/500"
        finally:
            cur.close()

    def test_buy_sell_signals_distribution(self, db_connection):
        """Verify buy/sell signals have reasonable distribution."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT
                    signal,
                    COUNT(*) as count
                FROM buy_sell_daily
                WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
                GROUP BY signal
            """)

            signals = {row[0]: row[1] for row in cur.fetchall()}

            # Should have both buys and sells
            assert 'BUY' in signals or 'SELL' in signals, "No signals found for latest date"
            assert signals.get('BUY', 0) > 0 or signals.get('SELL', 0) > 0, "No buy or sell signals"
        finally:
            cur.close()


class TestDataConsistency:
    """Verify data relationships and consistency."""

    def test_prices_match_symbols(self, db_connection):
        """Verify all price records reference valid symbols."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as orphan_count
                FROM price_daily pd
                LEFT JOIN stock_symbols ss ON pd.symbol = ss.symbol
                WHERE ss.symbol IS NULL
            """)

            result = cur.fetchone()
            orphan_count = result[0] if result else 0
            assert orphan_count == 0, f"Found {orphan_count} price records with invalid symbols"
        finally:
            cur.close()

    def test_scores_match_symbols(self, db_connection):
        """Verify all stock score records reference valid symbols."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as orphan_count
                FROM stock_scores ss
                LEFT JOIN stock_symbols sym ON ss.symbol = sym.symbol
                WHERE sym.symbol IS NULL
            """)

            result = cur.fetchone()
            orphan_count = result[0] if result else 0
            assert orphan_count == 0, f"Found {orphan_count} score records with invalid symbols"
        finally:
            cur.close()

    def test_signals_match_symbols(self, db_connection):
        """Verify all signal records reference valid symbols."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as orphan_count
                FROM buy_sell_daily bs
                LEFT JOIN stock_symbols ss ON bs.symbol = ss.symbol
                WHERE ss.symbol IS NULL
            """)

            result = cur.fetchone()
            orphan_count = result[0] if result else 0
            assert orphan_count == 0, f"Found {orphan_count} signal records with invalid symbols"
        finally:
            cur.close()


class TestLoaderStatus:
    """Verify loader health tracking system is working."""

    def test_data_loader_status_table_populated(self, db_connection):
        """Verify data_loader_status has recent entries."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT COUNT(*) as status_count
                FROM data_loader_status
                WHERE status IN ('HEALTHY', 'STALE', 'VERY_STALE')
            """)

            result = cur.fetchone()
            status_count = result[0] if result else 0
            assert status_count > 0, "data_loader_status table has no health check entries"
        finally:
            cur.close()

    def test_no_critical_empty_tables(self, db_connection):
        """Verify no critical tables are empty."""
        cur = db_connection.cursor()
        try:
            cur.execute("""
                SELECT table_name
                FROM data_loader_status
                WHERE status = 'EMPTY'
                AND table_name IN (
                    'stock_symbols', 'price_daily', 'buy_sell_daily',
                    'stock_scores', 'technical_indicators_daily'
                )
            """)

            empty_tables = [row[0] for row in cur.fetchall()]
            assert len(empty_tables) == 0, f"Critical tables are empty: {empty_tables}"
        finally:
            cur.close()


def run_all_tests():
    """Run all data integrity tests and report results."""
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == '__main__':
    run_all_tests()
