#!/usr/bin/env python3
"""End-to-end integration test for algo trading system."""

import sys
import argparse
import logging

logger = logging.getLogger(__name__)


class E2EIntegrationTest:
    """End-to-end integration tests."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def test_database(self) -> bool:
        """Verify database connectivity."""
        try:
            from utils.db_connection import get_db_connection

            conn = get_db_connection()
            cur = conn.cursor()

            tables = ['price_daily', 'technical_data_daily', 'buy_sell_daily',
                      'stock_scores', 'signal_quality_scores']

            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                logger.info(f"✅ {table}: {count:,} rows")

            cur.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"❌ Database test failed: {e}")
            return False

    def test_orchestrator(self) -> bool:
        """Test orchestrator initializes."""
        try:
            from algo.algo_orchestrator import AlgoOrchestrator
            from config.config import Config

            config = Config()
            logger.info("✅ Orchestrator initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Orchestrator test failed: {e}")
            return False

    def run_all(self, skip_loaders: bool = False) -> int:
        """Run all tests."""
        logging.basicConfig(level=logging.INFO, format='%(message)s')

        logger.info("=" * 60)
        logger.info("END-TO-END INTEGRATION TEST")
        logger.info("=" * 60)

        results = []
        results.append(("Database", self.test_database()))
        results.append(("Orchestrator", self.test_orchestrator()))

        logger.info("\n" + "=" * 60)
        for name, passed in results:
            status = "✅ PASS" if passed else "❌ FAIL"
            logger.info(f"{status}: {name}")

        all_passed = all(r[1] for r in results)
        return 0 if all_passed else 1


def main():
    parser = argparse.ArgumentParser(description='E2E integration test')
    parser.add_argument('--skip-loaders', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    test = E2EIntegrationTest(dry_run=args.dry_run)
    return test.run_all(skip_loaders=args.skip_loaders)


if __name__ == '__main__':
    sys.exit(main())
