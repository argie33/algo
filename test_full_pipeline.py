#!/usr/bin/env python3
"""Full pipeline test: buy_sell_daily → signal_quality_scores → swing_trader_scores → orchestrator Phase 5."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging
from datetime import date
from utils.loader_helpers import get_active_symbols
from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_buy_sell_daily(symbols=None, parallelism=4):
    """Run buy_sell_daily loader for given symbols."""
    logger.info(f"Running buy_sell_daily loader with {parallelism} workers...")
    from loaders.load_buy_sell_daily import SignalsDailyLoader

    if symbols is None:
        symbols = ["ON", "MU"]  # Test with ON and MU

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=parallelism)
        logger.info(f"buy_sell_daily completed: {result}")
        return True
    except Exception as e:
        logger.error(f"buy_sell_daily failed: {e}")
        return False

def run_signal_quality_scores(symbols=None, parallelism=4):
    """Run signal_quality_scores loader."""
    logger.info(f"Running signal_quality_scores loader with {parallelism} workers...")
    from loaders.load_signal_quality_scores import SignalQualityScoresLoader

    if symbols is None:
        symbols = ["ON", "MU"]

    loader = SignalQualityScoresLoader()
    try:
        result = loader.run(symbols, parallelism=parallelism)
        logger.info(f"signal_quality_scores completed: {result}")
        return True
    except Exception as e:
        logger.error(f"signal_quality_scores failed: {e}")
        return False

def run_swing_trader_scores(symbols=None, parallelism=4):
    """Run swing_trader_scores loader."""
    logger.info(f"Running swing_trader_scores loader with {parallelism} workers...")
    from loaders.load_swing_trader_scores import SwingTraderScoresLoader

    if symbols is None:
        symbols = ["ON", "MU"]

    loader = SwingTraderScoresLoader()
    try:
        result = loader.run(symbols, parallelism=parallelism)
        logger.info(f"swing_trader_scores completed: {result}")
        return True
    except Exception as e:
        logger.error(f"swing_trader_scores failed: {e}")
        return False

def check_signals(symbols=None):
    """Check generated signals in database."""
    if symbols is None:
        symbols = ["ON", "MU"]

    logger.info("\n=== Signals Generated ===")
    with DatabaseContext('read') as cur:
        for symbol in symbols:
            cur.execute(
                """SELECT date, signal, strength, reason
                   FROM buy_sell_daily
                   WHERE symbol = %s
                   ORDER BY date DESC
                   LIMIT 10""",
                (symbol,)
            )
            rows = cur.fetchall()
            if rows:
                logger.info(f"\n{symbol}:")
                for date, signal, strength, reason in rows:
                    logger.info(f"  {date} | {signal} | Strength: {strength:.2f} | {reason}")
            else:
                logger.info(f"\n{symbol}: NO SIGNALS")

def check_scores(symbols=None):
    """Check signal quality scores."""
    if symbols is None:
        symbols = ["ON", "MU"]

    logger.info("\n=== Signal Quality Scores ===")
    with DatabaseContext('read') as cur:
        for symbol in symbols:
            cur.execute(
                """SELECT date, signal, quality_score
                   FROM signal_quality_scores
                   WHERE symbol = %s
                   ORDER BY date DESC
                   LIMIT 5""",
                (symbol,)
            )
            rows = cur.fetchall()
            if rows:
                logger.info(f"\n{symbol}:")
                for date, signal, quality_score in rows:
                    logger.info(f"  {date} | {signal} | Quality: {quality_score:.2f if quality_score else 'N/A'}")
            else:
                logger.info(f"\n{symbol}: NO SCORES")

def main():
    symbols = ["ON", "MU"]
    parallelism = 4

    logger.info("=" * 60)
    logger.info("FULL PIPELINE TEST: buy_sell_daily → scores → orchestrator")
    logger.info("=" * 60)

    # Run buy_sell_daily
    if not run_buy_sell_daily(symbols, parallelism):
        logger.error("Pipeline test FAILED at buy_sell_daily")
        return 1

    # Check signals
    check_signals(symbols)

    # Run signal_quality_scores
    if not run_signal_quality_scores(symbols, parallelism):
        logger.error("Pipeline test FAILED at signal_quality_scores")
        return 1

    # Run swing_trader_scores
    if not run_swing_trader_scores(symbols, parallelism):
        logger.error("Pipeline test FAILED at swing_trader_scores")
        return 1

    # Check scores
    check_scores(symbols)

    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE TEST COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

    return 0

if __name__ == "__main__":
    sys.exit(main())
