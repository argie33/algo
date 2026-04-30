#!/usr/bin/env python3
"""
Comprehensive Data Validation & Issue Detection
Find data problems, missing data, and validate query results
"""

import os
import sys
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 required. Install: pip install psycopg2-binary")
    sys.exit(1)

class DataValidator:
    def __init__(self):
        self.config = {
            'host': os.getenv('DB_HOST', 'rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com'),
            'user': os.getenv('DB_USER', 'stocks'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'stocks'),
            'port': 5432
        }
        self.conn = None
        self.issues = []

    def connect(self):
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(**self.config)
            print("✅ Database connected")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from database"""
        if self.conn:
            self.conn.close()

    def run_query(self, query):
        """Execute query and return results"""
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return results
        except Exception as e:
            print(f"❌ Query error: {e}")
            return []

    def check_table_exists(self, table):
        """Check if table exists"""
        query = f"""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_name = '{table}'
            );
        """
        result = self.run_query(query)
        return result[0]['exists'] if result else False

    def validate_phase2_tables(self):
        """Validate all Phase 2 tables exist and have data"""
        print("\n" + "=" * 70)
        print("PHASE 2 TABLE VALIDATION")
        print("=" * 70)

        tables = [
            'sector_technical_data',
            'economic_data',
            'stock_scores',
            'quality_metrics',
            'growth_metrics',
            'momentum_metrics',
            'stability_metrics',
            'value_metrics',
            'positioning_metrics'
        ]

        total_rows = 0
        missing_tables = []

        for table in tables:
            if not self.check_table_exists(table):
                print(f"  ❌ Table missing: {table}")
                missing_tables.append(table)
                continue

            result = self.run_query(f"SELECT COUNT(*) as count FROM {table};")
            count = result[0]['count'] if result else 0
            total_rows += count

            if count == 0:
                print(f"  ⚠️  Empty: {table:40s} (0 rows)")
                self.issues.append(f"Table {table} is empty")
            elif count < 1000:
                print(f"  ⚠️  Small: {table:40s} ({count:,} rows)")
                self.issues.append(f"Table {table} has only {count} rows (expected 10k+)")
            else:
                print(f"  ✅ OK:    {table:40s} ({count:,} rows)")

        print(f"\n  📊 TOTAL: {total_rows:,} rows across Phase 2 tables")

        if missing_tables:
            print(f"\n  ❌ Missing tables: {', '.join(missing_tables)}")
            self.issues.append(f"Missing tables: {missing_tables}")

        return total_rows > 0 and len(missing_tables) == 0

    def check_data_quality(self):
        """Check data quality and completeness"""
        print("\n" + "=" * 70)
        print("DATA QUALITY ANALYSIS")
        print("=" * 70)

        # Check for nulls
        print("\n  Null values (should be minimal):")

        queries = {
            'sector_technical_data': """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END) as null_price,
                  SUM(CASE WHEN ma_20 IS NULL THEN 1 ELSE 0 END) as null_ma20,
                  SUM(CASE WHEN rsi IS NULL THEN 1 ELSE 0 END) as null_rsi
                FROM sector_technical_data;
            """,
            'stock_scores': """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN score IS NULL THEN 1 ELSE 0 END) as null_score
                FROM stock_scores;
            """,
            'quality_metrics': """
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN roe IS NULL THEN 1 ELSE 0 END) as null_roe,
                  SUM(CASE WHEN roa IS NULL THEN 1 ELSE 0 END) as null_roa
                FROM quality_metrics;
            """
        }

        for table, query in queries.items():
            result = self.run_query(query)
            if result:
                row = result[0]
                print(f"    {table}:")
                for key, val in row.items():
                    if key != 'total' and val:
                        print(f"      • {key}: {val} nulls out of {row['total']} rows")

        # Check date ranges
        print("\n  Date coverage:")

        date_queries = {
            'sector_technical_data': 'SELECT MIN(date) as min_date, MAX(date) as max_date FROM sector_technical_data;',
            'economic_data': 'SELECT MIN(date) as min_date, MAX(date) as max_date FROM economic_data;',
            'stock_scores': 'SELECT MIN(date) as min_date, MAX(date) as max_date FROM stock_scores;',
        }

        for table, query in date_queries.items():
            result = self.run_query(query)
            if result and result[0]['min_date']:
                min_d = result[0]['min_date']
                max_d = result[0]['max_date']
                print(f"    {table:30s}: {min_d} to {max_d}")

        # Check symbol coverage
        print("\n  Symbol/sector coverage:")

        coverage_queries = {
            'Unique stocks (stock_scores)': 'SELECT COUNT(DISTINCT symbol) FROM stock_scores;',
            'Unique sectors': 'SELECT COUNT(DISTINCT sector) FROM sector_technical_data;',
            'Unique FRED series': 'SELECT COUNT(DISTINCT series_id) FROM economic_data;',
        }

        for label, query in coverage_queries.items():
            result = self.run_query(query)
            if result:
                count = result[0][list(result[0].keys())[0]]
                print(f"    {label:40s}: {count:,}")

    def check_query_results(self):
        """Verify key queries return expected results"""
        print("\n" + "=" * 70)
        print("SAMPLE QUERY VALIDATION")
        print("=" * 70)

        sample_queries = {
            'Sectors with data': """
                SELECT DISTINCT sector FROM sector_technical_data
                ORDER BY sector LIMIT 5;
            """,
            'Recent economic data': """
                SELECT DISTINCT series_id FROM economic_data
                ORDER BY date DESC LIMIT 3;
            """,
            'Top 5 stocks by score': """
                SELECT symbol, MAX(score) as max_score
                FROM stock_scores GROUP BY symbol
                ORDER BY max_score DESC LIMIT 5;
            """,
            'Metrics with highest ROE': """
                SELECT symbol, MAX(roe) as max_roe
                FROM quality_metrics WHERE roe IS NOT NULL
                GROUP BY symbol ORDER BY max_roe DESC LIMIT 3;
            """,
        }

        for label, query in sample_queries.items():
            print(f"\n  {label}:")
            result = self.run_query(query)
            if result:
                for row in result[:3]:
                    print(f"    • {dict(row)}")
            else:
                print(f"    ⚠️  No results")
                self.issues.append(f"Query '{label}' returned no results")

    def generate_report(self):
        """Generate final validation report"""
        print("\n" + "=" * 70)
        print("VALIDATION REPORT")
        print("=" * 70)

        if not self.issues:
            print("\n  ✅ ALL VALIDATION CHECKS PASSED")
            print("\n  Data status:")
            print("    • All Phase 2 tables exist")
            print("    • Data is loaded and accessible")
            print("    • Queries returning expected results")
            print("    • No data quality issues detected")
        else:
            print(f"\n  ⚠️  {len(self.issues)} ISSUE(S) DETECTED:")
            for i, issue in enumerate(self.issues, 1):
                print(f"    {i}. {issue}")

        print("\n  Next steps:")
        print("    1. Review CloudWatch logs for loader errors")
        print("    2. Check if Phase 2 loaders are still running")
        print("    3. Verify AWS infrastructure is deployed")
        print("    4. Ensure RDS database credentials are correct")

def main():
    print("\n" + "=" * 70)
    print("🔍 COMPREHENSIVE DATA VALIDATION")
    print("=" * 70)
    print(f"Started: {datetime.now()}\n")

    validator = DataValidator()

    if not validator.connect():
        sys.exit(1)

    try:
        validator.validate_phase2_tables()
        validator.check_data_quality()
        validator.check_query_results()
        validator.generate_report()
    finally:
        validator.disconnect()

    print("\n" + "=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
