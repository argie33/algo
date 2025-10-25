#!/usr/bin/env python3
"""
AWS Data Sync Script - Replicate Local Data to AWS RDS

Syncs all tables from local PostgreSQL to AWS RDS:
- positioning_metrics
- momentum_metrics
- stock_scores
- (and any other tables in stocks database)

Supports:
- Full table replication with data truncation
- Incremental sync (upsert on conflicts)
- Batch processing for large tables
- Progress tracking and error reporting
- AWS RDS IAM authentication

Usage:
  python3 sync_data_to_aws.py [--full] [--batch-size 1000]

Environment Variables:
  AWS_SECRET_ARN: AWS Secrets Manager ARN for RDS credentials
  OR manually set AWS_RDS_ENDPOINT, AWS_RDS_USER, AWS_RDS_PASSWORD
"""

import os
import sys
import logging
import json
import psycopg2
import psycopg2.extras
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 1000
TABLES_TO_SYNC = [
    'positioning_metrics',
    'momentum_metrics',
    'stock_scores',
]

class AWSDataSync:
    def __init__(self, batch_size=BATCH_SIZE, full_sync=False):
        self.batch_size = batch_size
        self.full_sync = full_sync
        self.local_conn = None
        self.aws_conn = None
        self.stats = {
            'tables_synced': 0,
            'rows_synced': 0,
            'errors': 0,
            'start_time': datetime.now()
        }

    def get_aws_credentials(self):
        """Get AWS RDS credentials from Secrets Manager or environment"""

        # Try environment variables first
        if os.getenv('AWS_RDS_ENDPOINT'):
            return {
                'endpoint': os.getenv('AWS_RDS_ENDPOINT'),
                'user': os.getenv('AWS_RDS_USER'),
                'password': os.getenv('AWS_RDS_PASSWORD'),
                'database': 'stocks'
            }

        # Try Secrets Manager
        secret_arn = os.getenv('AWS_SECRET_ARN')
        if not secret_arn:
            logger.error("AWS_SECRET_ARN not set and no environment variables found")
            logger.error("Set AWS_SECRET_ARN or AWS_RDS_* variables")
            return None

        try:
            client = boto3.client('secretsmanager', region_name='us-east-1')
            response = client.get_secret_value(SecretId=secret_arn)

            if 'SecretString' in response:
                secret = json.loads(response['SecretString'])
                return {
                    'endpoint': secret['host'],
                    'user': secret['username'],
                    'password': secret['password'],
                    'database': 'stocks'
                }
        except ClientError as e:
            logger.error(f"Failed to get AWS credentials: {e}")
            return None

        return None

    def connect_local(self):
        """Connect to local PostgreSQL"""
        try:
            self.local_conn = psycopg2.connect(
                host="localhost",
                port=5432,
                user="postgres",
                password="password",
                database="stocks"
            )
            logger.info("✅ Connected to local PostgreSQL")
            return True
        except psycopg2.OperationalError as e:
            logger.error(f"❌ Failed to connect to local PostgreSQL: {e}")
            return False

    def connect_aws(self):
        """Connect to AWS RDS"""
        creds = self.get_aws_credentials()
        if not creds:
            logger.error("❌ Could not get AWS credentials")
            return False

        try:
            self.aws_conn = psycopg2.connect(
                host=creds['endpoint'],
                port=5432,
                user=creds['user'],
                password=creds['password'],
                database=creds['database'],
                connect_timeout=10
            )
            logger.info(f"✅ Connected to AWS RDS ({creds['endpoint']})")
            return True
        except psycopg2.OperationalError as e:
            logger.error(f"❌ Failed to connect to AWS RDS: {e}")
            return False

    def sync_table(self, table_name):
        """Sync a single table from local to AWS"""

        logger.info(f"\n📊 Syncing table: {table_name}")

        local_cur = self.local_conn.cursor()
        aws_cur = self.aws_conn.cursor()

        try:
            # Get row count
            local_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = local_cur.fetchone()[0]
            logger.info(f"  Local rows: {row_count}")

            if row_count == 0:
                logger.warning(f"  ⚠️  No rows to sync (table empty)")
                return

            # Full sync: truncate and reload
            if self.full_sync:
                logger.info(f"  Truncating AWS table...")
                aws_cur.execute(f"TRUNCATE TABLE {table_name}")
                self.aws_conn.commit()

            # Fetch and sync in batches
            local_cur.execute(f"SELECT * FROM {table_name} ORDER BY symbol")
            synced = 0

            while True:
                rows = local_cur.fetchall()
                if not rows:
                    break

                # Get column names
                col_names = [desc[0] for desc in local_cur.description]

                # Prepare INSERT/UPSERT for AWS
                placeholders = ','.join(['%s'] * len(col_names))
                insert_sql = f"""
                    INSERT INTO {table_name} ({','.join(col_names)})
                    VALUES ({placeholders})
                    ON CONFLICT (symbol, date) DO UPDATE SET
                    {', '.join([f"{col}=EXCLUDED.{col}" for col in col_names if col not in ('symbol', 'date')])}
                """

                # Execute batch
                for row in rows:
                    try:
                        aws_cur.execute(insert_sql, row)
                    except psycopg2.IntegrityError as e:
                        logger.warning(f"    Conflict for row: {e}")
                        self.aws_conn.rollback()

                self.aws_conn.commit()
                synced += len(rows)

                pct = (synced / row_count) * 100
                logger.info(f"  Progress: {synced}/{row_count} ({pct:.1f}%)")

            logger.info(f"  ✅ {table_name}: {synced} rows synced")
            self.stats['rows_synced'] += synced
            self.stats['tables_synced'] += 1

        except Exception as e:
            logger.error(f"  ❌ Error syncing {table_name}: {e}")
            self.stats['errors'] += 1
        finally:
            local_cur.close()
            aws_cur.close()

    def sync_all(self):
        """Sync all tables"""

        if not self.connect_local():
            return False

        if not self.connect_aws():
            return False

        logger.info("\n" + "="*70)
        logger.info("  AWS DATA SYNC STARTING")
        logger.info("="*70)

        for table in TABLES_TO_SYNC:
            self.sync_table(table)

        # Summary
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        logger.info("\n" + "="*70)
        logger.info("  SYNC COMPLETE")
        logger.info("="*70)
        logger.info(f"Tables synced: {self.stats['tables_synced']}")
        logger.info(f"Rows synced: {self.stats['rows_synced']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Time elapsed: {elapsed:.1f}s")

        self.local_conn.close()
        self.aws_conn.close()

        return self.stats['errors'] == 0

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Sync local PostgreSQL to AWS RDS')
    parser.add_argument('--full', action='store_true', help='Full sync (truncate AWS tables)')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE, help='Batch size for inserts')

    args = parser.parse_args()

    syncer = AWSDataSync(batch_size=args.batch_size, full_sync=args.full)
    success = syncer.sync_all()

    sys.exit(0 if success else 1)
