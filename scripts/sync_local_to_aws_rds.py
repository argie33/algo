#!/usr/bin/env python3
"""
Sync fresh data from local development database to AWS RDS.

TEMPORARY WORKAROUND while Terraform apply is blocked by IAM permission issues.
This script copies critical tables with fresh data from local DB to AWS RDS.

Usage:
    python3 scripts/sync_local_to_aws_rds.py --source localhost --target algo-db.xxxxx.rds.amazonaws.com
    python3 scripts/sync_local_to_aws_rds.py --help
"""

import argparse
import logging
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')

# Critical tables to sync (latest data from local DB)
CRITICAL_TABLES = [
    "stock_scores",
    "algo_trades",
    "algo_portfolio_snapshots",
    "algo_orchestrator_runs",
    "technical_data_daily",
    "price_daily",
    "buy_sell_daily",
]

OPTIONAL_TABLES = [
    "growth_metrics",
    "quality_metrics",
    "stability_metrics",
    "positioning_metrics",
    "value_metrics",
    "momentum_metrics",
    "market_exposure_daily",
]


def get_connection(host: str, user: str = "stocks", password: str = "stocks", db: str = "stocks") -> psycopg2.extensions.connection:
    """Get database connection."""
    try:
        conn = psycopg2.connect(
            host=host,
            port=5432,
            user=user,
            password=password,
            database=db,
            connect_timeout=10,
        )
        return conn
    except psycopg2.OperationalError as e:
        raise RuntimeError(f"Failed to connect to {host}: {e}")


def sync_table(src_conn: psycopg2.extensions.connection, tgt_conn: psycopg2.extensions.connection, table: str) -> bool:
    """Sync a single table from source to target.

    Returns: True if successful, False if failed.
    """
    try:
        src_cur = src_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        tgt_cur = tgt_conn.cursor()

        # Count records
        src_cur.execute(f"SELECT COUNT(*) FROM {table}")
        src_count = src_cur.fetchone()[0]

        tgt_cur.execute(f"SELECT COUNT(*) FROM {table}")
        tgt_count = tgt_cur.fetchone()[0]

        logger.info(f"{table}: {src_count} records (source) vs {tgt_count} (target)")

        if src_count == 0:
            logger.warning(f"  Skipping: source table is empty!")
            return False

        # If target has data, compare latest timestamps
        src_cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='{table}' AND column_name IN ('created_at', 'updated_at')
            LIMIT 1
        """)
        timestamp_col = src_cur.fetchone()
        if timestamp_col:
            timestamp_col = timestamp_col[0]
            src_cur.execute(f"SELECT MAX({timestamp_col}) FROM {table}")
            src_latest = src_cur.fetchone()[0]
            tgt_cur.execute(f"SELECT MAX({timestamp_col}) FROM {table}")
            tgt_latest = tgt_cur.fetchone()[0]
            logger.info(f"  Source latest: {src_latest}, Target latest: {tgt_latest}")

            if tgt_latest and src_latest and src_latest <= tgt_latest:
                logger.info(f"  Target is already fresh, skipping full sync")
                src_cur.close()
                tgt_cur.close()
                return True

        # Full table sync: truncate + copy
        logger.info(f"  Syncing {src_count} records...")

        # Get all data from source
        src_cur.execute(f"SELECT * FROM {table}")
        rows = src_cur.fetchall()

        if not rows:
            logger.warning(f"  No rows to copy!")
            src_cur.close()
            tgt_cur.close()
            return False

        # Get column names
        col_names = [desc[0] for desc in src_cur.description]

        # Truncate target
        tgt_cur.execute(f"TRUNCATE TABLE {table}")

        # Copy data
        for row in rows:
            placeholders = ','.join(['%s'] * len(col_names))
            insert_sql = f"INSERT INTO {table} ({','.join(col_names)}) VALUES ({placeholders})"
            try:
                tgt_cur.execute(insert_sql, tuple(row.values() if isinstance(row, dict) else row))
            except Exception as e:
                logger.error(f"    Failed to insert row: {e}")
                tgt_conn.rollback()
                return False

        tgt_conn.commit()
        tgt_cur.execute(f"SELECT COUNT(*) FROM {table}")
        new_count = tgt_cur.fetchone()[0]
        logger.info(f"  Success: {new_count} records synced")

        src_cur.close()
        tgt_cur.close()
        return True

    except Exception as e:
        logger.error(f"  FAILED: {type(e).__name__}: {e}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync fresh data from local DB to AWS RDS (temporary workaround)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync to default AWS endpoint
  python3 scripts/sync_local_to_aws_rds.py

  # Sync to custom AWS endpoint
  python3 scripts/sync_local_to_aws_rds.py --target my-rds-endpoint.rds.amazonaws.com

  # Dry run (just show what would be synced)
  python3 scripts/sync_local_to_aws_rds.py --dry-run
        """,
    )
    parser.add_argument("--source", default="localhost", help="Source database host (default: localhost)")
    parser.add_argument("--target", default="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com", help="Target database host")
    parser.add_argument("--source-user", default="stocks", help="Source database user")
    parser.add_argument("--source-pass", default="stocks", help="Source database password")
    parser.add_argument("--target-user", default="stocks", help="Target database user")
    parser.add_argument("--target-pass", required=False, help="Target database password (will prompt if not provided)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without making changes")
    parser.add_argument("--tables", nargs="+", help="Override list of tables to sync")

    args = parser.parse_args()

    if not args.target_pass:
        import getpass
        args.target_pass = getpass.getpass(f"Password for {args.target_user}@{args.target}: ")

    # Get connections
    logger.info(f"Connecting to source: {args.source}")
    src_conn = get_connection(args.source, args.source_user, args.source_pass)

    logger.info(f"Connecting to target: {args.target}")
    tgt_conn = get_connection(args.target, args.target_user, args.target_pass)

    try:
        # Determine tables to sync
        tables = args.tables or (CRITICAL_TABLES + OPTIONAL_TABLES)

        logger.info(f"\n{'='*60}")
        logger.info(f"SYNCING {len(tables)} TABLES")
        logger.info(f"{'='*60}\n")

        successful = 0
        failed = 0

        for table in tables:
            try:
                # Check if table exists
                src_cur = src_conn.cursor()
                src_cur.execute(f"""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name='{table}'
                    )
                """)
                exists = src_cur.fetchone()[0]
                src_cur.close()

                if not exists:
                    logger.warning(f"{table}: Table does not exist in source, skipping")
                    continue

                if args.dry_run:
                    logger.info(f"{table}: Would be synced (dry run)")
                    successful += 1
                else:
                    if sync_table(src_conn, tgt_conn, table):
                        successful += 1
                    else:
                        failed += 1
            except Exception as e:
                logger.error(f"{table}: {type(e).__name__}: {e}")
                failed += 1

        logger.info(f"\n{'='*60}")
        logger.info(f"RESULTS: {successful} successful, {failed} failed")
        logger.info(f"{'='*60}\n")

        if args.dry_run:
            logger.info("Dry run complete. No changes made.")
            return 0

        if failed > 0:
            logger.warning(f"Some tables failed to sync. Check errors above.")
            return 1

        logger.info("All critical data synced successfully!")
        logger.info("Dashboard should now show fresh data from AWS API.")
        return 0

    finally:
        src_conn.close()
        tgt_conn.close()


if __name__ == "__main__":
    sys.exit(main())
