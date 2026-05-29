#!/usr/bin/env python3
"""
Load signal trade performance metrics.
Tracks how well signals predict price movements.
"""
import psycopg2
from datetime import datetime, timedelta
import logging
from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)

def load_signal_trade_performance():
    """
    Load signal trade performance metrics.
    NOTE: Disabled until rewritten to match schema.
    Table schema expects individual trade records (trade_id FK) with entry/exit prices,
    not aggregated win/loss statistics. This loader tried to insert aggregates
    that don't exist in the table definition.
    TODO: Rewrite to link actual trades to their initiating signals.
    """
    logger.warning("load_signal_trade_performance disabled - schema mismatch")
    return 0

if __name__ == "__main__":
    load_signal_trade_performance()
