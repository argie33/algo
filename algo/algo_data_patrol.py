#!/usr/bin/env python3

"""
Data Patrol — Continuous integrity watchdog

Beyond simple staleness checks, validates that loaded data is actually USABLE
for finance decisions. Real-money trading needs real data — this catches the
silent failures that mock and sample-based testing miss:

  P1. STALENESS         latest data within expected window per source
  P2. NULL ANOMALIES    sudden spike in NULL values (loader regression)
  P3. ZERO/IDENTICAL    rows with all zeros, identical OHLC (API limit hit)
  P4. PRICE SANITY      prices within reasonable %-change vs prior day
  P5. VOLUME SANITY     volume <1M (new pattern) or >100M (halts/unusual)
  P5B. OHLC SANITY      High >= Open/Close/Low, detect negative prices
  P6. CROSS-SOURCE      validate top symbols vs Alpaca (free, already have key)
  P7. UNIVERSE COVERAGE %symbols updated today (drop-off detection)
  P8. SEQUENCE          dates contiguous (no missing trading days)
  P9. CONSTRAINT        DB integrity (FK, unique, NOT NULL violations)
 P10. SCORE FRESHNESS   computed scores updated post raw data refresh
 P11. LOADER CONTRACTS  per-loader row-count thresholds (regression detection)
 P12. EARNINGS DATA     earnings estimates, revisions, history freshness + coverage
 P13. ETF DATA          ETF prices and signals freshness
 P14. CROSS-ALIGN       symbol universe alignment across dependent tables
 P15. FUNDAMENTALS      financial statements and key metrics freshness
 P16. TRADE ALIGNMENT   every filled trade has price history on/after fill date

Every check writes to data_patrol_log with severity (info/warn/error/critical).
The orchestrator's Phase 1 reads aggregate severity and fails closed on critical.

Designed to run multiple times per day for the high-frequency tables (price,
signals) and daily for fundamentals/earnings. Can run in parallel where safe.

USAGE:
  python3 algo_data_patrol.py                    # full patrol
  python3 algo_data_patrol.py --quick            # critical checks only (P1,P3,P7,P9)
  python3 algo_data_patrol.py --validate-alpaca  # cross-source check vs Alpaca
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import json
import argparse
from utils.db_connection import get_db_connection
import requests
import time
from pathlib import Path
from datetime import datetime, date as _date, timedelta
from algo.algo_sql_safety import assert_safe_table, assert_safe_column, safe_select_count
from utils.structured_logger import get_logger

logger = get_logger(__name__)

