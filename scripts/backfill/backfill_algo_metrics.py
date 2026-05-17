#!/usr/bin/env python3
"""
Backfill Algo Metrics

Calculates market_health_daily and trend_template_data for all historical dates
in the database (from the earliest price_daily up to today).

This is required before running backtests, as load_algo_metrics_daily.py only
processes the latest date. Without this backfill, the filter pipeline lacks
critical market health and trend template data for historical periods.

Run once, or schedule daily for incremental updates.
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
import sys
from utils.db_connection import get_db_connection
from datetime import datetime, timedelta, date as _date
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

