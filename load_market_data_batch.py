#!/usr/bin/env python3
"""
Market Data Batch Loader — Consolidated market & sentiment data refresh.

Runs multiple loaders in sequence:
1. Market indices (SPY, QQQ, IWM, VIX, etc.)
2. Economic data (Fed rates, yields, spreads, inflation indicators)
3. AAII sentiment (individual investor positioning)
4. Fear & Greed Index (market sentiment)

This is a convenience wrapper scheduled via EventBridge to refresh all
market regime + sentiment data together.

Run:
    python3 load_market_data_batch.py [--parallelism 4]
"""

import argparse
import logging
import os
import sys
import subprocess
from datetime import date
from typing import Tuple
from pathlib import Path

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

# dotenv-autoload
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).resolve().parent / '.env.local'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class MarketDataBatchLoader:
    """Run market data loaders in sequence."""

    # Loaders to run (in order)
    LOADERS = [
        ('loadmarketindices.py', 'Market Indices'),
        ('loadecondata.py', 'Economic Data'),
        ('loadaaiidata.py', 'AAII Sentiment'),
        ('loadfeargreed.py', 'Fear & Greed Index'),
    ]

    def __init__(self, parallelism: int = 4):
        self.parallelism = parallelism
        self.results = {}
        self.script_dir = Path(__file__).parent

    def run_loader(self, loader_name: str, label: str) -> Tuple[bool, str]:
        """Run a single loader and return (success, message)."""
        loader_path = self.script_dir / loader_name

        if not loader_path.exists():
            msg = f"{label}: File not found ({loader_name})"
            logger.warning(msg)
            return False, msg

        try:
            logger.info(f"Running {label}...")
            result = subprocess.run(
                [sys.executable, str(loader_path), f'--parallelism={self.parallelism}'],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout
            )

            if result.returncode == 0:
                msg = f"{label}: [OK]"
                logger.info(msg)
                return True, msg
            else:
                error = result.stderr or result.stdout or 'unknown error'
                msg = f"{label}: [FAILED] {error[:100]}"
                logger.warning(msg)
                return False, msg

        except subprocess.TimeoutExpired:
            msg = f"{label}: [TIMEOUT] exceeded 300s"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"{label}: [ERROR] {str(e)[:100]}"
            logger.error(msg)
            return False, msg

    def record_sla_status(self, success: bool, message: str) -> None:
        """Record loader SLA status in database."""
        try:
            import psycopg2
            from credential_helper import get_db_password

            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "stocks"),
                password=get_db_password(),
                database=os.getenv("DB_NAME", "stocks"),
            )

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO loader_sla_status
                    (loader_name, load_date, status, details)
                    VALUES (%s, %s, %s, %s)
                """, (
                    'load_market_data_batch',
                    date.today(),
                    'success' if success else 'failed',
                    message,
                ))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to record SLA status: {e}")

    def run(self) -> int:
        """Run all loaders and return exit code."""
        logger.info("=== Market Data Batch Loader Started ===")

        total_success = 0
        total_failed = 0

        for loader_name, label in self.LOADERS:
            success, message = self.run_loader(loader_name, label)
            self.results[label] = (success, message)

            if success:
                total_success += 1
            else:
                total_failed += 1

        # Summary
        logger.info("=== Market Data Batch Summary ===")
        for label, (success, message) in self.results.items():
            logger.info(message)

        # Record overall status
        summary = f"Batch complete: {total_success} succeeded, {total_failed} failed"
        logger.info(summary)
        self.record_sla_status(total_failed == 0, summary)

        logger.info("=== Market Data Batch Loader Complete ===")

        # Exit code: 0 if all passed, 1 if any failed
        return 0 if total_failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Consolidated market data batch loader"
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=4,
        help="Parallelism for individual loaders (default: 4)",
    )

    args = parser.parse_args()

    loader = MarketDataBatchLoader(parallelism=args.parallelism)
    exit_code = loader.run()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
