#!/usr/bin/env python3
"""
Monitor Phase 2 Execution in Real-Time
Track loader execution, data flow, and performance metrics
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Try to import AWS clients
try:
    import boto3
    HAS_AWS = True
except ImportError:
    HAS_AWS = False
    print("⚠️ boto3 not installed - AWS monitoring unavailable")

# Try to import database client
try:
    import psycopg2
    HAS_DB = True
except ImportError:
    HAS_DB = False
    print("⚠️ psycopg2 not installed - database monitoring unavailable")

class Phase2Monitor:
    def __init__(self):
        self.config = self._load_config()
        self.aws_client = None
        self.db_conn = None

        if HAS_AWS:
            self.aws_client = boto3.client('logs', region_name='us-east-1')
        if HAS_DB:
            self.db_conn = self._connect_db()

    def _load_config(self):
        """Load configuration from environment"""
        return {
            'rds_host': os.getenv('DB_HOST', 'rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com'),
            'rds_user': os.getenv('DB_USER', 'stocks'),
            'rds_password': os.getenv('DB_PASSWORD', ''),
            'rds_db': os.getenv('DB_NAME', 'stocks'),
            'region': 'us-east-1'
        }

    def _connect_db(self):
        """Connect to RDS database"""
        try:
            conn = psycopg2.connect(
                host=self.config['rds_host'],
                user=self.config['rds_user'],
                password=self.config['rds_password'],
                database=self.config['rds_db']
            )
            return conn
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return None

    def monitor_cloudwatch_logs(self):
        """Monitor CloudWatch logs for Phase 2 loaders"""
        if not HAS_AWS:
            print("❌ AWS monitoring not available (boto3 not installed)")
            return

        print("=" * 60)
        print("MONITORING CLOUDWATCH LOGS")
        print("=" * 60)
        print("")

        log_groups = [
            '/ecs/algo-loadsectors',
            '/ecs/algo-loadecondata',
            '/ecs/algo-loadstockscores',
            '/ecs/algo-loadfactormetrics'
        ]

        for log_group in log_groups:
            print(f"\n📋 {log_group}")
            print("-" * 60)

            try:
                # Get log streams
                response = self.aws_client.describe_log_streams(
                    logGroupName=log_group,
                    orderBy='LastEventTime',
                    descending=True,
                    limit=1
                )

                if not response['logStreams']:
                    print("  ⚠️ No log streams found (loader hasn't run yet)")
                    continue

                stream = response['logStreams'][0]
                print(f"  Stream: {stream['logStreamName']}")

                if 'lastEventTimestamp' in stream:
                    last_event = datetime.fromtimestamp(stream['lastEventTimestamp']/1000)
                    print(f"  Last event: {last_event}")

                # Get recent log events
                events = self.aws_client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream['logStreamName'],
                    limit=5
                )

                if events['events']:
                    print(f"  Recent logs:")
                    for event in events['events'][-3:]:
                        msg = event['message'][:80]
                        print(f"    • {msg}")

            except Exception as e:
                print(f"  ❌ Error: {e}")

    def check_data_loaded(self):
        """Check if data has been loaded into RDS"""
        if not HAS_DB or not self.db_conn:
            print("❌ Database monitoring not available")
            return

        print("\n" + "=" * 60)
        print("CHECKING DATA IN RDS")
        print("=" * 60)
        print("")

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

        try:
            cursor = self.db_conn.cursor()

            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                total_rows += count

                status = "✅" if count > 0 else "⚠️"
                print(f"  {status} {table:35s}: {count:>10,} rows")

            cursor.close()

            print(f"\n  📊 TOTAL ROWS (all Phase 2 tables): {total_rows:,}")

            if total_rows == 0:
                print("  ❌ NO DATA LOADED - Check logs for errors")
            elif total_rows < 100000:
                print("  ⚠️ Low row count - loaders may still be running")
            else:
                print("  ✅ Data loading in progress or complete")

        except Exception as e:
            print(f"  ❌ Error: {e}")

    def check_data_quality(self):
        """Check data quality and completeness"""
        if not HAS_DB or not self.db_conn:
            return

        print("\n" + "=" * 60)
        print("DATA QUALITY CHECK")
        print("=" * 60)
        print("")

        try:
            cursor = self.db_conn.cursor()

            # Check for null values
            print("  Checking for null/missing values:")

            cursor.execute("""
                SELECT
                  COUNT(*) as total,
                  SUM(CASE WHEN price IS NULL THEN 1 ELSE 0 END) as null_prices,
                  SUM(CASE WHEN ma_20 IS NULL THEN 1 ELSE 0 END) as null_ma20
                FROM sector_technical_data;
            """)
            row = cursor.fetchone()
            if row and row[0] > 0:
                print(f"    sector_technical_data: {row[0]:,} rows, {row[1]} null prices, {row[2]} null ma20")

            # Check date ranges
            print("\n  Date coverage:")

            cursor.execute("SELECT MIN(date), MAX(date) FROM sector_technical_data;")
            dates = cursor.fetchone()
            if dates[0]:
                print(f"    sector_technical_data: {dates[0]} to {dates[1]}")

            cursor.execute("SELECT MIN(date), MAX(date) FROM economic_data;")
            dates = cursor.fetchone()
            if dates[0]:
                print(f"    economic_data: {dates[0]} to {dates[1]}")

            # Check symbol coverage
            print("\n  Symbol coverage:")

            cursor.execute("SELECT COUNT(DISTINCT symbol) FROM stock_scores;")
            symbols = cursor.fetchone()[0]
            print(f"    stock_scores: {symbols:,} unique symbols")

            cursor.execute("SELECT COUNT(DISTINCT sector) FROM sector_technical_data;")
            sectors = cursor.fetchone()[0]
            print(f"    sectors: {sectors} sectors")

            cursor.close()

        except Exception as e:
            print(f"  ❌ Error: {e}")

    def generate_summary(self):
        """Generate execution summary"""
        print("\n" + "=" * 60)
        print("EXECUTION SUMMARY")
        print("=" * 60)
        print("")

        print("Next steps:")
        print("  1. ✓ GitHub secrets configured")
        print("  2. ✓ AWS OIDC deployed")
        print("  3. ⏳ Phase 2 workflow running (check GitHub Actions)")
        print("  4. ⏳ Data loading (watch CloudWatch logs)")
        print("  5. ⏳ Verify data in database (see above)")
        print("")

        print("Expected:")
        print("  • Total rows: ~150,000+ across all Phase 2 tables")
        print("  • Symbols: ~5,000 stocks")
        print("  • Sectors: 11")
        print("  • Execution time: ~25 minutes")
        print("  • Speedup: 2.1x faster than baseline (53 → 25 min)")
        print("")

def main():
    print("\n🔍 PHASE 2 EXECUTION MONITOR")
    print("=" * 60)
    print(f"Started: {datetime.now()}")
    print("")

    monitor = Phase2Monitor()

    # Run all checks
    monitor.monitor_cloudwatch_logs()
    monitor.check_data_loaded()
    monitor.check_data_quality()
    monitor.generate_summary()

    print("\n" + "=" * 60)
    print("MONITORING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
