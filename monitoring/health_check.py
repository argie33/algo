#!/usr/bin/env python3
"""
Production Health Monitor - Real-time checks for critical fixes

Monitors the 7 critical fixes deployed in production:
- C1: RSI division by zero (check for NaN in scores)
- C2: Same-day entry/exit (check for same-day closes)
- C3: Fake price injection (check for fallback usage)
- C4: Risk fallback consistency (check drawdown logic)
- C5: Circuit breaker errors (check for halt patterns)
- H3: Duplicate orders (check for dedup cases)
- H6: Data completeness gate (check scores coverage)
"""

from config.credential_manager import get_db_config
import os
import sys
import logging
from datetime import datetime, timedelta, date as _date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

