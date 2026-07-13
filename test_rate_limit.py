#!/usr/bin/env python3
"""Test to measure rate limiting in stock_prices_daily loader.

Run with increasing symbol counts to find the rate limiting threshold.
Measure actual execution time and identify when batch reduction happens.
"""

import time
import logging
from loaders.load_prices import PriceLoader

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)


def test_price_loader(symbol_count: int, parallelism: int = 2) -> dict:
    """Test price loader with N symbols."""
    import psycopg2

    # Get N symbols from database
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT DISTINCT symbol FROM price_daily ORDER BY symbol LIMIT %s',
        (symbol_count,)
    )
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not symbols:
        logger.error(f"Could not load {symbol_count} symbols from database")
        return {}

    logger.info(f"\n{'='*70}")
    logger.info(f"TEST: {len(symbols)} symbols, parallelism={parallelism}")
    logger.info(f"{'='*70}")

    loader = PriceLoader()
    start_time = time.time()

    try:
        result = loader.run(symbols=symbols, parallelism=parallelism)
        elapsed_sec = time.time() - start_time

        logger.info(f"\n{'RESULT':*^70}")
        logger.info(f"Time: {elapsed_sec:.1f}s ({elapsed_sec/60:.1f}min)")
        logger.info(f"Symbols processed: {result.get('symbols_processed', 0)}/{len(symbols)}")
        logger.info(f"Rows fetched: {result.get('rows_fetched', 0)}")
        logger.info(f"Rate limit errors: {result.get('rate_limit_errors', 0)}")
        logger.info(f"Failed symbols: {result.get('symbols_failed', 0)}")
        logger.info(f"Rate: {len(symbols)/elapsed_sec:.1f} symbols/sec")

        return {
            'symbol_count': len(symbols),
            'elapsed_sec': elapsed_sec,
            'symbols_processed': result.get('symbols_processed', 0),
            'rate_limit_errors': result.get('rate_limit_errors', 0),
            'failed': result.get('symbols_failed', 0),
        }

    except Exception as e:
        elapsed_sec = time.time() - start_time
        logger.error(f"Test failed after {elapsed_sec:.1f}s: {type(e).__name__}: {e}")
        return {
            'symbol_count': len(symbols),
            'elapsed_sec': elapsed_sec,
            'error': str(e),
        }


if __name__ == '__main__':
    results = []

    # Test increasing symbol counts to find rate limit threshold
    test_sizes = [30, 100, 500, 1000, 2000]

    for size in test_sizes:
        result = test_price_loader(size, parallelism=2)
        results.append(result)

        # Stop if we hit errors
        if 'error' in result:
            logger.warning(f"Stopping tests due to error at {size} symbols")
            break

        time.sleep(2)  # Wait between tests

    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"SUMMARY")
    logger.info(f"{'='*70}")
    for r in results:
        symbols = r['symbol_count']
        elapsed = r['elapsed_sec']
        rate = symbols / elapsed
        rate_limit_errs = r.get('rate_limit_errors', 0)
        status = "❌ RATE LIMIT" if rate_limit_errs > 0 else "✅ OK"
        logger.info(
            f"{symbols:5d} symbols: {elapsed:7.1f}s "
            f"({rate:6.1f} sym/sec) "
            f"Rate limit errors: {rate_limit_errs:3d} {status}"
        )
