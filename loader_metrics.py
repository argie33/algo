#!/usr/bin/env python3
"""Helper module for logging loader execution metrics"""

import psycopg2
from db_helper import DatabaseHelper
import os
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from credential_helper import get_db_password, get_db_config
try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

load_dotenv('.env.local')

logger = logging.getLogger(__name__)
credential_manager = get_credential_manager()


def log_execution_start(loader_name: str) -> dict:
    """Log the start of a loader execution and return start_time dict"""
    return {
        'loader_name': loader_name,
        'start_time': datetime.now(),
        'start_timestamp': datetime.now().isoformat()
    }


def log_execution_complete(
    loader_name: str,
    start_time: datetime,
    rows_inserted: int,
    symbols_processed: int,
    rows_skipped: int = 0,
    symbols_failed: int = 0,
    worker_count: int = 1,
    status: str = 'completed',
    error_message: Optional[str] = None,
    aws_region: Optional[str] = None,
    ecs_task_id: Optional[str] = None,
    git_commit: Optional[str] = None
) -> bool:
    """Log execution metrics to database"""

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            user=os.getenv('DB_USER', 'stocks'),
            password=get_db_password(),
            dbname=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=10
        )
        conn.autocommit = True
        cur = conn.cursor()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Calculate speedup assuming 60 minute baseline
        baseline_seconds = 3600  # 1 hour
        speedup = baseline_seconds / duration if duration > 0 else 0

        # Log the execution
        cur.execute('''
            INSERT INTO loader_execution_metrics
            (loader_name, start_time, end_time, duration_seconds,
             rows_inserted, rows_skipped, symbols_processed, symbols_failed,
             worker_count, speedup_vs_baseline, status, error_message,
             aws_region, ecs_task_id, git_commit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            loader_name, start_time, end_time, duration,
            rows_inserted, rows_skipped, symbols_processed, symbols_failed,
            worker_count, speedup, status, error_message,
            aws_region, ecs_task_id, git_commit
        ))

        logger.info(f"[METRICS] {loader_name}: {rows_inserted} rows in {duration:.1f}s ({speedup:.1f}x speedup)")

        # Publish duration to CloudWatch (non-blocking — DB insert already succeeded above)
        try:
            from algo_metrics import MetricsPublisher
            m = MetricsPublisher()
            m.put_loader_duration(loader_name, duration)
            m.flush()
        except Exception:
            pass

        return True

    except Exception as e:
        logger.error(f"[METRICS ERROR] Failed to log execution: {e}")
        return False
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_recent_performance(loader_name: str, limit: int = 10) -> list:
    """Get recent performance data for a loader"""

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            user=os.getenv('DB_USER', 'stocks'),
            password=get_db_password(),
            dbname=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=10
        )
        cur = conn.cursor()

        cur.execute('''
            SELECT
              id, start_time, duration_seconds, rows_inserted,
              speedup_vs_baseline, status, error_message
            FROM loader_execution_metrics
            WHERE loader_name = %s
            ORDER BY start_time DESC
            LIMIT %s
        ''', (loader_name, limit))

        results = cur.fetchall()
        return results

    except Exception as e:
        logger.error(f"[METRICS ERROR] Failed to fetch performance data: {e}")
        return []
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def print_performance_summary():
    """Print summary of all loader performance"""

    conn = None
    cur = None
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            user=os.getenv('DB_USER', 'stocks'),
            password=get_db_password(),
            dbname=os.getenv('DB_NAME', 'stocks'),
            connect_timeout=10
        )
        cur = conn.cursor()

        cur.execute('''
            SELECT * FROM loader_performance_summary
        ''')

        logger.info('\n' + '=' * 100)
        logger.info('LOADER PERFORMANCE SUMMARY (last 30 days)')
        logger.info('=' * 100)
        logger.info(f'{"Loader":<40} {"Runs":>6} {"Success":>8} {"Avg Dur":>10} {"Max Rows":>12} {"Speedup":>8}')
        logger.info('-' * 100)

        for row in cur.fetchall():
            loader_name, total_runs, successful, failed, avg_dur, max_rows, speedup, last_run = row
            avg_dur_str = f"{avg_dur:.1f}s" if avg_dur else "N/A"
            max_rows_str = f"{max_rows:,}" if max_rows else "N/A"
            speedup_str = f"{speedup:.1f}x" if speedup else "N/A"

            logger.info(f'{loader_name:<40} {total_runs:>6} {successful:>8} {avg_dur_str:>10} {max_rows_str:>12} {speedup_str:>8}')

        logger.info('=' * 100 + '\n')

    except Exception as e:
        logger.error(f"[METRICS ERROR] Failed to print summary: {e}")
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    # Test the metrics logging
    logger.info("Testing metrics logging...")

    start_time = datetime.now()

    # Simulate a loader run
    success = log_execution_complete(
        loader_name='test_loader',
        start_time=start_time,
        rows_inserted=1000,
        symbols_processed=100,
        worker_count=5,
        status='completed'
    )

    if success:
        logger.info("[OK] Metrics logged successfully")

        # Print summary
        print_performance_summary()
    else:
        logger.error("[ERROR] Failed to log metrics")
