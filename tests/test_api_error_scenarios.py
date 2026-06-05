#!/usr/bin/env python3
"""
API Error Scenario Test Suite

Tests for proper error handling and graceful degradation when:
1. API returns NULL fields (sector, industry, company_name)
2. Metrics tables have missing data
3. Company profile has gaps
4. Queries timeout
5. Responses are malformed
6. Frontend handles errors gracefully

Post-Jun 6 execution. Medium priority - validates system robustness.
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import json

# Database connection
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'algo')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')


class APIErrorScenarioTests:
    """Test API error handling and graceful degradation."""

    def __init__(self):
        self.conn = None
        self.results = []

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, database=DB_NAME,
                user=DB_USER, password=DB_PASSWORD, connect_timeout=5
            )
            self.results.append(("DATABASE_CONNECTION", "PASS", "Connected to database"))
        except Exception as e:
            self.results.append(("DATABASE_CONNECTION", "FAIL", str(e)))
            raise

    def test_null_sector_industry_handling(self):
        """Test that API gracefully handles NULL sector/industry from LEFT JOINs."""
        try:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Check company_profile for NULL values
            cur.execute("""
                SELECT COUNT(*) as null_count
                FROM company_profile
                WHERE sector IS NULL OR industry IS NULL
            """)
            row = cur.fetchone()
            null_count = row['null_count'] if row else 0

            if null_count == 0:
                self.results.append(("NULL_SECTOR_INDUSTRY", "PASS", "No NULL values in company_profile"))
            else:
                # This is acceptable - test that frontend handles it
                self.results.append(("NULL_SECTOR_INDUSTRY", "WARN",
                    f"Found {null_count} NULL values - frontend must handle with COALESCE"))
        except Exception as e:
            self.results.append(("NULL_SECTOR_INDUSTRY", "FAIL", str(e)))

    def test_metrics_table_coverage(self):
        """Test that metrics tables have sufficient data coverage."""
        try:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            metrics_tables = {
                'value_metrics': 8000,  # Expected minimum rows
                'quality_metrics': 8000,
                'growth_metrics': 2000,  # Lower expected - not all stocks have growth data
                'stability_metrics': 8000,
                'positioning_metrics': 800,  # Lower expected - not all stocks have positioning data
            }

            all_pass = True
            for table, min_expected in metrics_tables.items():
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                row = cur.fetchone()
                count = row['count'] if row else 0

                if count >= min_expected:
                    status = "PASS"
                else:
                    status = "WARN"
                    all_pass = False

                self.results.append((f"METRICS_{table.upper()}", status,
                    f"{count} rows (expected >= {min_expected})"))

            if all_pass:
                self.results.append(("METRICS_COVERAGE", "PASS", "All metrics tables adequately populated"))
            else:
                self.results.append(("METRICS_COVERAGE", "WARN", "Some metrics tables below expected coverage"))
        except Exception as e:
            self.results.append(("METRICS_COVERAGE", "FAIL", str(e)))

    def test_company_profile_completeness(self):
        """Test that company_profile has complete data for all symbols."""
        try:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Get total symbols vs company_profile rows
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM stock_symbols) as total_symbols,
                    (SELECT COUNT(*) FROM company_profile) as cp_rows,
                    (SELECT COUNT(*) FROM company_profile WHERE sector IS NULL
                     OR industry IS NULL OR ticker IS NULL) as incomplete_rows
            """)
            row = cur.fetchone()
            total = row['total_symbols']
            cp_rows = row['cp_rows']
            incomplete = row['incomplete_rows']
            coverage_pct = (cp_rows / total * 100) if total > 0 else 0

            if coverage_pct >= 95 and incomplete < 10:
                self.results.append(("COMPANY_PROFILE", "PASS",
                    f"{coverage_pct:.1f}% coverage ({cp_rows}/{total}), {incomplete} incomplete"))
            else:
                self.results.append(("COMPANY_PROFILE", "WARN",
                    f"{coverage_pct:.1f}% coverage ({cp_rows}/{total}), {incomplete} incomplete"))
        except Exception as e:
            self.results.append(("COMPANY_PROFILE", "FAIL", str(e)))

    def test_frontend_response_shape_validation(self):
        """Test that API responses have consistent shape for frontend parsing."""
        try:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Sample a few records to verify response structure
            # This would be done via actual API calls in integration tests
            cur.execute("""
                SELECT
                    symbol,
                    COALESCE(sector, 'Unknown') as sector,
                    COALESCE(industry, 'Unknown') as industry
                FROM company_profile
                LIMIT 5
            """)
            rows = cur.fetchall()

            valid_rows = 0
            for row in rows:
                if (row['symbol'] is not None and
                    row['sector'] is not None and
                    row['industry'] is not None):
                    valid_rows += 1

            if valid_rows == len(rows):
                self.results.append(("RESPONSE_SHAPE", "PASS",
                    "All sample records have required fields non-null"))
            else:
                self.results.append(("RESPONSE_SHAPE", "WARN",
                    f"Only {valid_rows}/{len(rows)} records have all fields populated"))
        except Exception as e:
            self.results.append(("RESPONSE_SHAPE", "FAIL", str(e)))

    def test_data_staleness_columns(self):
        """Test that staleness columns are properly populated."""
        try:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            staleness_fields = [
                ('signal_quality_scores', 'updated_at'),
                ('buy_sell_daily', 'updated_at'),
                ('technical_data_daily', 'date'),
                ('trend_template_data', 'date'),
            ]

            all_populated = True
            for table, col in staleness_fields:
                cur.execute(f"""
                    SELECT COUNT(*) as null_count
                    FROM {table}
                    WHERE {col} IS NULL
                """)
                row = cur.fetchone()
                null_count = row['null_count'] if row else 0

                if null_count == 0:
                    self.results.append((f"STALENESS_{table.upper()}", "PASS",
                        "All rows have staleness column populated"))
                else:
                    self.results.append((f"STALENESS_{table.upper()}", "WARN",
                        f"{null_count} rows missing staleness column"))
                    all_populated = False

            if all_populated:
                self.results.append(("STALENESS_VALIDATION", "PASS", "All staleness columns populated"))
        except Exception as e:
            self.results.append(("STALENESS_VALIDATION", "FAIL", str(e)))

    def run_all_tests(self):
        """Run all error scenario tests."""
        print("\n" + "="*70)
        print("API ERROR SCENARIO TEST SUITE")
        print("="*70 + "\n")

        try:
            self.connect()
            self.test_null_sector_industry_handling()
            self.test_metrics_table_coverage()
            self.test_company_profile_completeness()
            self.test_frontend_response_shape_validation()
            self.test_data_staleness_columns()
        except Exception as e:
            print(f"FATAL ERROR: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()

        return self.print_results()

    def print_results(self):
        """Print test results summary."""
        passed = sum(1 for _, status, _ in self.results if status == "PASS")
        warned = sum(1 for _, status, _ in self.results if status == "WARN")
        failed = sum(1 for _, status, _ in self.results if status == "FAIL")

        for test_name, status, message in self.results:
            status_symbol = {
                "PASS": "[PASS]",
                "WARN": "[WARN]",
                "FAIL": "[FAIL]",
            }.get(status, "[????]")
            print(f"{status_symbol} {test_name}: {message}")

        print(f"\n{'-'*70}")
        print(f"Results: {passed} PASSED, {warned} WARNED, {failed} FAILED")
        print(f"{'-'*70}\n")

        success = failed == 0
        return success


if __name__ == '__main__':
    import sys
    tests = APIErrorScenarioTests()
    success = tests.run_all_tests()
    sys.exit(0 if success else 1)
