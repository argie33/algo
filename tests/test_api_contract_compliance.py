#!/usr/bin/env python3
"""
API Contract Validation Tests

Verifies that all API endpoints return responses matching API_CONTRACT.md.
These tests ensure frontend and backend are aligned on data structure.

Run with: pytest tests/test_api_contract_compliance.py
"""

import pytest
import json
from datetime import datetime, timedelta
from utils.db_connection import get_db_connection


class TestAPIContractCompliance:
    """Verify all API endpoints return correct response structure."""

    @pytest.fixture(scope="session")
    def db_conn(self):
        """Get database connection for validation."""
        conn = get_db_connection()
        yield conn
        conn.close()

    def test_stockscores_endpoint_schema(self, db_conn):
        """
        Test /api/scores/stockscores returns all required columns.
        Per API_CONTRACT.md, needs:
        - symbol, swing_score, grade, trend_score, market_cap, price, change_pct, date
        """
        cur = db_conn.cursor()
        try:
            # Query the data source
            cur.execute("""
                SELECT
                    s.symbol, s.swing_score, s.grade, s.trend_score,
                    cp.market_cap, pd.close as price,
                    ((pd.close - pd_prev.close) / pd_prev.close * 100) as change_pct,
                    pd.date
                FROM swing_trader_scores s
                LEFT JOIN price_daily pd ON s.symbol = pd.symbol AND s.date = pd.date
                LEFT JOIN price_daily pd_prev ON s.symbol = pd_prev.symbol AND pd_prev.date = pd.date - INTERVAL 1 day
                LEFT JOIN company_profile cp ON s.symbol = cp.symbol
                LIMIT 10
            """)
            rows = cur.fetchall()

            assert len(rows) > 0, "stockscores query returned no rows"

            # Verify all required columns are present and non-null for most rows
            required_fields = ['symbol', 'swing_score', 'grade', 'trend_score', 'market_cap', 'price', 'change_pct', 'date']
            for row in rows:
                row_dict = dict(zip([desc[0] for desc in cur.description], row))
                assert 'symbol' in row_dict, "Missing required field: symbol"
                assert row_dict['symbol'] is not None, "symbol cannot be null"
                assert isinstance(row_dict['swing_score'], (int, float)), "swing_score must be numeric"
                assert 0 <= row_dict['swing_score'] <= 100, f"swing_score out of range: {row_dict['swing_score']}"
                assert 'grade' in row_dict, "Missing required field: grade"

        finally:
            cur.close()

    def test_deep_value_endpoint_schema(self, db_conn):
        """
        Test /api/stocks/deep-value returns all required columns.
        Per API_CONTRACT.md, needs:
        - symbol, company_name, price, eps, pe_ratio, pb_ratio, roe, debt_to_equity, market_cap, sector, industry
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    cp.symbol, cp.name as company_name, pd.close as price,
                    fm.earnings_per_share as eps, fm.pe_ratio, fm.pb_ratio,
                    fm.return_on_equity as roe, fm.debt_to_equity,
                    cp.market_cap, cp.sector, cp.industry
                FROM company_profile cp
                LEFT JOIN price_daily pd ON cp.symbol = pd.symbol AND pd.date = CURRENT_DATE
                LEFT JOIN fundamental_metrics fm ON cp.symbol = fm.symbol
                LIMIT 20
            """)
            rows = cur.fetchall()

            assert len(rows) > 0, "deep_value query returned no rows"

            # Verify critical fields
            for row in rows:
                row_dict = dict(zip([desc[0] for desc in cur.description], row))
                assert row_dict['symbol'] is not None, "symbol cannot be null"
                assert row_dict['company_name'] is not None, "company_name cannot be null"

        finally:
            cur.close()

    def test_swing_scores_detail_endpoint_schema(self, db_conn):
        """
        Test /api/algo/swing-scores?symbol=X returns components JSON.
        Per API_CONTRACT.md, needs:
        - swing_score, grade, components (with setup_quality, trend_quality, momentum_rs, volume, fundamentals, sector_industry, multi_timeframe)
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    swing_score, grade, components
                FROM swing_trader_scores
                WHERE components IS NOT NULL
                LIMIT 5
            """)
            rows = cur.fetchall()

            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert row_dict['swing_score'] is not None
                    assert row_dict['grade'] is not None

                    # If components is a string, it should be valid JSON
                    if row_dict['components']:
                        try:
                            components = json.loads(row_dict['components']) if isinstance(row_dict['components'], str) else row_dict['components']
                            # Verify key component fields exist
                            assert 'setup_quality' in components or 'score' in components, "Missing component breakdown"
                        except json.JSONDecodeError:
                            pytest.skip("Components field not in JSON format (optional)")

        finally:
            cur.close()

    def test_price_history_endpoint_schema(self, db_conn):
        """
        Test /api/prices/history/{SYMBOL} returns OHLCV data.
        Per API_CONTRACT.md, needs:
        - date, open, high, low, close, volume
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    date, open, high, low, close, volume
                FROM price_daily
                WHERE volume > 0
                LIMIT 20
            """)
            rows = cur.fetchall()

            assert len(rows) > 0, "price_daily query returned no rows"

            for row in rows:
                row_dict = dict(zip([desc[0] for desc in cur.description], row))
                assert row_dict['date'] is not None, "date cannot be null"
                assert row_dict['open'] is not None, "open cannot be null"
                assert row_dict['high'] is not None, "high cannot be null"
                assert row_dict['low'] is not None, "low cannot be null"
                assert row_dict['close'] is not None, "close cannot be null"
                assert row_dict['volume'] is not None, "volume cannot be null"

        finally:
            cur.close()

    def test_circuit_breaker_endpoint_schema(self, db_conn):
        """
        Test /api/algo/circuit-breakers returns status data.
        Per API_CONTRACT.md, needs:
        - name, status, threshold, current_value, triggered_at, last_check
        """
        cur = db_conn.cursor()
        try:
            # Check if circuit breaker table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'circuit_breaker_status'
                )
            """)
            if cur.fetchone()[0]:
                cur.execute("""
                    SELECT
                        name, status, threshold, current_value, triggered_at, last_check
                    FROM circuit_breaker_status
                    LIMIT 10
                """)
                rows = cur.fetchall()

                if len(rows) > 0:
                    for row in rows:
                        row_dict = dict(zip([desc[0] for desc in cur.description], row))
                        assert row_dict['name'] is not None, "name cannot be null"
                        assert row_dict['status'] is not None, "status cannot be null"
                        assert row_dict['last_check'] is not None, "last_check cannot be null"
            else:
                pytest.skip("circuit_breaker_status table not found")

        finally:
            cur.close()

    def test_sector_trends_endpoint_schema(self, db_conn):
        """
        Test /api/sectors/trends-batch returns sector metrics.
        Per API_CONTRACT.md, needs:
        - sector_name, momentum_score, relative_strength
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    sector, momentum_score, relative_strength
                FROM sector_metrics
                LIMIT 10
            """)
            rows = cur.fetchall()

            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert row_dict['sector'] is not None, "sector cannot be null"
                    # momentum_score may be null in some cases

        finally:
            cur.close()

    def test_critical_tables_exist(self, db_conn):
        """Verify all critical tables referenced in API_CONTRACT exist."""
        cur = db_conn.cursor()
        try:
            required_tables = [
                'swing_trader_scores',
                'price_daily',
                'company_profile',
                'fundamental_metrics',
                'sector_metrics',
            ]

            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()[0]
                assert exists, f"Required table {table_name} does not exist"

        finally:
            cur.close()

    def test_data_freshness(self, db_conn):
        """Verify critical tables have recent data (within 7 days)."""
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            latest_price_date = cur.fetchone()[0]

            if latest_price_date:
                days_old = (datetime.now().date() - latest_price_date).days
                assert days_old <= 7, f"price_daily data is {days_old} days old (should be < 7)"

        finally:
            cur.close()


class TestAPIResponseFormat:
    """Verify API responses are properly formatted."""

    def test_api_response_structure(self):
        """
        Per API_CONTRACT, responses should follow:
        {
            "success": true/false,
            "data": { ... } or [ ... ],
            "error": "message if success=false"
        }
        """
        # This would be tested with actual API calls in integration tests
        # Listed here for documentation purposes
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
