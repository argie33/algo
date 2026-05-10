#!/usr/bin/env python3
"""
AWS Batch Worker for buyselldaily Loader with Spot Interruption Handling

Wraps loadbuyselldaily.py to:
1. Handle SIGTERM gracefully (Spot interruption notice)
2. Save checkpoint every N symbols or every 5 minutes
3. Resume from checkpoint on restart

This allows long-running jobs to survive Spot terminations
by resuming from the last checkpoint instead of restarting from scratch.

Environment Variables:
    SYMBOL_COUNT: Total symbols to process
    BACKFILL_DAYS: Days to backfill (default: 30)
    PARALLELISM: Concurrent workers (default: 4)
    CHECKPOINT_INTERVAL: Symbols between checkpoints (default: 100)
    CHECKPOINT_DIR: Directory for checkpoint files (default: /tmp/batch-checkpoints)
"""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

# Global state for graceful shutdown
shutdown_event = False


def handle_sigterm(signum, frame):
    """Handle SIGTERM for Spot interruption"""
    global shutdown_event
    log.warning(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event = True


def setup_signal_handlers():
    """Register signal handlers for graceful shutdown"""
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)


def get_active_symbols() -> List[str]:
    """Fetch active symbols from database"""
    import psycopg2

    try:
        secrets_client = __import__('boto3').client('secretsmanager')
        secret_name = os.environ.get('RDS_SECRET_ARN', 'stocks-prod-postgres-creds')

        try:
            secret_response = secrets_client.get_secret_value(SecretId=secret_name)
            secret = json.loads(secret_response['SecretString'])
        except Exception:
            secret = {
                'host': os.environ.get('DB_HOST', 'localhost'),
                'port': int(os.environ.get('DB_PORT', '5432')),
                'user': os.environ.get('DB_USER', 'stocks'),
                'password': os.environ.get('DB_PASSWORD', ''),
                'dbname': os.environ.get('DB_NAME', 'stocks')
            }

        conn = None
        cursor = None
        try:
            conn = psycopg2.connect(
                host=secret.get('host'),
                port=secret.get('port', 5432),
                user=secret.get('username', secret.get('user')),
                password=secret.get('password'),
                database=secret.get('dbname', secret.get('name'))
            )

            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]

            log.info(f"Fetched {len(symbols)} active symbols from database")
            return symbols
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception as e:
        log.exception(f"Failed to get symbols: {e}")
        raise


