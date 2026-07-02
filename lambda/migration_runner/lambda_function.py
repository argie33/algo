"""Lambda function to apply pending database migrations to AWS RDS.

This function applies migration 0044 (add quality_score column) which
was marked complete in deployment but never actually applied to the
AWS RDS database.
"""

import json
import psycopg2
import os
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# RDS connection details from environment
RDS_HOST = os.getenv('RDS_HOST', 'algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com')
RDS_PORT = int(os.getenv('RDS_PORT', '5432'))
RDS_DB = os.getenv('RDS_DB', 'algo_prod')
RDS_USER = os.getenv('RDS_USER', 'algo_admin')
RDS_PASSWORD = os.getenv('RDS_PASSWORD')


def lambda_handler(event, context):
    """Apply pending migrations to AWS RDS."""

    if not RDS_PASSWORD:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'RDS_PASSWORD environment variable not set'})
        }

    try:
        logger.info(f"Connecting to RDS at {RDS_HOST}:{RDS_PORT}/{RDS_DB}")

        conn = psycopg2.connect(
            host=RDS_HOST,
            port=RDS_PORT,
            database=RDS_DB,
            user=RDS_USER,
            password=RDS_PASSWORD,
            connect_timeout=10
        )
        conn.autocommit = True
        cur = conn.cursor()

        logger.info("Applying migration 0044 (COMPLETE)...")

        # Migration 0044: Add all 11 missing columns to quality_metrics
        # Original migration was incomplete - only added quality_score + debt_to_assets
        # Missing 9 unavailable_reason columns caused BulkInsertManager to silently drop financial data
        migrations = [
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_margin_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS net_margin_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roe_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roa_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_equity_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS current_ratio_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quick_ratio_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS interest_coverage_unavailable_reason VARCHAR(255);",
            "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets_unavailable_reason VARCHAR(255);",
            "CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);",
        ]

        for migration_sql in migrations:
            logger.info(f"Executing: {migration_sql}")
            cur.execute(migration_sql)

        # Verify all columns were created
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='quality_metrics'
            AND column_name IN (
                'quality_score', 'debt_to_assets',
                'operating_margin_unavailable_reason', 'net_margin_unavailable_reason',
                'roe_unavailable_reason', 'roa_unavailable_reason',
                'debt_to_equity_unavailable_reason', 'current_ratio_unavailable_reason',
                'quick_ratio_unavailable_reason', 'interest_coverage_unavailable_reason',
                'debt_to_assets_unavailable_reason'
            )
            ORDER BY column_name
        """)

        columns = [row[0] for row in cur.fetchall()]
        logger.info(f"Verified columns in quality_metrics: {columns}")
        logger.info(f"Total columns verified: {len(columns)}/11")

        cur.close()
        conn.close()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'message': 'Migration 0044 applied successfully',
                'columns_created': columns,
                'timestamp': datetime.utcnow().isoformat()
            })
        }

    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Database error: {str(e)}'})
        }
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Unexpected error: {str(e)}'})
        }
