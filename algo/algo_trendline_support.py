#!/usr/bin/env python3
"""
Minervini Trendline Support Detection

Finds 2-point rising support lines and validates entry near the line.
Support line = two recent lows with an uptrend angle.

HIGH CONFIDENCE ENTRY: Stage 2 + RS > 70 + Volume + Entry near trendline support
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
from utils.db_connection import get_db_connection
from pathlib import Path
from config.credential_helper import get_db_password, get_db_config
from datetime import datetime, date, timedelta
from typing import Dict, Optional, Tuple
import logging
import statistics

logger = logging.getLogger(__name__)

