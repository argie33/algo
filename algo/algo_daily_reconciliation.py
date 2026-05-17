#!/usr/bin/env python3
"""
Daily Reconciliation - Sync positions, calculate P&L, create snapshots

Tasks:
1. Fetch Alpaca account data
2. Compare with algo_positions
3. Calculate P&L and metrics
4. Create portfolio snapshots
5. Audit and log discrepancies
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
from config.credential_helper import get_db_password, get_db_config
import requests
import logging
from pathlib import Path
from datetime import datetime
from utils.trade_status import TradeStatus, PositionStatus
from algo.algo_config import get_config

logger = logging.getLogger(__name__)