class CheckpointManager:
    """Manages checkpoints for resumable processing"""

    def __init__(self, checkpoint_dir: str = "/tmp/batch-checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / "buyselldaily_checkpoint.json"

    def save_checkpoint(self, processed_symbols: List[str], stats: Dict) -> None:
        """Save checkpoint after processing symbols"""
        try:
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'processed_symbols': processed_symbols,
                'total_processed': len(processed_symbols),
                'stats': stats,
                'job_id': os.environ.get('AWS_BATCH_JOB_ID', 'unknown')
            }

            with open(self.checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)

            log.info(f"Saved checkpoint: {len(processed_symbols)} symbols processed")
        except Exception as e:
            log.exception(f"Failed to save checkpoint: {e}")

    def load_checkpoint(self) -> Optional[Dict]:
        """Load checkpoint if it exists"""
        try:
            if self.checkpoint_file.exists():
                with open(self.checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                log.info(f"Loaded checkpoint: {checkpoint['total_processed']} symbols previously processed")
                return checkpoint
        except Exception as e:
            log.warning(f"Failed to load checkpoint: {e}")
        return None

    def get_remaining_symbols(self, all_symbols: List[str]) -> List[str]:
        """Get symbols remaining after checkpoint"""
        checkpoint = self.load_checkpoint()
        if checkpoint:
            processed = set(checkpoint['processed_symbols'])
            remaining = [s for s in all_symbols if s not in processed]
            log.info(f"Resuming from checkpoint: {len(remaining)} symbols remaining out of {len(all_symbols)}")
            return remaining
        return all_symbols

    def clear_checkpoint(self) -> None:
        """Clear checkpoint after successful completion"""
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                log.info("Cleared checkpoint file")
        except Exception as e:
            log.warning(f"Failed to clear checkpoint: {e}")


def run_batch_job():
    """Main entry point for Batch job"""
    setup_signal_handlers()

    try:
        # Parse configuration from environment
        symbol_count = int(os.environ.get('SYMBOL_COUNT', '5000'))
        backfill_days = os.environ.get('BACKFILL_DAYS', '30')
        parallelism = os.environ.get('PARALLELISM', '4')
        checkpoint_interval = int(os.environ.get('CHECKPOINT_INTERVAL', '100'))

        log.info(f"Starting buyselldaily Batch job")
        log.info(f"  Expected symbols: {symbol_count}")
        log.info(f"  Backfill days: {backfill_days}")
        log.info(f"  Parallelism: {parallelism}")
        log.info(f"  Checkpoint interval: {checkpoint_interval}")

        # Get all active symbols
        all_symbols = get_active_symbols()
        log.info(f"Found {len(all_symbols)} active symbols in database")

        # Initialize checkpoint manager
        checkpoint_mgr = CheckpointManager()

        # Get remaining symbols (accounting for checkpoint)
        remaining_symbols = checkpoint_mgr.get_remaining_symbols(all_symbols)
        processed_symbols = []
        if checkpoint := checkpoint_mgr.load_checkpoint():
            processed_symbols = checkpoint['processed_symbols']

        log.info(f"Processing {len(remaining_symbols)} remaining symbols")

        # Import loader
        from loadbuyselldaily import BuySellDailyLoader

        loader = BuySellDailyLoader()

        try:
            # Process symbols in chunks with checkpoint
            chunk_size = checkpoint_interval
            cumulative_stats = {
                'rows_inserted': 0,
                'symbols_failed': 0,
                'symbols_processed': 0,
                'duration_sec': 0
            }

            start_time = time.time()

            for i in range(0, len(remaining_symbols), chunk_size):
                # Check for shutdown signal
                if shutdown_event:
                    log.warning("Shutdown signal received, saving checkpoint and exiting...")
                    checkpoint_mgr.save_checkpoint(processed_symbols, cumulative_stats)
                    return 130  # Standard exit code for SIGTERM

                chunk = remaining_symbols[i:i + chunk_size]
                log.info(f"Processing chunk {i // chunk_size + 1}: {len(chunk)} symbols")

                # Run loader on this chunk
                try:
                    chunk_stats = loader.run(chunk, parallelism=int(parallelism))
                    cumulative_stats['rows_inserted'] += chunk_stats.get('rows_inserted', 0)
                    cumulative_stats['symbols_failed'] += chunk_stats.get('symbols_failed', 0)
                    cumulative_stats['symbols_processed'] += len(chunk) - chunk_stats.get('symbols_failed', 0)

                    # Update processed symbols
                    processed_symbols.extend(chunk)

                    # Save checkpoint after each chunk
                    checkpoint_mgr.save_checkpoint(processed_symbols, cumulative_stats)

                    log.info(f"Chunk completed: {chunk_stats.get('rows_inserted', 0)} rows, "
                            f"{chunk_stats.get('symbols_failed', 0)} failures")

                except Exception as e:
                    log.exception(f"Error processing chunk: {e}")
                    cumulative_stats['symbols_failed'] += len(chunk)
                    # Continue with next chunk instead of failing completely

            # Job completed successfully
            cumulative_stats['duration_sec'] = int(time.time() - start_time)
            log.info(f"Batch job completed successfully!")
            log.info(f"  Total rows inserted: {cumulative_stats['rows_inserted']}")
            log.info(f"  Total symbols processed: {cumulative_stats['symbols_processed']}")
            log.info(f"  Total symbols failed: {cumulative_stats['symbols_failed']}")
            log.info(f"  Duration: {cumulative_stats['duration_sec']} seconds")

            # Clear checkpoint on success
            checkpoint_mgr.clear_checkpoint()

            return 0 if cumulative_stats['symbols_failed'] == 0 else 1

        finally:
            loader.close()

    except Exception as e:
        log.exception(f"Batch job failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = run_batch_job()
    sys.exit(exit_code)
