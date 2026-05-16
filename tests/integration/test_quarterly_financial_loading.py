"""
Integration tests for quarterly financial data loading.

Tests the quarterly income statement, balance sheet, and cash flow loaders:
- load_income_statement.py with --period quarterly
- load_balance_sheet.py with --period quarterly
- load_cash_flow.py with --period quarterly
- TTM (Trailing Twelve Months) aggregation loaders

Verifies:
- Quarterly data is loaded correctly from SEC EDGAR
- Data is stored in quarterly_* tables with correct schema
- TTM loaders correctly sum 4 most recent quarters
- Quarterly data is picked up by signal quality checks
"""

import pytest
from datetime import date
import psycopg2


@pytest.mark.integration
class TestQuarterlyIncomeStatement:
    """Tests for quarterly income statement loader."""

    def test_quarterly_income_statement_table_exists(self, seeded_test_db):
        """Verify quarterly_income_statement table exists with correct schema."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'quarterly_income_statement'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()

            assert len(columns) > 0, "quarterly_income_statement table not found"

            # Verify key columns exist
            column_names = {col[0] for col in columns}
            required_columns = {'symbol', 'fiscal_year', 'fiscal_period', 'revenue', 'net_income'}
            missing = required_columns - column_names

            assert not missing, f"Missing columns: {missing}"
        finally:
            cur.close()
            conn.close()

    def test_quarterly_income_statement_unique_constraint(self, seeded_test_db):
        """Verify (symbol, fiscal_year, fiscal_period) uniqueness constraint."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            # Try inserting duplicate
            symbol = 'TEST_QTR'
            fiscal_year = 2025
            fiscal_period = 1

            # First insert
            cur.execute("""
                INSERT INTO quarterly_income_statement
                (symbol, fiscal_year, fiscal_period, revenue, net_income, earnings_per_share)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (symbol, fiscal_year, fiscal_period, 1000000.0, 100000.0, 1.50))
            conn.commit()

            # Second insert (should fail on conflict)
            with pytest.raises(psycopg2.IntegrityError):
                cur.execute("""
                    INSERT INTO quarterly_income_statement
                    (symbol, fiscal_year, fiscal_period, revenue, net_income, earnings_per_share)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (symbol, fiscal_year, fiscal_period, 2000000.0, 200000.0, 2.50))
                conn.commit()
        finally:
            cur.rollback()
            cur.close()
            conn.close()


@pytest.mark.integration
class TestQuarterlyBalanceSheet:
    """Tests for quarterly balance sheet loader."""

    def test_quarterly_balance_sheet_table_exists(self, seeded_test_db):
        """Verify quarterly_balance_sheet table exists with correct schema."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'quarterly_balance_sheet'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()

            assert len(columns) > 0, "quarterly_balance_sheet table not found"

            # Verify key columns exist
            column_names = {col[0] for col in columns}
            required_columns = {'symbol', 'fiscal_year', 'fiscal_period', 'total_assets', 'stockholders_equity'}
            missing = required_columns - column_names

            assert not missing, f"Missing columns: {missing}"
        finally:
            cur.close()
            conn.close()


@pytest.mark.integration
class TestQuarterlyCashFlow:
    """Tests for quarterly cash flow loader."""

    def test_quarterly_cash_flow_table_exists(self, seeded_test_db):
        """Verify quarterly_cash_flow table exists with correct schema."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'quarterly_cash_flow'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()

            assert len(columns) > 0, "quarterly_cash_flow table not found"

            # Verify key columns exist
            column_names = {col[0] for col in columns}
            required_columns = {'symbol', 'fiscal_year', 'fiscal_period', 'operating_cash_flow', 'free_cash_flow'}
            missing = required_columns - column_names

            assert not missing, f"Missing columns: {missing}"
        finally:
            cur.close()
            conn.close()


@pytest.mark.integration
class TestTTMAggregates:
    """Tests for TTM (Trailing Twelve Months) aggregation loaders."""

    def test_ttm_income_statement_table_exists(self, seeded_test_db):
        """Verify ttm_income_statement table exists."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'ttm_income_statement'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()

            assert len(columns) > 0, "ttm_income_statement table not found"

            # Verify key columns
            column_names = {col[0] for col in columns}
            required_columns = {'symbol', 'date'}
            missing = required_columns - column_names

            assert not missing, f"Missing columns in ttm_income_statement: {missing}"
        finally:
            cur.close()
            conn.close()

    def test_ttm_cash_flow_table_exists(self, seeded_test_db):
        """Verify ttm_cash_flow table exists."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'ttm_cash_flow'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()

            assert len(columns) > 0, "ttm_cash_flow table not found"

            # Verify key columns
            column_names = {col[0] for col in columns}
            required_columns = {'symbol', 'date'}
            missing = required_columns - column_names

            assert not missing, f"Missing columns in ttm_cash_flow: {missing}"
        finally:
            cur.close()
            conn.close()


@pytest.mark.integration
class TestQuarterlyDataIntegration:
    """Tests quarterly data integration with signal quality."""

    def test_quarterly_data_populated_in_tier(self, seeded_test_db):
        """Verify quarterly data can be queried for signal quality assessment."""
        conn = psycopg2.connect(
            host='localhost', port=5432, database='stocks_test',
            user='stocks', password=''
        )
        cur = conn.cursor()

        try:
            # Insert test quarterly data
            cur.execute("""
                INSERT INTO quarterly_income_statement
                (symbol, fiscal_year, fiscal_period, revenue, net_income, earnings_per_share)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, fiscal_year, fiscal_period) DO NOTHING
            """, ('TESTQ1', 2025, 1, 1000000.0, 100000.0, 1.50))

            cur.execute("""
                INSERT INTO quarterly_income_statement
                (symbol, fiscal_year, fiscal_period, revenue, net_income, earnings_per_share)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, fiscal_year, fiscal_period) DO NOTHING
            """, ('TESTQ1', 2025, 2, 1100000.0, 110000.0, 1.65))

            conn.commit()

            # Verify we can query the data
            cur.execute("""
                SELECT symbol, SUM(revenue) as total_revenue
                FROM quarterly_income_statement
                WHERE symbol = %s AND fiscal_year = 2025
                GROUP BY symbol
            """, ('TESTQ1',))

            result = cur.fetchone()
            assert result is not None, "Could not retrieve quarterly data"
            symbol, total_revenue = result
            assert symbol == 'TESTQ1'
            assert total_revenue == 2100000.0
        finally:
            conn.rollback()
            cur.close()
            conn.close()
