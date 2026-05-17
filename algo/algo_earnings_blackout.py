#!/usr/bin/env python3
"""Earnings date awareness and blackout enforcement.

Prevents entries ±N days around earnings announcements to avoid whipsaws.
Default: ±7 days from earnings date is a blackout period.
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
from datetime import datetime, timedelta, date as _date
from typing import Dict, Any
import logging
from config.credential_helper import get_db_password, get_db_config

logger = logging.getLogger(__name__)

try:
    from algo.algo_alerts import AlertManager
except ImportError:
    class AlertManager:
        def critical(self, *args, **kwargs): pass

