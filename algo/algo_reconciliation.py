#!/usr/bin/env python3
"""
Position Reconciliation — Verify DB matches Alpaca account state

Nightly check: query Alpaca API for all open positions and compare against
DB algo_positions. Alert on any divergence (missing position, qty mismatch,
symbol not held, etc). Catches cases where orders were filled outside our
workflow or positions were closed in Alpaca but marked open in DB.
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
import json
from utils.db_connection import get_db_connection
from pathlib import Path
from config.credential_helper import get_db_password, get_db_config
import logging

logger = logging.getLogger(__name__)

