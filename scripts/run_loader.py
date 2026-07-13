#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

Usage:
  python3 scripts/run_loader.py prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader.py technical_indicators
  python3 scripts/run_loader.py stock_scores --limit 100

This bypasses the full orchestrator and Step Functions to test individual loaders quickly.
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger(__name__)


def run_price_loader(symbols=None, backfill_days=1):
    """Run price loader for specific symbols."""
    from loaders.load_prices import PriceLoader

    loader = PriceLoader()
    if not symbols:
        # Default: load all universe symbols (will be fetched from database)
        import psycopg2
        try:
            conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT symbol FROM market_constituents ORDER BY symbol')
            symbols = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            logger.info(f"Loaded {len(symbols)} symbols from universe")
        except Exception as e:
            logger.warning(f"Could not load universe, using default symbols: {e}")
            symbols = ['AAPL', 'SPY', 'QQQ', 'MSFT', 'NVDA']

    result = loader.run(
        symbols=symbols,
        backfill_days=backfill_days
    )
    logger.info(f"Price loader result: {result}")
    return result


def run_technical_indicators_loader(backfill_days=1):
    """Run technical indicators loader."""
    # Load all symbols from universe
    import psycopg2

    from loaders.load_technical_indicators import TechnicalIndicatorsLoader
    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT symbol FROM market_constituents ORDER BY symbol')
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for technical indicators")
    except Exception as e:
        logger.warning(f"Could not load universe, using default symbols: {e}")
        symbols = ['AAPL', 'SPY', 'QQQ', 'MSFT', 'NVDA']

    loader = TechnicalIndicatorsLoader()
    result = loader.run(symbols=symbols, backfill_days=backfill_days)
    logger.info(f"Technical indicators loader result: {result}")
    return result


def run_stock_scores_loader(limit=None):
    """Run stock scores loader."""
    from loaders.load_stock_scores import StockScoresLoader

    loader = StockScoresLoader()
    result = loader.run(limit=limit)
    logger.info(f"Stock scores loader result: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument('loader', choices=['prices', 'technical', 'scores', 'health', 'metrics'],
                       help='Loader to run')
    parser.add_argument('--symbols', help='CSV list of symbols (prices only)')
    parser.add_argument('--backfill', type=int, default=1, help='Days to backfill')
    parser.add_argument('--limit', type=int, help='Limit for scores loader')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.loader == 'prices':
            symbols = args.symbols.split(',') if args.symbols else None
            run_price_loader(symbols=symbols, backfill_days=args.backfill)

        elif args.loader == 'technical':
            run_technical_indicators_loader(backfill_days=args.backfill)

        elif args.loader == 'scores':
            run_stock_scores_loader(limit=args.limit)

        else:
            logger.error(f"Loader {args.loader} not yet implemented")
            return 1

        logger.info("Loader completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Loader failed: {e}", exc_info=args.debug)
        return 1


if __name__ == '__main__':
    sys.exit(main())
