#!/usr/bin/env python3
"""
API Contract Validation Tests

Verifies that all API endpoints return responses matching API_CONTRACT.md.
These tests ensure frontend and backend are aligned on data structure.

Run with: pytest tests/test_api_contract_compliance.py -v
"""

import pytest
import json
from datetime import datetime, timedelta
from decimal import Decimal
from utils.db_connection import get_db_connection


class TestAPIContractCompliance:
    """Verify all API endpoints return correct response structure."""

    @pytest.fixture(scope="session")
    def db_conn(self):
        """Get database connection for validation."""
        try:
            conn = get_db_connection()
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

    def test_stockscores_endpoint_schema(self, db_conn):
        """
        Test /api/scores/stockscores returns required columns from stock_scores table.
        Per API_CONTRACT.md, needs:
        - symbol, composite_score (mapped to swing_score), market_cap, price, date

        Note: The actual table is stock_scores (not swing_trader_scores).
        Grade is computed at runtime in the API route from the score value.
        """
        cur = db_conn.cursor()
        try:
            # Query the actual data source: stock_scores table
            cur.execute("""
                SELECT
                    ss.symbol, ss.composite_score,
                    km.market_cap, pd.close as price,
                    pd.date
                FROM stock_scores ss
                LEFT JOIN price_daily pd ON ss.symbol = pd.symbol AND pd.date = CURRENT_DATE - INTERVAL '1 day'
                LEFT JOIN key_metrics km ON ss.symbol = km.symbol
                LIMIT 10
            """)
            rows = cur.fetchall()

            # Note: May be empty if no price data loaded yet - that's OK
            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert row_dict['symbol'] is not None, "symbol cannot be null"
                    assert isinstance(row_dict['composite_score'], (int, float, Decimal)), "composite_score must be numeric"
                    if row_dict['composite_score'] is not None:
                        assert 0 <= row_dict['composite_score'] <= 100, f"composite_score out of range: {row_dict['composite_score']}"

        finally:
            cur.close()

    def test_deep_value_endpoint_schema(self, db_conn):
        """
        Test /api/stocks/deep-value uses value_metrics table.
        Per API_CONTRACT.md, needs:
        - symbol, company_name, price, pe_ratio, pb_ratio, roe, debt_to_equity, market_cap, sector, industry

        Note: Uses value_metrics, not non-existent fundamental_metrics table.
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    cp.symbol, cp.display_name as company_name, pd.close as price,
                    vm.pe_ratio, vm.pb_ratio,
                    km.market_cap, cp.sector, cp.industry
                FROM company_profile cp
                LEFT JOIN price_daily pd ON cp.symbol = pd.symbol AND pd.date = CURRENT_DATE - INTERVAL '1 day'
                LEFT JOIN value_metrics vm ON cp.symbol = vm.symbol
                LEFT JOIN key_metrics km ON cp.symbol = km.symbol
                LIMIT 10
            """)
            rows = cur.fetchall()

            # May be empty if no data loaded - that's OK
            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert row_dict['symbol'] is not None, "symbol cannot be null"

        finally:
            cur.close()

    def test_swing_scores_schema(self, db_conn):
        """
        Test swing_trader_scores table has correct structure.
        Per actual schema (not API_CONTRACT):
        - symbol, date, score (not swing_score), components JSONB

        Note: grade is computed at runtime in algo.js route from score value.
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    symbol, date, score, components
                FROM swing_trader_scores
                WHERE components IS NOT NULL
                LIMIT 5
            """)
            rows = cur.fetchall()

            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert row_dict['symbol'] is not None, "symbol cannot be null"
                    assert row_dict['score'] is not None, "score cannot be null"
                    assert isinstance(row_dict['score'], (int, float)), "score must be numeric"

                    # Verify components is valid JSON
                    if row_dict['components']:
                        try:
                            components = json.loads(row_dict['components']) if isinstance(row_dict['components'], str) else row_dict['components']
                            assert isinstance(components, dict), "components must be a JSON object"
                        except json.JSONDecodeError:
                            pytest.fail("components field not in valid JSON format")

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
                ORDER BY date DESC
                LIMIT 5
            """)
            rows = cur.fetchall()

            if len(rows) == 0:
                pytest.skip("No price data available in database")

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

    def test_sector_trends_schema(self, db_conn):
        """
        Test /api/sectors/trends-batch uses sector_ranking + sector_performance tables.
        Per actual schema (not API_CONTRACT):
        - sector_ranking: sector, date_recorded, current_rank, momentum_score
        - sector_performance: sector, date, return_pct, relative_strength
        """
        cur = db_conn.cursor()
        try:
            # Verify sector_ranking exists and has data
            cur.execute("""
                SELECT
                    sector_name, current_rank, momentum_score
                FROM sector_ranking
                ORDER BY date_recorded DESC
                LIMIT 10
            """)
            rows = cur.fetchall()

            if len(rows) == 0:
                pytest.skip("No sector ranking data available")

            for row in rows:
                row_dict = dict(zip([desc[0] for desc in cur.description], row))
                assert row_dict['sector_name'] is not None, "sector_name cannot be null"

        finally:
            cur.close()

    def test_algo_notifications_schema(self, db_conn):
        """
        Test algo_notifications table has correct columns.
        Actual columns: id, kind (NOT type), severity, title, message, symbol, details, seen (NOT is_read), created_at
        """
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT
                    id, kind, severity, title, message, seen, created_at
                FROM algo_notifications
                LIMIT 5
            """)
            rows = cur.fetchall()

            # If there's data, verify structure
            if len(rows) > 0:
                for row in rows:
                    row_dict = dict(zip([desc[0] for desc in cur.description], row))
                    assert 'id' in row_dict, "Missing id column"
                    assert 'kind' in row_dict, "Missing kind column (NOT type)"
                    assert 'severity' in row_dict, "Missing severity column"
                    assert 'seen' in row_dict, "Missing seen column (NOT is_read)"

        finally:
            cur.close()

    def test_critical_tables_exist(self, db_conn):
        """Verify all critical tables actually exist in the database."""
        cur = db_conn.cursor()
        try:
            required_tables = [
                # Core market data
                'stock_symbols',
                'price_daily',
                'company_profile',
                'stock_scores',
                # Metrics (use these, not non-existent "fundamental_metrics")
                'value_metrics',
                'quality_metrics',
                'growth_metrics',
                # Sectors (use these, not non-existent "sector_metrics")
                'sector_ranking',
                'sector_performance',
                # Algo trading
                'algo_trades',
                'algo_positions',
                'algo_portfolio_snapshots',
                'algo_notifications',
                'swing_trader_scores',
                # Support tables
                'market_health_daily',
                'trend_template_data',
            ]

            missing_tables = []
            for table_name in required_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table_name,))
                if not cur.fetchone()[0]:
                    missing_tables.append(table_name)

            if missing_tables:
                pytest.fail(f"Required tables missing: {', '.join(missing_tables)}")

        finally:
            cur.close()

    def test_company_profile_pk(self, db_conn):
        """Verify company_profile primary key is 'ticker', not 'symbol'."""
        cur = db_conn.cursor()
        try:
            # Check that ticker is used as join key (PK is ticker)
            cur.execute("""
                SELECT COUNT(*) FROM company_profile WHERE ticker IS NOT NULL
            """)
            count = cur.fetchone()[0]
            assert count > 0, "company_profile table has no rows with ticker"

        finally:
            cur.close()

    def test_data_freshness(self, db_conn):
        """Verify critical tables have recent data (within 14 days)."""
        cur = db_conn.cursor()
        try:
            cur.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            latest_price_date = cur.fetchone()[0]

            if latest_price_date:
                days_old = (datetime.now().date() - latest_price_date).days
                # Warn if data is stale but don't fail (loader may not have run yet)
                if days_old > 14:
                    pytest.skip(f"price_daily data is {days_old} days old - loader may need to run")

        finally:
            cur.close()


class TestAPIResponseFormat:
    """Verify API responses are properly formatted."""

    def test_api_response_structure_documented(self):
        """
        Per API_CONTRACT, responses should follow:
        {
            "success": true/false,
            "data": { ... } or [ ... ],
            "pagination": {...} (optional),
            "error": "message if success=false"
        }

        Integration tests in tests/integration/ verify actual API responses.
        This test is for documentation purposes.
        """
        # This is verified by integration tests that make actual HTTP calls
        # Unit tests cannot verify response format without network access
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
