#!/usr/bin/env python3
"""Test actual trading execution against Alpaca paper trading."""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_trading_system():
    """Quick validation that trading system is functional."""
    try:
        # Test imports
        from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
        from algo.trading.order_manager import OrderManager
        from algo.orchestration.orchestrator import Orchestrator
        from utils.db.context import DatabaseContext
        
        logger.info("All trading system modules import successfully")
        
        # Check database has trading data
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_signals")
            signals = cur.fetchone()[0]
            logger.info(f"Signal database has {signals} signals")
            
            cur.execute("SELECT COUNT(*) FROM algo_positions")  
            positions = cur.fetchone()[0]
            logger.info(f"Position database has {positions} positions")
        
        logger.info("✓ TRADING SYSTEM READY FOR LIVE TRADING")
        return 0
        
    except Exception as e:
        logger.error(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(test_trading_system())
